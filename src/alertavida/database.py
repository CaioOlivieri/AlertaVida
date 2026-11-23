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
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from alertavida.domain import Alerta
from alertavida.domain.correlacao import (
    DISTANCIA_MAXIMA_KM,
    JANELA_TEMPO_SEGUNDOS,
    CandidatoCorrelacao,
    DecisaoCorrelacao,
    ResultadoDecisao,
    decidir_correlacao,
)
from alertavida.domain.detector import (
    AlertaSnapshot,
    ResultadoDeteccao,
    TipoEventoDetectado,
)
from alertavida.domain.enums import FonteDado, TipoEvento
from alertavida.domain.tempo import parse_iso_utc

DB_PATH_DEFAULT: Path = Path(__file__).resolve().parent.parent.parent / "data" / "alertavida.db"
ENV_DB_PATH: str = "ALERTAVIDA_DB_PATH"


def db_path() -> Path:
    """Resolve o caminho do banco a cada chamada, a partir da env var.

    `ALERTAVIDA_DB_PATH` sobrepõe o default (`data/alertavida.db` relativo ao
    pacote). Valor ausente ou em branco cai no default, sem levantar — mesmo
    padrão de `ALERTAVIDA_BUFFER_PROXIMO_GRAUS` em `domain/geographic.py`.

    É uma função (não uma constante lida no import) de propósito: a env var
    pode mudar depois do import (testes, hot-reload) e cada acesso reflete o
    valor corrente. Não há efeito colateral de import — o `mkdir` do diretório
    pai foi movido para `conectar()` (ver issue #22, item A).
    """
    valor_raw = os.getenv(ENV_DB_PATH)
    if valor_raw is None or not valor_raw.strip():
        return DB_PATH_DEFAULT
    return Path(valor_raw)


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

    O diretório pai do banco é criado aqui (não no import — issue #22 item A):
    importar o módulo é livre de efeito colateral no filesystem.
    """
    caminho = db_path()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.execute("PRAGMA busy_timeout=5000")
    # foreign_keys é por-conexão e vira no-op dentro de uma transação — tem de
    # ser ligado ANTES do `with conexao:` abaixo (issue #22, item B).
    conexao.execute("PRAGMA foreign_keys=ON")
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


class SchemaIncompativelError(Exception):
    """Banco existente é anterior ao schema que o código atual sabe migrar.

    Desde a #130 (2026-11-22), `_migrar_banco` só cobre o que o banco de
    produção (criado em 2026-08-13) e o snapshot pré-cutover de 2026-09-05
    precisam. Qualquer banco anterior a isso — sem as colunas da Camada 4
    A.2 / #11 em `alertas`, sem a FK da #22 ou sem `agregado_incidente_id`
    (#59) em `eventos` — é recusado aqui em vez de virar uma quimera.
    """


# Colunas que todo banco migrável já tem (produção nasceu em 2026-08-13,
# depois da #59 de 2026-08-12). Verificadas só com `user_version = 0`: a
# partir da #127 a versão de schema já garante o resto.
_COLUNAS_MINIMAS_ALERTAS: Final[frozenset[str]] = frozenset(
    {"id", "fonte", "cobrade_codigo", "fonte_classificacao", "descricao"}
)
_COLUNAS_MINIMAS_EVENTOS: Final[frozenset[str]] = frozenset({"agregado_incidente_id"})


def _verificar_compatibilidade_schema(conexao: sqlite3.Connection) -> None:
    """Recusa bancos anteriores ao que `_migrar_banco` sabe levar ao atual.

    - Banco novo (sem `alertas`) -> OK, `criar_banco()` cria tudo.
    - `user_version >= 1` -> OK: só existe a partir da #127.
    - `user_version = 0` com as colunas mínimas e a FK de `eventos` -> OK
      (banco de produção antes da #127, ou o snapshot de 2026-09-05).
    - Qualquer outra coisa -> SchemaIncompativelError, listando o que falta.

    Pré-condição: primeira operação dentro de `criar_banco()`, antes de
    qualquer CREATE ou ALTER.
    """
    colunas_alertas = {row[1] for row in conexao.execute("PRAGMA table_info(alertas)")}
    if not colunas_alertas:
        return
    if conexao.execute("PRAGMA user_version").fetchone()[0] >= 1:
        return

    problemas: list[str] = []
    faltam_alertas = _COLUNAS_MINIMAS_ALERTAS - colunas_alertas
    if faltam_alertas:
        problemas.append(f"tabela `alertas` sem coluna(s): {sorted(faltam_alertas)}")
    colunas_eventos = {row[1] for row in conexao.execute("PRAGMA table_info(eventos)")}
    if colunas_eventos:
        faltam_eventos = _COLUNAS_MINIMAS_EVENTOS - colunas_eventos
        if faltam_eventos:
            problemas.append(f"tabela `eventos` sem coluna(s): {sorted(faltam_eventos)}")
        if not conexao.execute("PRAGMA foreign_key_list(eventos)").fetchall():
            problemas.append("tabela `eventos` sem FOREIGN KEY para `alertas.id`")
    if problemas:
        raise SchemaIncompativelError(
            f"Schema do banco em '{db_path()}' é anterior ao que esta versão sabe "
            "migrar.\n\nDetectado:\n- "
            + "\n- ".join(problemas)
            + "\n\nDesde a #130, só bancos criados a partir de 2026-08-13 (Camada 5) "
            "são migrados. Ação: restaure um backup recente, ou apague o arquivo e "
            "rode criar_banco() de novo."
        )


def _migrar_banco(conexao: sqlite3.Connection) -> None:
    """Leva um banco migrável ao schema atual. Idempotente.

    Ponto de extensão obrigatório para mudança de schema futura — de
    preferência um passo numerado sob `PRAGMA user_version` (como
    `_corrigir_fuso_cemaden`), não mais inspeção de colunas.

    Os passos para schemas anteriores a 2026-08-13 saíram na #130: cobriam
    bancos que não existem mais em lugar nenhum (ver
    wiki/decisions/retire-pre-production-migrations.md).
    """
    # Manutenibilidade #89 — idx_escopo_geografico era especulativo (nenhuma
    # query filtra por escopo_geografico) e idx_fonte é redundante com
    # sqlite_autoindex_alertas_1 (`fonte` é coluna líder do UNIQUE). Mantido
    # porque o snapshot pré-cutover de 2026-09-05 ainda tem os dois.
    conexao.execute("DROP INDEX IF EXISTS idx_fonte")
    conexao.execute("DROP INDEX IF EXISTS idx_escopo_geografico")

    # Passos numerados por user_version, em ordem.
    _corrigir_fuso_cemaden(conexao)  # 0 -> 1 (#127, migração de valor)
    _indice_pendentes_parcial(conexao)  # 1 -> 2 (#132)


# Issue #127 — versão de schema em `PRAGMA user_version`. Até aqui toda
# migration era idempotente por inspeção (coluna existe? índice existe?); um
# deslocamento de valor não tem como ser inspecionado — rodar duas vezes
# somaria 6h. 0 = banco anterior à #127; 1 = timestamps do CEMADEN já em UTC.
_VERSAO_SCHEMA_FUSO_CEMADEN: Final[int] = 1

# Constante CONGELADA da migration, de propósito NÃO importada de
# sources/cemaden.py: descreve o erro que os dados gravados até a #127
# carregam (lidos como UTC, eram UTC-3), não o fuso corrente do painel. Se
# FUSO_PAINEL_CEMADEN mudar um dia, esta migration continua correta.
_DESLOCAMENTO_FUSO_CEMADEN: Final[timedelta] = timedelta(hours=3)


def _deslocar_iso(valor: str | None, delta: timedelta) -> str | None:
    """Soma `delta` a um timestamp ISO gravado, preservando NULL/vazio.

    Via `datetime` e não aritmética de string/SQL: o resultado tem de ser
    byte a byte o `.isoformat()` que o parser corrigido produz para o mesmo
    dado bruto — o detector compara `ult_atualizacao` como string.
    """
    if not valor:
        return valor
    return (datetime.fromisoformat(valor) + delta).isoformat()


def _corrigir_fuso_cemaden(conexao: sqlite3.Connection) -> None:
    """Migration única (#127): timestamps do CEMADEN gravados como UTC eram
    horário de Brasília — soma 3h a `datahoracriacao` e `ult_atualizacao`.

    Protegida por `user_version`, que é transacional no SQLite: os UPDATEs e
    o bump de versão entram no mesmo commit de `criar_banco()`, então uma
    falha no meio não deixa linhas deslocadas com a versão ainda em 0 (o que
    faria a próxima inicialização deslocar de novo).

    Fora do alcance, por decisão: `eventos.payload` (histórico append-only
    da outbox) mantém os valores antigos. Ver
    wiki/decisions/cemaden-timestamps-brasilia-time.md.
    """
    versao = conexao.execute("PRAGMA user_version").fetchone()[0]
    if versao >= _VERSAO_SCHEMA_FUSO_CEMADEN:
        return
    linhas = conexao.execute(
        "SELECT id, datahoracriacao, ult_atualizacao FROM alertas WHERE fonte = 'CEMADEN'"
    ).fetchall()
    for id_, criacao, atualizacao in linhas:
        conexao.execute(
            "UPDATE alertas SET datahoracriacao = ?, ult_atualizacao = ? WHERE id = ?",
            (
                _deslocar_iso(criacao, _DESLOCAMENTO_FUSO_CEMADEN),
                _deslocar_iso(atualizacao, _DESLOCAMENTO_FUSO_CEMADEN),
                id_,
            ),
        )
    # PRAGMA não aceita parâmetro bind; o valor é constante de módulo.
    conexao.execute(f"PRAGMA user_version = {_VERSAO_SCHEMA_FUSO_CEMADEN}")


# Issue #132 — versão 2: idx_eventos_pendentes passa a ser parcial.
_VERSAO_SCHEMA_INDICE_PENDENTES: Final[int] = 2


def _indice_pendentes_parcial(conexao: sqlite3.Connection) -> None:
    """Passo de schema 2 (#132): `idx_eventos_pendentes` vira índice parcial.

    O dispatcher só consulta `WHERE processado_em IS NULL ORDER BY
    criado_em`, e quase toda a outbox já foi processada — o índice
    completo sobre `(processado_em, criado_em)` era 12 % do arquivo de
    produção para indexar ~0 linhas. O parcial cobre exatamente a
    consulta e fica do tamanho da fila pendente. `CREATE INDEX IF NOT
    EXISTS` em `criar_banco` não substitui um índice existente de mesmo
    nome, por isso o DROP + CREATE explícito aqui, uma vez.
    """
    if conexao.execute("PRAGMA user_version").fetchone()[0] >= _VERSAO_SCHEMA_INDICE_PENDENTES:
        return
    conexao.execute("DROP INDEX IF EXISTS idx_eventos_pendentes")
    conexao.execute(
        "CREATE INDEX idx_eventos_pendentes ON eventos (criado_em) WHERE processado_em IS NULL"
    )
    conexao.execute(f"PRAGMA user_version = {_VERSAO_SCHEMA_INDICE_PENDENTES}")


def criar_banco() -> None:
    with conectar() as conexao:
        conexao.execute("PRAGMA journal_mode=WAL")
        _verificar_compatibilidade_schema(conexao)  # recusa bancos pré-2026-08-13
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
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo                   TEXT NOT NULL,
                agregado_id            INTEGER NOT NULL,
                agregado_incidente_id  INTEGER NULL,
                payload                TEXT NOT NULL,
                schema_versao          INTEGER NOT NULL DEFAULT 1,
                criado_em              TEXT NOT NULL,
                processado_em          TEXT NULL,
                tentativas             INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (agregado_id) REFERENCES alertas(id),
                FOREIGN KEY (agregado_incidente_id) REFERENCES incidentes(id)
            )
            """
        )
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_eventos_pendentes
            ON eventos (criado_em) WHERE processado_em IS NULL
            """
        )
        # SQLite recomenda indexar a child key da FK (issue #22, item B).
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_eventos_agregado_id ON eventos (agregado_id)"
        )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS incidentes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                status        TEXT    NOT NULL DEFAULT 'ATIVO',
                criado_em     TEXT    NOT NULL,
                atualizado_em TEXT    NOT NULL,
                resolvido_em  TEXT    NULL,
                fundido_em    INTEGER NULL,
                FOREIGN KEY (fundido_em) REFERENCES incidentes(id)
            )
            """
        )
        # Child-key index do redirect de fusão (issue #22, item B, mesmo estilo).
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidentes_fundido_em ON incidentes (fundido_em)"
        )
        # Índice de busca de candidatos (#60): incidentes abertos e não fundidos.
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidentes_status_fundido
            ON incidentes (status, fundido_em)
            """
        )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS incidente_membros (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                incidente_id INTEGER NOT NULL,
                alerta_id    INTEGER NOT NULL,
                score        REAL    NOT NULL,
                motivo       TEXT    NOT NULL,
                criado_em    TEXT    NOT NULL,
                UNIQUE (alerta_id),
                FOREIGN KEY (incidente_id) REFERENCES incidentes(id),
                FOREIGN KEY (alerta_id)    REFERENCES alertas(id)
            )
            """
        )
        # UNIQUE (alerta_id) já cria um índice implícito (child key da FK
        # alerta_id -> alertas); incidente_id precisa do seu próprio.
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_incidente_membros_incidente_id
            ON incidente_membros (incidente_id)
            """
        )
        # Issue #60 — índice espacial: tabela virtual R-Tree sobre a posição
        # de cada alerta (bbox degenerada, min=max=ponto). Disponibilidade
        # do módulo verificada empiricamente em ubuntu-latest e
        # windows-latest (ver TestCapacidadeEspacialSQLite em
        # tests/test_database.py e o PR #60) — sem fallback necessário.
        # Populada em aplicar_resultado_deteccao no INSERT de cada alerta
        # CRIADO. (O backfill para alertas anteriores à #60 saiu na #130: o
        # banco de produção nasceu depois dela, sem nenhum alerta órfão.)
        conexao.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS idx_alertas_espacial
            USING rtree(id, min_lat, max_lat, min_lon, max_lon)
            """
        )
        # Issue #60 — dataset de instrumentação para a #63 calibrar: TODO
        # par (alerta, incidente candidato) avaliado, inclusive NAO_VINCULA.
        # incidente_id NULL = blocking não achou nenhum candidato para o
        # alerta. Append-only — nunca UPDATE/DELETE. Shape fixado no plano
        # técnico da #59/#60 (wiki/projects/layer-5-correlation.md).
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS correlacao_observacoes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                alerta_id        INTEGER NOT NULL,
                incidente_id     INTEGER NULL,
                delta_t_segundos REAL    NOT NULL,
                distancia_km     REAL    NULL,
                mesmo_codibge    INTEGER NOT NULL,
                score            REAL    NOT NULL,
                decisao          TEXT    NOT NULL,
                motivo           TEXT    NOT NULL,
                criado_em        TEXT    NOT NULL,
                FOREIGN KEY (alerta_id)    REFERENCES alertas(id),
                FOREIGN KEY (incidente_id) REFERENCES incidentes(id)
            )
            """
        )
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_correlacao_observacoes_alerta_id
            ON correlacao_observacoes (alerta_id)
            """
        )
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_correlacao_observacoes_incidente_id
            ON correlacao_observacoes (incidente_id)
            """
        )
        _migrar_banco(conexao)
        # Child-key index de agregado_incidente_id (#59). A coluna está no
        # CREATE TABLE de `eventos` e é exigida de bancos existentes por
        # _verificar_compatibilidade_schema.
        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_eventos_agregado_incidente_id
            ON eventos (agregado_incidente_id)
            """
        )
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


# Teto de parâmetros por UPDATE em lote — bem abaixo do limite do SQLite
# (32.766 desde 3.32), para nunca depender da versão embutida no Python.
_TAMANHO_LOTE: Final[int] = 500


def _atualizar_em_lote(
    conexao: sqlite3.Connection,
    clausula_set: str,
    agora: str,
    codigos: set[str],
    fonte_por_codigo: dict[str, FonteDado],
) -> None:
    """Um UPDATE por fonte (e por lote de 500), em vez de um por alerta (#132).

    `clausula_set` é literal constante do chamador, com exatamente um `?`
    (o carimbo `agora`) — nunca entrada externa. Os códigos vão como
    parâmetros.
    """
    por_fonte: dict[FonteDado, list[str]] = {}
    for cod in sorted(codigos):
        por_fonte.setdefault(fonte_por_codigo[cod], []).append(cod)
    for fonte, lista in por_fonte.items():
        for inicio in range(0, len(lista), _TAMANHO_LOTE):
            lote = lista[inicio : inicio + _TAMANHO_LOTE]
            marcadores = ", ".join("?" * len(lote))
            conexao.execute(
                f"UPDATE alertas {clausula_set} WHERE fonte = ? AND cod_alerta IN ({marcadores})",
                (agora, fonte.value, *lote),
            )


def aplicar_resultado_deteccao(
    resultado: ResultadoDeteccao,
    alertas_por_codigo: dict[str, "Alerta"],
    agora: str,
) -> dict[str, int]:
    """Persiste o resultado do ChangeDetector atomicamente.

    INSERT/UPDATE em alertas e INSERT em eventos ocorrem na mesma transação
    SQLite — outbox pattern. `agregado_id` em eventos referencia o `id`
    surrogate da tabela `alertas`.

    A fonte de cada código é obtida via `resultado.fonte_por_codigo[cod]`
    (populado pelo detector) — não recebe `fonte` como parâmetro. Isso
    permite que rodadas multi-fonte (Camada 5+) sejam tratadas sem
    mudanças nesta função.

    Retorna `{cod_alerta: alerta_id}` para todo evento com um `agregado_id`
    resolvido (CRIADO/ATUALIZADO/REATIVADO/RESOLVIDO) — Tell, Don't Ask
    (mesmo princípio de `ResultadoDeteccao`): esta função já calcula o id
    surrogate de cada alerta para o INSERT/UPDATE de `alertas`, e a
    integração de correlação (#61) precisa exatamente desses ids logo em
    seguida para CRIADO/REATIVADO/RESOLVIDO — reconsultar por
    (fonte, cod_alerta) seria uma query redundante por alerta.
    """
    ids_por_codigo: dict[str, int] = {}
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
                # Issue #60 — posição imutável após a criação (ATUALIZADO/
                # REATIVADO nunca tocam latitude/longitude, ver ramo abaixo),
                # então o índice espacial só precisa de um INSERT aqui.
                conexao.execute(
                    """
                    INSERT INTO idx_alertas_espacial (id, min_lat, max_lat, min_lon, max_lon)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        agregado_id,
                        alerta.coordenadas.latitude,
                        alerta.coordenadas.latitude,
                        alerta.coordenadas.longitude,
                        alerta.coordenadas.longitude,
                    ),
                )

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
                ids_por_codigo[evento.cod_alerta] = agregado_id
                # Mesmo INSERT dos eventos de Incidente (#131): um só lugar
                # escreve na outbox, e a invariante de agregado_incidente_id
                # vale também para os eventos de Alerta (sempre None aqui).
                _inserir_evento_outbox(
                    conexao,
                    tipo=evento.tipo.value,
                    agregado_id=agregado_id,
                    agregado_incidente_id=None,
                    payload=evento.payload,
                    criado_em=agora,
                )

        codigos_com_evento = {e.cod_alerta for e in resultado.eventos}
        _atualizar_em_lote(
            conexao,
            "SET visto_ultima_vez = ?, rodadas_ausente = 0",
            agora,
            resultado.codigos_vistos - codigos_com_evento,
            resultado.fonte_por_codigo,
        )
        _atualizar_em_lote(
            conexao,
            "SET rodadas_ausente = rodadas_ausente + 1, visto_ultima_vez = ?",
            agora,
            resultado.codigos_ausentes,
            resultado.fonte_por_codigo,
        )

        conexao.commit()
    return ids_por_codigo


# ---------------------------------------------------------------------------
# Persistência de Incidente (Camada 5, issue #59) — tabelas, proveniência,
# redirect de fusão e eventos de outbox. Decidir QUAIS alertas formam um
# Incidente é responsabilidade de #60/#61 (blocking + integração); as
# funções abaixo só persistem uma transição de estado já decidida pelo
# chamador, cada uma na sua própria transação (outbox pattern, invariante 4).
#
# Tipos de evento de Incidente, string crua (mesmo estilo de events.py —
# "sem dependência de domínio, mensagens cruzam a fronteira de processo via
# SQL da outbox onde strings são a representação canônica").
# ---------------------------------------------------------------------------

TIPOS_EVENTO_INCIDENTE: Final[frozenset[str]] = frozenset(
    {
        "IncidenteCriado",
        "IncidenteAtualizado",
        "IncidenteResolvido",
        "IncidenteReativado",
        "IncidenteFundido",
    }
)


def _inserir_evento_outbox(
    conexao: sqlite3.Connection,
    *,
    tipo: str,
    agregado_id: int,
    agregado_incidente_id: int | None,
    payload: dict,
    criado_em: str,
) -> None:
    """INSERT na outbox com a invariante de `agregado_incidente_id` validada.

    `agregado_incidente_id` deve estar preenchido SE E SOMENTE SE `tipo` for
    um evento de ciclo de vida de Incidente — nunca como CHECK constraint
    (SQLite não permite adicioná-la via ALTER TABLE, e quebraria a política
    aditiva de `_migrar_banco`); validado aqui em runtime, mesmo estilo de
    `Alerta._validar_invariante_classificacao` /
    `Incidente._validar_invariante_resolucao`. Ver
    [[decisions/agregado-incidente-id]].
    """
    eh_evento_incidente = tipo in TIPOS_EVENTO_INCIDENTE
    tem_agregado_incidente = agregado_incidente_id is not None
    if eh_evento_incidente != tem_agregado_incidente:
        raise ValueError(
            "Invariante violada: agregado_incidente_id deve estar preenchido "
            "se e somente se o evento for de ciclo de vida de Incidente. "
            f"tipo={tipo!r}, agregado_incidente_id={agregado_incidente_id!r}"
        )
    conexao.execute(
        """
        INSERT INTO eventos (
            tipo, agregado_id, agregado_incidente_id, payload, schema_versao,
            criado_em, processado_em, tentativas
        ) VALUES (?, ?, ?, ?, 1, ?, NULL, 0)
        """,
        (
            tipo,
            agregado_id,
            agregado_incidente_id,
            json.dumps(payload, ensure_ascii=False),
            criado_em,
        ),
    )


def criar_incidente(alerta_id: int, score: float, motivo: str, agora: str) -> int:
    """Abre um novo Incidente com um único membro fundador; emite `IncidenteCriado`.

    `alerta_id` é o disparador: o Alerta cuja correlação não encontrou
    Incidente compatível e abriu um novo (Round 1, Q6, opção 2 — "abre um
    novo"; wiki/projects/layer-5-correlation.md). INSERT em `incidentes` +
    `incidente_membros` + `eventos` na mesma transação SQLite.
    """
    with conectar() as conexao:
        cursor = conexao.execute(
            "INSERT INTO incidentes (status, criado_em, atualizado_em) VALUES ('ATIVO', ?, ?)",
            (agora, agora),
        )
        incidente_id = cursor.lastrowid
        assert incidente_id is not None  # AUTOINCREMENT sempre popula lastrowid
        conexao.execute(
            """
            INSERT INTO incidente_membros (
                incidente_id, alerta_id, score, motivo, criado_em
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (incidente_id, alerta_id, score, motivo, agora),
        )
        _inserir_evento_outbox(
            conexao,
            tipo="IncidenteCriado",
            agregado_id=alerta_id,
            agregado_incidente_id=incidente_id,
            payload={
                "incidente_id": incidente_id,
                "alerta_id": alerta_id,
                "score": score,
                "motivo": motivo,
            },
            criado_em=agora,
        )
        conexao.commit()
    return incidente_id


def adicionar_membro_incidente(
    incidente_id: int, alerta_id: int, score: float, motivo: str, agora: str
) -> None:
    """Associa um Alerta a um Incidente já aberto; emite `IncidenteAtualizado`.

    `alerta_id` é o disparador: o Alerta que a correlação vinculou a um
    Incidente compatível já aberto (Round 1, Q6, opção 1 — "junta-se").
    `UNIQUE (alerta_id)` em `incidente_membros` garante que um Alerta
    pertence a no máximo um Incidente vivo por vez.
    """
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO incidente_membros (
                incidente_id, alerta_id, score, motivo, criado_em
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (incidente_id, alerta_id, score, motivo, agora),
        )
        conexao.execute(
            "UPDATE incidentes SET atualizado_em = ? WHERE id = ?",
            (agora, incidente_id),
        )
        _inserir_evento_outbox(
            conexao,
            tipo="IncidenteAtualizado",
            agregado_id=alerta_id,
            agregado_incidente_id=incidente_id,
            payload={
                "incidente_id": incidente_id,
                "alerta_id": alerta_id,
                "score": score,
                "motivo": motivo,
            },
            criado_em=agora,
        )
        conexao.commit()


def resolver_incidente(incidente_id: int, alerta_id_disparador: int, agora: str) -> None:
    """Resolve um Incidente; emite `IncidenteResolvido`.

    `alerta_id_disparador` é o Alerta cuja resolução completou a condição de
    "todos os membros resolvidos" (Round 1, Q5 — resolve só quando TODOS
    resolvem, nunca quando qualquer um resolve). A decisão de QUANDO chamar
    esta função — a verificação "todos os membros já resolveram?" — pertence
    à integração (#61); esta função só persiste a transição já decidida.
    """
    with conectar() as conexao:
        conexao.execute(
            """
            UPDATE incidentes
            SET status = 'RESOLVIDO', resolvido_em = ?, atualizado_em = ?
            WHERE id = ?
            """,
            (agora, agora, incidente_id),
        )
        _inserir_evento_outbox(
            conexao,
            tipo="IncidenteResolvido",
            agregado_id=alerta_id_disparador,
            agregado_incidente_id=incidente_id,
            payload={"incidente_id": incidente_id, "alerta_id_disparador": alerta_id_disparador},
            criado_em=agora,
        )
        conexao.commit()


def reativar_incidente(incidente_id: int, alerta_id_disparador: int, agora: str) -> None:
    """Reativa um Incidente RESOLVIDO; emite `IncidenteReativado`.

    Espelha `AlertaReativado` ([[decisions/alert-reactivation-instead-of-crash]]):
    um Incidente RESOLVIDO cujo Alerta membro reaparece precisa poder voltar
    a ATIVO, sob pena de deixar `alertas` e `incidentes` inconsistentes
    (Round 1, Q5). `alerta_id_disparador` é o Alerta que reativou.
    """
    with conectar() as conexao:
        conexao.execute(
            """
            UPDATE incidentes
            SET status = 'ATIVO', resolvido_em = NULL, atualizado_em = ?
            WHERE id = ?
            """,
            (agora, incidente_id),
        )
        _inserir_evento_outbox(
            conexao,
            tipo="IncidenteReativado",
            agregado_id=alerta_id_disparador,
            agregado_incidente_id=incidente_id,
            payload={"incidente_id": incidente_id, "alerta_id_disparador": alerta_id_disparador},
            criado_em=agora,
        )
        conexao.commit()


def fundir_incidentes(
    incidente_sobrevivente_id: int,
    incidente_fundido_id: int,
    alerta_id_disparador: int,
    agora: str,
) -> None:
    """Funde dois Incidentes ATIVOs abertos; emite `IncidenteFundido`.

    Redirect append-only (Round 1, Q6): `incidente_fundido_id` NUNCA é
    apagado nem tem seus membros movidos — sua linha ganha
    `fundido_em = incidente_sobrevivente_id`, e ambos os ids permanecem
    resolvíveis para sempre. `alerta_id_disparador` é o Alerta cujo
    processamento revelou que os dois Incidentes descrevem o mesmo evento
    físico.
    """
    with conectar() as conexao:
        conexao.execute(
            "UPDATE incidentes SET fundido_em = ?, atualizado_em = ? WHERE id = ?",
            (incidente_sobrevivente_id, agora, incidente_fundido_id),
        )
        _inserir_evento_outbox(
            conexao,
            tipo="IncidenteFundido",
            agregado_id=alerta_id_disparador,
            agregado_incidente_id=incidente_fundido_id,
            payload={
                "incidente_sobrevivente_id": incidente_sobrevivente_id,
                "incidente_fundido_id": incidente_fundido_id,
                "alerta_id_disparador": alerta_id_disparador,
            },
            criado_em=agora,
        )
        conexao.commit()


def buscar_alertas_orfaos(fonte: FonteDado) -> list[int]:
    """Ids de alertas `ATIVO` da fonte sem linha em `incidente_membros`.

    Mecanismo compensatório do invariante 4 para a Camada 5 (issue #87,
    ver [[decisions/incident-boundary-reconciliation-sweep]]): cobre um
    processo morto entre a transação de `avaliar_candidatos_correlacao` e a
    de `criar_incidente`/`adicionar_membro_incidente` — o alerta fica
    persistido e `ATIVO`, mas sem membership, e nenhuma rodada futura o
    reprocessa (`ATIVO` sem mudança nunca gera `EventoDetectado`).

    Escopo deliberadamente `status_interno = 'ATIVO'`: um órfão que já
    transitou para `RESOLVIDO` antes de ser varrido fica de fora — mesmo
    tratamento que [[decisions/incident-lifecycle-wiring]] já dá a um
    alerta pré-#61 que resolve sem nunca ter sido correlacionado (severidade
    branda, não vale abrir um Incidente para um alerta morto).
    """
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            SELECT a.id
            FROM alertas a
            LEFT JOIN incidente_membros m ON m.alerta_id = a.id
            WHERE a.fonte = ? AND a.status_interno = 'ATIVO' AND m.id IS NULL
            """,
            (fonte.value,),
        )
        return [row[0] for row in cursor.fetchall()]


def buscar_incidente_atual(alerta_id: int) -> int | None:
    """Segue o redirect de fusão (`fundido_em`) até o Incidente sobrevivente
    ao qual `alerta_id` pertence hoje.

    `incidente_membros` nunca move linhas entre incidentes (Round 1, Q6 —
    fusão é redirect, nunca realocação), então a associação original de um
    alerta pode apontar para um Incidente já fundido em outro; este helper
    resolve a cadeia até o id atual. Retorna `None` se o alerta nunca foi
    correlacionado (nenhuma linha em `incidente_membros`) — caso de um
    alerta ainda não processado por `avaliar_candidatos_correlacao`/a ação
    de #61 sobre ela.
    """
    with conectar() as conexao:
        row = conexao.execute(
            "SELECT incidente_id FROM incidente_membros WHERE alerta_id = ?",
            (alerta_id,),
        ).fetchone()
        if row is None:
            return None
        incidente_id: int = row[0]
        while True:
            redirecionamento = conexao.execute(
                "SELECT fundido_em FROM incidentes WHERE id = ?", (incidente_id,)
            ).fetchone()
            if redirecionamento is None or redirecionamento[0] is None:
                return incidente_id
            incidente_id = redirecionamento[0]


def status_incidente(incidente_id: int) -> str:
    """Status atual (`ATIVO`/`RESOLVIDO`) do Incidente.

    Não segue o redirect de fusão — quem chama já resolveu o id atual via
    `buscar_incidente_atual`.
    """
    with conectar() as conexao:
        row = conexao.execute(
            "SELECT status FROM incidentes WHERE id = ?", (incidente_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Incidente id={incidente_id} não encontrado")
        return row[0]


def todos_membros_resolvidos(incidente_id: int) -> bool:
    """True quando TODO Alerta membro do Incidente — e de qualquer Incidente
    fundido nele, transitivamente — está com `status_interno = 'RESOLVIDO'`
    (Round 1, Q5: resolve só quando o ÚLTIMO membro não-resolvido resolve).

    A árvore de fusão importa porque `fundir_incidentes` nunca move linhas
    de `incidente_membros` para o sobrevivente (redirect append-only) — os
    membros do Incidente fundido continuam com `incidente_id` apontando
    para ele, não para o sobrevivente, então contar só os membros do id
    passado ignoraria membros herdados por fusão.
    """
    with conectar() as conexao:
        row = conexao.execute(
            """
            WITH RECURSIVE arvore_fusao(id) AS (
                SELECT ?
                UNION ALL
                SELECT i.id FROM incidentes i
                JOIN arvore_fusao f ON i.fundido_em = f.id
            )
            SELECT COUNT(*)
            FROM incidente_membros im
            JOIN alertas a ON a.id = im.alerta_id
            JOIN arvore_fusao f ON f.id = im.incidente_id
            WHERE a.status_interno != 'RESOLVIDO'
            """,
            (incidente_id,),
        ).fetchone()
        return row[0] == 0


# ---------------------------------------------------------------------------
# Blocking de correlação (Camada 5, issue #60) — geração de candidatos e
# instrumentação. Decidir se um par (Alerta, Incidente candidato) é o mesmo
# evento é responsabilidade do núcleo puro em domain/correlacao.py (#58);
# este módulo só gera candidatos baratos (bbox + janela) e avalia cada um
# através daquele núcleo, registrando TODO par avaliado em
# correlacao_observacoes — inclusive NAO_VINCULA (Round 1, Q1, "instrument
# before calibrating"; wiki/projects/layer-5-correlation.md).
#
# Candidatos = SÓ incidentes com status ATIVO, fundido_em IS NULL, cujo
# bbox intersecte a posição (com buffer) do alerta avaliado e cuja janela de
# tempo por tipo ainda esteja aberta (Round 1, Q6 — custo O(incidentes
# abertos), nunca O(histórico)): a query só toca incidentes já filtrados por
# `idx_incidentes_status_fundido` e os membros DESSES incidentes via
# `idx_alertas_espacial`, nunca a tabela `alertas` inteira.
# ---------------------------------------------------------------------------

# Buffer de blocking em graus decimais — NUNCA usado na decisão (#58 decide
# com haversine exata sobre coordenadas reais); só alimenta o WHERE do
# R-Tree para superselecionar candidatos (Round 1, Q2: bbox pode
# superselecionar, nunca subselecionar). Convertido de DISTANCIA_MAXIMA_KM
# (#58) usando a pior compressão de longitude do território brasileiro
# (~34°S, 1° de longitude ≈ 92 km — valor conservador, arredondado para
# baixo). Na latitude, 111 km/grau é aproximadamente constante em todo o
# país, então o mesmo buffer também cobre esse eixo com folga.
#
# GARANTIA VÁLIDA SÓ PARA LATITUDES BRASILEIRAS (até ~34°S). NasaEonetSource
# ingere eventos globais sem filtro de bbox (decision record, "Global NASA
# EONET ingestion"), e acima de |34°| a compressão de longitude piora (a
# 60°S, 1° de longitude ≈ 55 km — o mesmo buffer cobre só ~30 km ali),
# então FORA do Brasil o blocking pode SUBSELECIONAR candidatos por
# longitude, violando a garantia acima. Limitação conhecida e aceita — o
# produto é brasileiro e o viés do projeto é para separar (Round 2), não
# para vincular de mais —, registrada aqui para não ficar silenciosa.
_KM_POR_GRAU_LONGITUDE_MINIMO_BRASIL: Final[float] = 92.0
BUFFER_BLOQUEIO_GRAUS: Final[float] = DISTANCIA_MAXIMA_KM / _KM_POR_GRAU_LONGITUDE_MINIMO_BRASIL

# Janela de "incidente ainda aberto para novos membros", por tipo de evento
# do ALERTA avaliado (Round 1, Q1 — estrutura per-type mantida em v1). Cada
# entrada é (janela_antes, janela_depois) em segundos: quanto o onset do
# alerta avaliado pode preceder (antes) ou suceder (depois) o onset do
# representante do incidente e ainda contar como candidato. A ASSIMETRIA é
# estrutural — a issue #60 exige a forma per-type/assimétrica em v1 mesmo
# que os dois lados comecem IGUAIS (ambos = domain.correlacao.JANELA_TEMPO_SEGUNDOS)
# — para que a #63 edite só esta tabela de valores, nunca o formato do
# código, quando calibrar contra pares confirmados reais (latência de
# detecção difere por fonte, então antes/depois não devem convergir para o
# mesmo número após calibração). NÃO preencher com valores "da literatura"
# — mesma disciplina de domain/cobrade.py.
JANELA_ABERTA_SEGUNDOS_POR_TIPO: Final[dict[TipoEvento, tuple[float, float]]] = {
    tipo: (JANELA_TEMPO_SEGUNDOS, JANELA_TEMPO_SEGUNDOS) for tipo in TipoEvento
}


@dataclass(frozen=True)
class ObservacaoCandidato:
    """Resultado de avaliar um candidato — o suficiente para quem chama
    (#61) decidir se age sobre `incidente_id` (VINCULA/REVISAO) sem
    reconsultar o banco. `incidente_id is None` só ocorre na linha
    "sem candidatos" (blocking não achou nenhum incidente aberto compatível).
    """

    incidente_id: int | None
    decisao: DecisaoCorrelacao


def _construir_candidato_correlacao(row: tuple) -> CandidatoCorrelacao:
    """Constrói um `CandidatoCorrelacao` a partir de uma row de `alertas`.

    Ordem esperada da row: (fonte, cod_alerta, evento, cobrade_codigo,
    codibge, latitude, longitude, datahoracriacao). `TipoEvento.from_string`/
    `FonteDado.from_string` são a mesma rede de segurança contra dado
    corrompido já usada por `buscar_snapshots` (invariante 15,
    wiki/patterns/resilience-invariants.md).
    """
    fonte, cod_alerta, evento, cobrade_codigo, codibge, latitude, longitude, datahoracriacao = row
    if not datahoracriacao:
        raise ValueError(
            f"Alerta {fonte}/{cod_alerta} sem datahoracriacao — não é possível "
            "correlacionar sem um momento de onset."
        )
    return CandidatoCorrelacao(
        fonte=FonteDado.from_string(fonte),
        cod_alerta=cod_alerta,
        tipo_evento=TipoEvento.from_string(evento),
        cobrade_codigo=cobrade_codigo,
        codigo_ibge=codibge,
        latitude=latitude,
        longitude=longitude,
        momento_onset=parse_iso_utc(datahoracriacao),
    )


def _buscar_incidentes_candidatos(
    conexao: sqlite3.Connection,
    candidato_alerta: CandidatoCorrelacao,
    janela_antes_segundos: float,
    janela_depois_segundos: float,
) -> list[tuple[int, CandidatoCorrelacao]]:
    """Blocking: incidentes abertos com um membro dentro do bbox bufferizado
    E dentro da janela de tempo por tipo, um por incidente.

    Estágio 1 (bbox, R-Tree) roda inteiramente em SQL — é o que realmente
    precisa de índice espacial. Estágio 2 (janela de tempo) roda em Python
    sobre o resultado já filtrado pelo bbox (pequeno, O(incidentes abertos)),
    evitando aritmética de data em SQL sobre strings ISO. Quando um
    incidente tem mais de um membro dentro do bbox, o membro mais
    recentemente associado (`incidente_membros.criado_em` mais alto)
    representa o incidente na comparação — decisão v1, documentada em
    wiki/decisions/incidente-representante-blocking.md.
    """
    linhas = conexao.execute(
        """
        SELECT im.incidente_id, im.criado_em,
               a.fonte, a.cod_alerta, a.evento, a.cobrade_codigo, a.codibge,
               a.latitude, a.longitude, a.datahoracriacao
        FROM idx_alertas_espacial r
        JOIN incidente_membros im ON im.alerta_id = r.id
        JOIN incidentes i ON i.id = im.incidente_id
        JOIN alertas a ON a.id = r.id
        WHERE i.status = 'ATIVO' AND i.fundido_em IS NULL
          AND r.min_lat <= ? AND r.max_lat >= ?
          AND r.min_lon <= ? AND r.max_lon >= ?
        """,
        (
            candidato_alerta.latitude + BUFFER_BLOQUEIO_GRAUS,
            candidato_alerta.latitude - BUFFER_BLOQUEIO_GRAUS,
            candidato_alerta.longitude + BUFFER_BLOQUEIO_GRAUS,
            candidato_alerta.longitude - BUFFER_BLOQUEIO_GRAUS,
        ),
    ).fetchall()

    representante_por_incidente: dict[int, tuple[str, tuple]] = {}
    for incidente_id, criado_em_membro, *campos_alerta in linhas:
        if not campos_alerta[-1]:  # datahoracriacao ausente — membro inutilizável
            continue
        atual = representante_por_incidente.get(incidente_id)
        if atual is None or criado_em_membro > atual[0]:
            representante_por_incidente[incidente_id] = (criado_em_membro, tuple(campos_alerta))

    candidatos: list[tuple[int, CandidatoCorrelacao]] = []
    for incidente_id, (_, campos_alerta) in representante_por_incidente.items():
        representante = _construir_candidato_correlacao(campos_alerta)
        # Sinal importa (Round 1, Q1 — janela assimétrica): delta_t > 0
        # significa que o alerta avaliado tem onset DEPOIS do representante;
        # delta_t < 0, ANTES. Cada lado é checado contra sua própria janela.
        delta_t = (candidato_alerta.momento_onset - representante.momento_onset).total_seconds()
        if -janela_antes_segundos <= delta_t <= janela_depois_segundos:
            candidatos.append((incidente_id, representante))
    return candidatos


def _inserir_observacao_correlacao(
    conexao: sqlite3.Connection,
    *,
    alerta_id: int,
    incidente_id: int | None,
    decisao: DecisaoCorrelacao,
    mesmo_codibge: bool,
    agora: str,
) -> None:
    conexao.execute(
        """
        INSERT INTO correlacao_observacoes (
            alerta_id, incidente_id, delta_t_segundos, distancia_km,
            mesmo_codibge, score, decisao, motivo, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alerta_id,
            incidente_id,
            decisao.delta_t_segundos,
            decisao.distancia_km if incidente_id is not None else None,
            int(mesmo_codibge),
            decisao.score,
            decisao.resultado.value,
            decisao.motivo,
            agora,
        ),
    )


def avaliar_candidatos_correlacao(alerta_id: int, agora: str) -> list[ObservacaoCandidato]:
    """Gera candidatos (blocking), avalia cada um via `decidir_correlacao`
    (#58) e grava uma linha em `correlacao_observacoes` por par avaliado —
    inclusive quando não há nenhum candidato. Não muta `incidentes`/
    `incidente_membros`: agir sobre VINCULA/REVISAO (criar, juntar, fundir)
    é responsabilidade de quem chama (#61).
    """
    with conectar() as conexao:
        row_alerta = conexao.execute(
            """
            SELECT fonte, cod_alerta, evento, cobrade_codigo, codibge,
                   latitude, longitude, datahoracriacao
            FROM alertas WHERE id = ?
            """,
            (alerta_id,),
        ).fetchone()
        if row_alerta is None:
            raise ValueError(f"Alerta id={alerta_id} não encontrado")
        candidato_alerta = _construir_candidato_correlacao(row_alerta)

        janela_antes, janela_depois = JANELA_ABERTA_SEGUNDOS_POR_TIPO[candidato_alerta.tipo_evento]
        candidatos = _buscar_incidentes_candidatos(
            conexao, candidato_alerta, janela_antes, janela_depois
        )

        resultados: list[ObservacaoCandidato] = []
        if not candidatos:
            decisao_vazia = DecisaoCorrelacao(
                resultado=ResultadoDecisao.NAO_VINCULA,
                score=0.0,
                motivo="sem_candidatos",
                distancia_km=0.0,
                delta_t_segundos=0.0,
            )
            _inserir_observacao_correlacao(
                conexao,
                alerta_id=alerta_id,
                incidente_id=None,
                decisao=decisao_vazia,
                mesmo_codibge=False,
                agora=agora,
            )
            resultados.append(ObservacaoCandidato(incidente_id=None, decisao=decisao_vazia))
        else:
            for incidente_id, representante in candidatos:
                decisao = decidir_correlacao(candidato_alerta, representante)
                mesmo_codibge = (
                    candidato_alerta.codigo_ibge is not None
                    and candidato_alerta.codigo_ibge == representante.codigo_ibge
                )
                _inserir_observacao_correlacao(
                    conexao,
                    alerta_id=alerta_id,
                    incidente_id=incidente_id,
                    decisao=decisao,
                    mesmo_codibge=mesmo_codibge,
                    agora=agora,
                )
                resultados.append(ObservacaoCandidato(incidente_id=incidente_id, decisao=decisao))

        conexao.commit()
    return resultados
