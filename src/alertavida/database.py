import sqlite3
from datetime import datetime
from pathlib import Path

from alertavida.domain import Alerta


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
