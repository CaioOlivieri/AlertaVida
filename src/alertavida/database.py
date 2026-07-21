"""Persistência SQLite — Camada 1 + refator Camada 4 Parte A.1.4.

Schema da tabela `alertas` reescrito para multi-fonte:
- Surrogate key `id` (FK opaca em outras tabelas).
- `UNIQUE (fonte, cod_alerta)` substitui PK composta.
- Coluna `fonte` discrimina origem do alerta (CEMADEN, EONET, INMET, INPE).
- Coluna `escopo_geografico` armazena classificação calculada na ingestão.

Tabela `eventos` (Outbox Pattern) preserva contrato — `agregado_id` agora
referencia `alertas.id` (surrogate INTEGER), não `cod_alerta` da fonte.
O `cod_alerta` original fica preservado dentro do `payload` JSON do evento.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from alertavida.domain import Alerta
from alertavida.domain.detector import (
    AlertaSnapshot,
    ResultadoDeteccao,
    TipoEventoDetectado,
)
from alertavida.domain.enums import FonteDado

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "alertavida.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextlib.contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Abre conexão SQLite com busy_timeout para contenção multi-thread.

    `sqlite3.Connection` usado como context manager controla apenas a
    *transação* (commit no sucesso / rollback na exceção) — não fecha a
    conexão. O `yield` abaixo acontece DENTRO de um `with conexao:`, então
    uma exceção levantada no bloco do chamador (`with conectar() as
    conexao:`) ainda dispara rollback (issue #40 — invariante da outbox
    transacional, ver wiki/patterns/resilience-invariants.md #4) antes do
    `finally` fechar a conexão de fato.
    """
    conexao = sqlite3.connect(DB_PATH)
    conexao.execute("PRAGMA busy_timeout=5000")
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


class SchemaIncompativelError(Exception):
    """Banco existente tem schema incompatível com a versão atual do código.

    Levantada quando criar_banco() detecta uma tabela `alertas` pré-A.1
    (sem coluna `id` ou `fonte`). Bancos pré-A.1 não têm caminho de migration
    automática — a Camada 4 Parte A.1 (09/05/2026) introduziu ruptura de
    schema (PK composta -> surrogate key) que SQLite não suporta via ALTER.
    """


def _verificar_compatibilidade_schema(conexao: sqlite3.Connection) -> None:
    """Verifica se o schema existente é compatível com a versão atual.

    Casos:
    - Tabela `alertas` não existe -> OK, criar_banco() vai criá-la
    - Tabela existe com `id` + `fonte` -> OK, _migrar_banco() cuida de aditivos
    - Tabela existe sem `id` ou sem `fonte` -> SchemaIncompativelError

    Pré-condição: chamada como primeira operação dentro de criar_banco(),
    antes de qualquer CREATE TABLE ou ALTER TABLE.
    """
    cursor = conexao.execute("PRAGMA table_info(alertas)")
    colunas = {row[1] for row in cursor.fetchall()}

    if not colunas:
        return

    colunas_obrigatorias = {"id", "fonte"}
    faltantes = colunas_obrigatorias - colunas

    if faltantes:
        raise SchemaIncompativelError(
            f"Schema do banco em '{DB_PATH}' é incompatível com a versão atual.\n"
            f"\n"
            f"Detectado: tabela `alertas` sem coluna(s): {sorted(faltantes)}.\n"
            f"Provável origem: banco criado antes da Camada 4 Parte A.1 (09/05/2026).\n"
            f"\n"
            f"A Camada 4 Parte A.1 introduziu ruptura estrutural (surrogate key + "
            f"UNIQUE composto) sem caminho de migration automática — bancos pré-A.1 "
            f"precisam ser recriados.\n"
            f"\n"
            f"Ação: apague o arquivo do banco e rode criar_banco() novamente.\n"
            f"Se houver dados a preservar, exporte para JSON antes de apagar."
        )


def _migrar_banco(conexao: sqlite3.Connection) -> None:
    """Aplica migrations aditivas/de limpeza idempotentes ao schema existente.

    Cobre as colunas COBRADE da Camada 4 Parte A.2 (`cobrade_codigo`,
    `fonte_classificacao`), adicionadas via `ALTER TABLE` apenas quando
    ausentes; a remoção de `assinatura` (issue #8 B1 — coluna nunca lida
    nem escrita com valor real, resquício da abordagem de hash pré-
    `ult_atualizacao`); a remoção dos índices especulativos `idx_uf`,
    `idx_evento`, `idx_nivel` (issue #11 D3 — sem query real hoje, custo
    de escrita sem benefício até a Camada 6 definir os filtros reais); e
    a coluna aditiva `descricao` (issue #11 D4 — write-only no domínio
    até aqui, `NasaEonetSource` já populava com o título do evento mas o
    dado morria na ingestão). A migration de PK composta
    para surrogate (A.1.4) nunca passou por aqui — o banco estava vazio no
    refator e rupturas estruturais são barradas antes por
    `_verificar_compatibilidade_schema`. É o ponto de extensão obrigatório
    para qualquer mudança de schema aditiva ou de limpeza futura.
    """
    # Camada 4 / A.2 — colunas COBRADE
    cursor = conexao.execute("PRAGMA table_info(alertas)")
    colunas_existentes = {row[1] for row in cursor.fetchall()}

    if "cobrade_codigo" not in colunas_existentes:
        conexao.execute("ALTER TABLE alertas ADD COLUMN cobrade_codigo TEXT NULL")

    if "fonte_classificacao" not in colunas_existentes:
        conexao.execute(
            "ALTER TABLE alertas ADD COLUMN fonte_classificacao "
            "TEXT NOT NULL DEFAULT 'INDETERMINADA'"
        )

    # Manutenibilidade #8 B1 — assinatura nunca teve valor real (sempre
    # inserida como NULL literal); DROP seguro, sem dado a preservar.
    if "assinatura" in colunas_existentes:
        conexao.execute("ALTER TABLE alertas DROP COLUMN assinatura")

    # Manutenibilidade #11 D3 — idx_uf/idx_evento/idx_nivel eram especulativos
    # (nenhuma query atual filtra por essas colunas; Camada 6 ainda não
    # existe). DROP INDEX não afeta dados, apenas remove custo de escrita.
    conexao.execute("DROP INDEX IF EXISTS idx_uf")
    conexao.execute("DROP INDEX IF EXISTS idx_evento")
    conexao.execute("DROP INDEX IF EXISTS idx_nivel")

    # Manutenibilidade #11 D4 — descricao era write-only no domínio (NasaEonetSource
    # já a populava com o título do evento, mas o dado morria na ingestão).
    if "descricao" not in colunas_existentes:
        conexao.execute("ALTER TABLE alertas ADD COLUMN descricao TEXT NULL")


def criar_banco() -> None:
    with conectar() as conexao:
        conexao.execute("PRAGMA journal_mode=WAL")
        _verificar_compatibilidade_schema(conexao)  # detecta bancos pré-A.1
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS alertas (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                fonte               TEXT NOT NULL DEFAULT 'CEMADEN',
                cod_alerta          TEXT NOT NULL,
                municipio           TEXT,
                uf                  TEXT,
                evento              TEXT,
                nivel               TEXT,
                datahoracriacao     TEXT,
                detectado_em        TEXT NOT NULL,
                codibge             INTEGER,
                latitude            REAL NOT NULL,
                longitude           REAL NOT NULL,
                escopo_geografico   TEXT NOT NULL DEFAULT 'INDETERMINADO',
                ult_atualizacao     TEXT,
                status_interno      TEXT NOT NULL DEFAULT 'ATIVO',
                visto_ultima_vez    TEXT NOT NULL DEFAULT '',
                rodadas_ausente     INTEGER NOT NULL DEFAULT 0,
                cobrade_codigo      TEXT NULL,
                fonte_classificacao TEXT NOT NULL DEFAULT 'INDETERMINADA',
                descricao           TEXT NULL,
                UNIQUE (fonte, cod_alerta)
            )
            """
        )
        conexao.execute("CREATE INDEX IF NOT EXISTS idx_fonte ON alertas (fonte)")
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_escopo_geografico ON alertas (escopo_geografico)"
        )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo            TEXT NOT NULL,
                agregado_id     INTEGER NOT NULL,
                payload         TEXT NOT NULL,
                schema_versao   INTEGER NOT NULL DEFAULT 1,
                criado_em       TEXT NOT NULL,
                processado_em   TEXT NULL,
                tentativas      INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_eventos_pendentes
            ON eventos (processado_em, criado_em)
            """
        )
        _migrar_banco(conexao)
        conexao.commit()


def buscar_snapshots(fonte: FonteDado) -> list[AlertaSnapshot]:
    """Retorna snapshots de todos os alertas (qualquer status) da fonte.

    Cada snapshot carrega sua `fonte` como campo (lido da row, não
    hardcoded do parâmetro) — robustez contra futuras mudanças no
    WHERE da query. Removeu filtro `status_interno = 'ATIVO'` para que
    alertas RESOLVIDO que reaparecem sejam detectados corretamente.
    """
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            SELECT cod_alerta, fonte, ult_atualizacao,
                   rodadas_ausente, status_interno
            FROM alertas
            WHERE fonte = ?
            """,
            (fonte.value,),
        )
        return [
            AlertaSnapshot(
                cod_alerta=row[0],
                fonte=FonteDado.from_string(row[1]),
                ult_atualizacao=row[2],
                rodadas_ausente=row[3],
                status_interno=row[4],
            )
            for row in cursor.fetchall()
        ]


def _executar_retornando_id(conexao: sqlite3.Connection, sql: str, params: tuple) -> int | None:
    """Executa um UPDATE ... RETURNING id e devolve o id (None se 0 linhas).

    Substitui o par UPDATE + SELECT id por uma única query. RETURNING exige
    SQLite >= 3.35 (Python 3.13 embute >= 3.40).
    """
    row = conexao.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def aplicar_resultado_deteccao(
    resultado: ResultadoDeteccao,
    alertas_por_codigo: dict[str, "Alerta"],
    agora: str,
) -> None:
    """Persiste o resultado do ChangeDetector atomicamente.

    INSERT/UPDATE em alertas e INSERT em eventos ocorrem na mesma transação
    SQLite — outbox pattern. `agregado_id` em eventos referencia o `id`
    surrogate da tabela `alertas`.

    A fonte de cada código é obtida via `resultado.fonte_por_codigo[cod]`
    (populado pelo detector) — não recebe `fonte` como parâmetro. Isso
    permite que rodadas multi-fonte (Camada 5+) sejam tratadas sem
    mudanças nesta função.
    """
    with conectar() as conexao:
        for evento in resultado.eventos:
            agregado_id: int | None = None

            if evento.tipo is TipoEventoDetectado.CRIADO:
                alerta = alertas_por_codigo[evento.cod_alerta]
                ult = alerta.ult_atualizacao.isoformat() if alerta.ult_atualizacao else None
                cursor = conexao.execute(
                    """
                    INSERT INTO alertas (
                        fonte, cod_alerta, municipio, uf, evento, nivel,
                        datahoracriacao, detectado_em, codibge,
                        latitude, longitude, escopo_geografico, ult_atualizacao,
                        status_interno, visto_ultima_vez, rodadas_ausente,
                        cobrade_codigo, fonte_classificacao, descricao
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO', ?, 0, ?, ?, ?)
                    """,
                    (
                        alerta.fonte.value,
                        alerta.cod_alerta,
                        alerta.municipio.nome if alerta.municipio is not None else None,
                        alerta.municipio.uf if alerta.municipio is not None else None,
                        alerta.tipo_evento.value,
                        alerta.nivel_risco.value,
                        alerta.data_criacao.isoformat(),
                        agora,
                        alerta.municipio.codigo_ibge if alerta.municipio is not None else None,
                        alerta.coordenadas.latitude,
                        alerta.coordenadas.longitude,
                        alerta.escopo_geografico.value,
                        ult,
                        agora,
                        alerta.cobrade_codigo,
                        alerta.fonte_classificacao.value,
                        alerta.descricao,
                    ),
                )
                agregado_id = cursor.lastrowid

            elif evento.tipo in (
                TipoEventoDetectado.ATUALIZADO,
                TipoEventoDetectado.REATIVADO,
            ):
                alerta = alertas_por_codigo[evento.cod_alerta]
                ult = alerta.ult_atualizacao.isoformat() if alerta.ult_atualizacao else None
                # REATIVADO reativa a linha (status volta a ATIVO); ATUALIZADO
                # mantém o status. set_status é literal constante (não entrada
                # externa) — sem risco de injeção SQL.
                set_status = (
                    "status_interno = 'ATIVO', "
                    if evento.tipo is TipoEventoDetectado.REATIVADO
                    else ""
                )
                agregado_id = _executar_retornando_id(
                    conexao,
                    f"""
                    UPDATE alertas
                    SET {set_status}nivel = ?, evento = ?, ult_atualizacao = ?,
                        visto_ultima_vez = ?, rodadas_ausente = 0,
                        cobrade_codigo = ?, fonte_classificacao = ?
                    WHERE fonte = ? AND cod_alerta = ?
                    RETURNING id
                    """,
                    (
                        alerta.nivel_risco.value,
                        alerta.tipo_evento.value,
                        ult,
                        agora,
                        alerta.cobrade_codigo,
                        alerta.fonte_classificacao.value,
                        alerta.fonte.value,
                        evento.cod_alerta,
                    ),
                )

            elif evento.tipo is TipoEventoDetectado.RESOLVIDO:
                agregado_id = _executar_retornando_id(
                    conexao,
                    """
                    UPDATE alertas
                    SET status_interno = 'RESOLVIDO', visto_ultima_vez = ?
                    WHERE fonte = ? AND cod_alerta = ?
                    RETURNING id
                    """,
                    (agora, evento.fonte.value, evento.cod_alerta),
                )

            if agregado_id is not None:
                conexao.execute(
                    """
                    INSERT INTO eventos (
                        tipo, agregado_id, payload, schema_versao,
                        criado_em, processado_em, tentativas
                    ) VALUES (?, ?, ?, 1, ?, NULL, 0)
                    """,
                    (
                        evento.tipo,
                        agregado_id,
                        json.dumps(evento.payload, ensure_ascii=False),
                        agora,
                    ),
                )

        codigos_com_evento = {e.cod_alerta for e in resultado.eventos}
        for cod in resultado.codigos_vistos - codigos_com_evento:
            fonte_cod = resultado.fonte_por_codigo[cod]
            conexao.execute(
                """
                UPDATE alertas
                SET visto_ultima_vez = ?, rodadas_ausente = 0
                WHERE fonte = ? AND cod_alerta = ?
                """,
                (agora, fonte_cod.value, cod),
            )

        for cod in resultado.codigos_ausentes:
            fonte_cod = resultado.fonte_por_codigo[cod]
            conexao.execute(
                """
                UPDATE alertas
                SET rodadas_ausente = rodadas_ausente + 1,
                    visto_ultima_vez = ?
                WHERE fonte = ? AND cod_alerta = ?
                """,
                (agora, fonte_cod.value, cod),
            )

        conexao.commit()
