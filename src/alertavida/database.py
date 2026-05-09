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

import json
import sqlite3
from pathlib import Path

from alertavida.domain import Alerta
from alertavida.domain.detector import AlertaSnapshot, EventoDetectado, ResultadoDeteccao


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "alertavida.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _migrar_banco(conexao: sqlite3.Connection) -> None:
    """Reservado para migrations futuras.

    A migration de PK composta para surrogate (A.1.4) não foi necessária
    aqui porque o banco estava vazio quando o refator aconteceu. Mantida
    como ponto de extensão obrigatório — qualquer mudança de schema futura
    é registrada nesta função.
    """
    pass


def criar_banco() -> None:
    with sqlite3.connect(DB_PATH) as conexao:
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
                assinatura          TEXT,
                UNIQUE (fonte, cod_alerta)
            )
            """
        )
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_uf ON alertas (uf)"
        )
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_evento ON alertas (evento)"
        )
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_nivel ON alertas (nivel)"
        )
        conexao.execute(
            "CREATE INDEX IF NOT EXISTS idx_fonte ON alertas (fonte)"
        )
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


def buscar_snapshots_ativos(fonte: str) -> list[AlertaSnapshot]:
    """Retorna snapshots de alertas ATIVOS da fonte especificada."""
    with sqlite3.connect(DB_PATH) as conexao:
        cursor = conexao.execute(
            """
            SELECT cod_alerta, nivel, evento, ult_atualizacao,
                   rodadas_ausente, status_interno
            FROM alertas
            WHERE status_interno = 'ATIVO' AND fonte = ?
            """,
            (fonte,),
        )
        return [
            AlertaSnapshot(
                cod_alerta=row[0],
                nivel_risco=row[1],
                tipo_evento=row[2],
                ult_atualizacao=row[3],
                rodadas_ausente=row[4],
                status_interno=row[5],
            )
            for row in cursor.fetchall()
        ]


def aplicar_resultado_deteccao(
    resultado: ResultadoDeteccao,
    alertas_por_codigo: dict[str, "Alerta"],
    fonte: str,
    agora: str,
) -> None:
    """Persiste o resultado do ChangeDetector atomicamente.

    INSERT/UPDATE em alertas e INSERT em eventos ocorrem na mesma transação
    SQLite — outbox pattern. `agregado_id` em eventos referencia o `id`
    surrogate da tabela `alertas`.
    """
    with sqlite3.connect(DB_PATH) as conexao:
        eventos: list[EventoDetectado] = resultado.eventos
        for evento in eventos:
            agregado_id: int | None = None

            if evento.tipo == "AlertaCriado":
                alerta = alertas_por_codigo[evento.cod_alerta]
                ult = (
                    alerta.ult_atualizacao.isoformat()
                    if alerta.ult_atualizacao
                    else None
                )
                cursor = conexao.execute(
                    """
                    INSERT INTO alertas (
                        fonte, cod_alerta, municipio, uf, evento, nivel,
                        datahoracriacao, detectado_em, codibge,
                        latitude, longitude, escopo_geografico, ult_atualizacao,
                        status_interno, visto_ultima_vez, rodadas_ausente,
                        assinatura
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO', ?, 0, NULL)
                    """,
                    (
                        fonte,
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
                    ),
                )
                agregado_id = cursor.lastrowid

            elif evento.tipo == "AlertaAtualizado":
                alerta = alertas_por_codigo[evento.cod_alerta]
                ult = (
                    alerta.ult_atualizacao.isoformat()
                    if alerta.ult_atualizacao
                    else None
                )
                conexao.execute(
                    """
                    UPDATE alertas
                    SET nivel = ?, evento = ?, ult_atualizacao = ?,
                        visto_ultima_vez = ?, rodadas_ausente = 0
                    WHERE fonte = ? AND cod_alerta = ?
                    """,
                    (
                        alerta.nivel_risco.value,
                        alerta.tipo_evento.value,
                        ult,
                        agora,
                        fonte,
                        evento.cod_alerta,
                    ),
                )
                cur_id = conexao.execute(
                    "SELECT id FROM alertas WHERE fonte = ? AND cod_alerta = ?",
                    (fonte, evento.cod_alerta),
                )
                row = cur_id.fetchone()
                agregado_id = row[0] if row is not None else None

            elif evento.tipo == "AlertaResolvido":
                conexao.execute(
                    """
                    UPDATE alertas
                    SET status_interno = 'RESOLVIDO', visto_ultima_vez = ?
                    WHERE fonte = ? AND cod_alerta = ?
                    """,
                    (agora, fonte, evento.cod_alerta),
                )
                cur_id = conexao.execute(
                    "SELECT id FROM alertas WHERE fonte = ? AND cod_alerta = ?",
                    (fonte, evento.cod_alerta),
                )
                row = cur_id.fetchone()
                agregado_id = row[0] if row is not None else None

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
            conexao.execute(
                """
                UPDATE alertas
                SET visto_ultima_vez = ?, rodadas_ausente = 0
                WHERE fonte = ? AND cod_alerta = ?
                """,
                (agora, fonte, cod),
            )

        for cod in resultado.codigos_ausentes:
            conexao.execute(
                """
                UPDATE alertas
                SET rodadas_ausente = rodadas_ausente + 1,
                    visto_ultima_vez = ?
                WHERE fonte = ? AND cod_alerta = ?
                """,
                (agora, fonte, cod),
            )

        conexao.commit()
