import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "alertavida.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def criar_banco():
    with sqlite3.connect(DB_PATH) as conexao:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS alertas (
                cod_alerta INTEGER PRIMARY KEY,
                municipio TEXT,
                uf TEXT,
                evento TEXT,
                nivel TEXT,
                datahoracriacao TEXT,
                detectado_em TEXT NOT NULL
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
        conexao.commit()


def alerta_existe(cod_alerta):
    with sqlite3.connect(DB_PATH) as conexao:
        cursor = conexao.execute(
            "SELECT 1 FROM alertas WHERE cod_alerta = ? LIMIT 1",
            (int(cod_alerta),),
        )
        return cursor.fetchone() is not None


def salvar_alerta(alerta_dict):
    cod_alerta = alerta_dict.get("cod_alerta")
    if cod_alerta is None:
        raise ValueError("O campo 'cod_alerta' e obrigatorio para salvar o alerta.")

    with sqlite3.connect(DB_PATH) as conexao:
        conexao.execute(
            """
            INSERT INTO alertas (
                cod_alerta,
                municipio,
                uf,
                evento,
                nivel,
                datahoracriacao,
                detectado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(cod_alerta),
                alerta_dict.get("municipio"),
                alerta_dict.get("uf"),
                alerta_dict.get("evento"),
                alerta_dict.get("nivel"),
                alerta_dict.get("datahoracriacao"),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conexao.commit()
