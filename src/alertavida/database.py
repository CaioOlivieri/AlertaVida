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
from pathlib import Path
from typing import Final

from alertavida.domain import Alerta
from alertavida.domain.detector import (
    AlertaSnapshot,
    ResultadoDeteccao,
    TipoEventoDetectado,
)
from alertavida.domain.enums import FonteDado

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
    """Banco existente tem schema incompatível com a versão atual do código.

    Dois gatilhos, ambos sem caminho de migration automática (SQLite não
    suporta a mudança via ALTER TABLE):
    - tabela `alertas` pré-A.1 (sem coluna `id` ou `fonte`) — a Camada 4 Parte
      A.1 (09/05/2026) trocou PK composta por surrogate key;
    - tabela `eventos` sem a FOREIGN KEY para `alertas.id` — banco criado antes
      da issue #22 (2026-07-28), que passou a exigir integridade referencial.
    """


def _verificar_compatibilidade_schema(conexao: sqlite3.Connection) -> None:
    """Verifica se o schema existente é compatível com a versão atual.

    Casos:
    - Tabela `alertas` não existe -> OK, criar_banco() vai criá-la
    - Tabela `alertas` existe com `id` + `fonte` -> OK, _migrar_banco() aditiva
    - Tabela `alertas` existe sem `id` ou sem `fonte` -> SchemaIncompativelError
    - Tabela `eventos` não existe -> OK, criar_banco() vai criá-la (com FK)
    - Tabela `eventos` existe SEM FOREIGN KEY -> SchemaIncompativelError (#22)

    Pré-condição: chamada como primeira operação dentro de criar_banco(),
    antes de qualquer CREATE TABLE ou ALTER TABLE.
    """
    colunas_alertas = {row[1] for row in conexao.execute("PRAGMA table_info(alertas)")}
    if colunas_alertas:
        faltantes = {"id", "fonte"} - colunas_alertas
        if faltantes:
            raise SchemaIncompativelError(
                f"Schema do banco em '{db_path()}' é incompatível com a versão atual.\n"
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

    # Item B da issue #22: `eventos` tem de declarar a FK para `alertas.id`.
    # SQLite não adiciona FK via ALTER TABLE, e recriar a tabela está fora da
    # política aditiva de _migrar_banco — logo, banco pré-#22 é barrado aqui.
    colunas_eventos = {row[1] for row in conexao.execute("PRAGMA table_info(eventos)")}
    if colunas_eventos:
        tem_fk = bool(conexao.execute("PRAGMA foreign_key_list(eventos)").fetchall())
        if not tem_fk:
            raise SchemaIncompativelError(
                f"Schema do banco em '{db_path()}' é incompatível com a versão atual.\n"
                f"\n"
                f"Detectado: tabela `eventos` sem FOREIGN KEY para `alertas.id`.\n"
                f"Provável origem: banco criado antes da issue #22 (2026-07-28).\n"
                f"\n"
                f"A issue #22 passou a exigir integridade referencial em `eventos`. "
                f"SQLite não adiciona FOREIGN KEY via ALTER TABLE, e recriar a tabela "
                f"está fora da política aditiva de _migrar_banco() — bancos pré-#22 "
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

    # Issue #59 — eventos de ciclo de vida de Incidente não podem reusar
    # agregado_id (FK fixa para alertas(id) desde a #22). Coluna aditiva
    # NULL com sua própria FK; SQLite aceita REFERENCES em ADD COLUMN
    # (verificado empiricamente — só não aceita para colunas NOT NULL sem
    # default constante). `incidentes` já existe neste ponto: é criada em
    # criar_banco() antes desta chamada. Ver [[decisions/agregado-incidente-id]].
    cursor_eventos = conexao.execute("PRAGMA table_info(eventos)")
    colunas_eventos = {row[1] for row in cursor_eventos.fetchall()}
    if "agregado_incidente_id" not in colunas_eventos:
        conexao.execute(
            "ALTER TABLE eventos ADD COLUMN agregado_incidente_id "
            "INTEGER NULL REFERENCES incidentes(id)"
        )


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
            ON eventos (processado_em, criado_em)
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
        _migrar_banco(conexao)
        # A coluna agregado_incidente_id só existe garantidamente depois de
        # _migrar_banco (bancos legados a recebem via ALTER TABLE ali) —
        # criar o índice antes disso falharia com "no such column".
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

_TIPOS_EVENTO_INCIDENTE: Final[frozenset[str]] = frozenset(
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
    eh_evento_incidente = tipo in _TIPOS_EVENTO_INCIDENTE
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
