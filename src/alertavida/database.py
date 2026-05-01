import sqlite3
from datetime import datetime
from pathlib import Path

from alertavida.domain import Alerta


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


def alerta_existe(cod_alerta: int) -> bool:
    with sqlite3.connect(DB_PATH) as conexao:
        cursor = conexao.execute(
            "SELECT 1 FROM alertas WHERE cod_alerta = ? LIMIT 1",
            (cod_alerta,),
        )
        return cursor.fetchone() is not None


def salvar_alerta(alerta: Alerta) -> None:
    """Persiste um Alerta no banco. Levanta se cod_alerta já existir."""
    with sqlite3.connect(DB_PATH) as conexao:
        conexao.execute(
            """
            INSERT INTO alertas (
                cod_alerta, municipio, uf, evento, nivel,
                datahoracriacao, detectado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alerta.cod_alerta,
                alerta.municipio.nome,
                alerta.municipio.uf,
                alerta.tipo_evento.value,
                alerta.nivel_risco.value,
                alerta.data_criacao.isoformat(),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conexao.commit()
