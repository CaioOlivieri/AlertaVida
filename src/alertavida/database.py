import sqlite3
from datetime import datetime
from pathlib import Path

from alertavida.domain import Alerta
from alertavida.domain.detector import AlertaSnapshot, EventoDetectado, ResultadoDeteccao


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "alertavida.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _migrar_banco(conexao: sqlite3.Connection) -> None:
    """Aplica colunas novas em bancos criados antes da Camada 3."""
    colunas_novas = {
        "codibge": "INTEGER",
        "latitude": "REAL",
        "longitude": "REAL",
        "ult_atualizacao": "TEXT",
        "status_interno": "TEXT NOT NULL DEFAULT 'ATIVO'",
        "visto_ultima_vez": "TEXT NOT NULL DEFAULT ''",
        "rodadas_ausente": "INTEGER NOT NULL DEFAULT 0",
        "assinatura": "TEXT",
    }
    cursor = conexao.execute("PRAGMA table_info(alertas)")
    existentes = {row[1] for row in cursor.fetchall()}
    for coluna, tipo in colunas_novas.items():
        if coluna not in existentes:
            conexao.execute(
                f"ALTER TABLE alertas ADD COLUMN {coluna} {tipo}"
            )


def criar_banco() -> None:
    with sqlite3.connect(DB_PATH) as conexao:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS alertas (
                cod_alerta          INTEGER PRIMARY KEY,
                municipio           TEXT,
                uf                  TEXT,
                evento              TEXT,
                nivel               TEXT,
                datahoracriacao     TEXT,
                detectado_em        TEXT NOT NULL,
                codibge             INTEGER,
                latitude            REAL,
                longitude           REAL,
                ult_atualizacao     TEXT,
                status_interno      TEXT NOT NULL DEFAULT 'ATIVO',
                visto_ultima_vez    TEXT NOT NULL DEFAULT '',
                rodadas_ausente     INTEGER NOT NULL DEFAULT 0,
                assinatura          TEXT
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


def alerta_existe(cod_alerta: int) -> bool:
    with sqlite3.connect(DB_PATH) as conexao:
        cursor = conexao.execute(
            "SELECT 1 FROM alertas WHERE cod_alerta = ? LIMIT 1",
            (cod_alerta,),
        )
        return cursor.fetchone() is not None


def salvar_alerta(alerta: Alerta) -> None:
    """Persiste um Alerta no banco. Levanta se cod_alerta já existir."""
    lat = lon = None
    if alerta.coordenadas is not None:
        lat = alerta.coordenadas.latitude
        lon = alerta.coordenadas.longitude
    agora = datetime.now().isoformat(timespec="seconds")
    ult_str = (
        alerta.ult_atualizacao.isoformat()
        if alerta.ult_atualizacao is not None
        else None
    )
    with sqlite3.connect(DB_PATH) as conexao:
        conexao.execute(
            """
            INSERT INTO alertas (
                cod_alerta, municipio, uf, evento, nivel,
                datahoracriacao, detectado_em, codibge, latitude, longitude,
                ult_atualizacao, status_interno, visto_ultima_vez,
                rodadas_ausente, assinatura
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO', ?, 0, NULL)
            """,
            (
                alerta.cod_alerta,
                alerta.municipio.nome,
                alerta.municipio.uf,
                alerta.tipo_evento.value,
                alerta.nivel_risco.value,
                alerta.data_criacao.isoformat(),
                agora,
                alerta.municipio.codigo_ibge,
                lat,
                lon,
                ult_str,
                agora,
            ),
        )
        conexao.commit()


def buscar_snapshots_ativos() -> list[AlertaSnapshot]:
    """Retorna snapshot de todos os alertas com status_interno='ATIVO'."""
    with sqlite3.connect(DB_PATH) as conexao:
        cursor = conexao.execute(
            """
            SELECT cod_alerta, nivel, evento, ult_atualizacao,
                   rodadas_ausente, status_interno
            FROM alertas
            WHERE status_interno = 'ATIVO'
            """
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
    alertas_por_codigo: dict[int, "Alerta"],
    agora: str,
) -> None:
    """
    Persiste o resultado do ChangeDetector atomicamente.
    salvar_alerta e salvar_evento ocorrem na mesma transação — outbox pattern.
    agora: isoformat sem microssegundos, usado em detectado_em e visto_ultima_vez.
    """
    with sqlite3.connect(DB_PATH) as conexao:
        eventos: list[EventoDetectado] = resultado.eventos
        for evento in eventos:
            import json as _json

            if evento.tipo == "AlertaCriado":
                alerta = alertas_por_codigo[evento.cod_alerta]
                lat = alerta.coordenadas.latitude if alerta.coordenadas else None
                lon = alerta.coordenadas.longitude if alerta.coordenadas else None
                ult = (
                    alerta.ult_atualizacao.isoformat()
                    if alerta.ult_atualizacao
                    else None
                )
                conexao.execute(
                    """
                    INSERT INTO alertas (
                        cod_alerta, municipio, uf, evento, nivel,
                        datahoracriacao, detectado_em, codibge,
                        latitude, longitude, ult_atualizacao,
                        status_interno, visto_ultima_vez, rodadas_ausente,
                        assinatura
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO', ?, 0, NULL)
                    """,
                    (
                        alerta.cod_alerta,
                        alerta.municipio.nome,
                        alerta.municipio.uf,
                        alerta.tipo_evento.value,
                        alerta.nivel_risco.value,
                        alerta.data_criacao.isoformat(),
                        agora,
                        alerta.municipio.codigo_ibge,
                        lat,
                        lon,
                        ult,
                        agora,
                    ),
                )

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
                    WHERE cod_alerta = ?
                    """,
                    (
                        alerta.nivel_risco.value,
                        alerta.tipo_evento.value,
                        ult,
                        agora,
                        evento.cod_alerta,
                    ),
                )

            elif evento.tipo == "AlertaResolvido":
                conexao.execute(
                    """
                    UPDATE alertas
                    SET status_interno = 'RESOLVIDO', visto_ultima_vez = ?
                    WHERE cod_alerta = ?
                    """,
                    (agora, evento.cod_alerta),
                )

            conexao.execute(
                """
                INSERT INTO eventos (
                    tipo, agregado_id, payload, schema_versao,
                    criado_em, processado_em, tentativas
                ) VALUES (?, ?, ?, 1, ?, NULL, 0)
                """,
                (
                    evento.tipo,
                    evento.cod_alerta,
                    _json.dumps(evento.payload, ensure_ascii=False),
                    agora,
                ),
            )

        codigos_com_evento = {e.cod_alerta for e in resultado.eventos}
        for cod in resultado.codigos_vistos - codigos_com_evento:
            conexao.execute(
                """
                UPDATE alertas
                SET visto_ultima_vez = ?, rodadas_ausente = 0
                WHERE cod_alerta = ?
                """,
                (agora, cod),
            )

        for cod in resultado.codigos_ausentes:
            conexao.execute(
                """
                UPDATE alertas
                SET rodadas_ausente = rodadas_ausente + 1,
                    visto_ultima_vez = ?
                WHERE cod_alerta = ?
                """,
                (agora, cod),
            )

        conexao.commit()
