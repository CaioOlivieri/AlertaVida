"""WAL-safe SQLite backup for the AlertaVida database.

The `sqlite3` CLI is not assumed to be installed on the deploy target, so
this reimplements the same backup semantics the CLI's `.backup` command
provides — through `sqlite3.Connection.backup()`, the stdlib API every
Python 3 ships with. A plain file copy (`cp`) of a database in WAL mode can
read the main file mid-checkpoint while committed pages still sit in the
`-wal` file, producing an inconsistent snapshot; `.backup()` uses SQLite's
online backup API and is safe against concurrent writers.

Run via `deploy/backup.sh`, itself invoked by the `alertavida-backup.timer`
systemd timer. Not part of the `alertavida` package: it is deploy tooling,
not application code, and only needs the stdlib plus the already-installed
`alertavida.database.db_path()` for path resolution.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from alertavida.database import db_path

BACKUP_DIR_DEFAULT = Path("/var/lib/alertavida/backups")
RETENTION_DAYS_DEFAULT = 30


def fazer_backup(origem: Path, diretorio_destino: Path) -> Path:
    """Copia `origem` para um novo arquivo em `diretorio_destino` via API .backup."""
    diretorio_destino.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = diretorio_destino / f"alertavida-{timestamp}.db"

    conexao_origem = sqlite3.connect(origem)
    try:
        conexao_destino = sqlite3.connect(destino)
        try:
            conexao_origem.backup(conexao_destino)
        finally:
            conexao_destino.close()
    finally:
        conexao_origem.close()

    return destino


def podar_backups_antigos(diretorio: Path, dias_retencao: int) -> list[Path]:
    """Remove backups com mtime mais antigo que `dias_retencao` dias. Retorna os removidos."""
    limite = datetime.now(timezone.utc).timestamp() - dias_retencao * 86400
    removidos = []
    for caminho in diretorio.glob("alertavida-*.db"):
        if caminho.stat().st_mtime < limite:
            caminho.unlink()
            removidos.append(caminho)
    return removidos


def main() -> int:
    origem = db_path()
    diretorio_destino = Path(
        os.getenv("ALERTAVIDA_BACKUP_DIR", str(BACKUP_DIR_DEFAULT))
    )
    dias_retencao = int(
        os.getenv("ALERTAVIDA_BACKUP_RETENTION_DAYS", str(RETENTION_DAYS_DEFAULT))
    )

    if not origem.exists():
        print(f"Banco não encontrado em {origem}", file=sys.stderr)
        return 1

    destino = fazer_backup(origem, diretorio_destino)
    print(f"Backup gravado em {destino}")

    removidos = podar_backups_antigos(diretorio_destino, dias_retencao)
    for caminho in removidos:
        print(f"Backup expirado removido: {caminho}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
