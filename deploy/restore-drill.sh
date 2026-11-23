#!/usr/bin/env bash
# deploy/restore-drill.sh — proves the OFF-HOST backups can actually be
# restored (issue #134). A backup nobody has restored is an assumption.
#
#   sudo bash deploy/restore-drill.sh
#
# What it does, read-only for production:
#   1. picks the newest backup on the Drive remote (`gdrive:AlertaVida/backups`);
#   2. downloads it into a scratch directory — never over the live database;
#   3. compares its SHA-256 with the local copy of the same file, if present;
#   4. runs PRAGMA integrity_check and counts rows in every table;
#   5. checks the counts against the local copy (same snapshot => equal);
#   6. opens the restored copy with the CURRENT code (`criar_banco()` +
#      `buscar_snapshots()`), proving today's release can run on it;
#   7. deletes the scratch copy, unless KEEP=1.
# The live database and the service are never touched. Last line is an
# explicit success line; its absence is the failure signal.
set -euo pipefail

SERVICE_USER=alertavida
DATA_DIR=/var/lib/alertavida
LOCAL_BACKUPS="$DATA_DIR/backups"
RCLONE_CONFIG_PATH="$DATA_DIR/rclone/rclone.conf"
REMOTE=gdrive:AlertaVida/backups
VENV_PY=/opt/alertavida/.venv/bin/python
SCRATCH="$DATA_DIR/restore-drill/$(date -u +%Y%m%dT%H%M%SZ)"

as_service() {
    runuser -u "$SERVICE_USER" -- env HOME="$DATA_DIR" RCLONE_CONFIG="$RCLONE_CONFIG_PATH" "$@"
}

echo "== 1/6: newest backup on $REMOTE =="
NEWEST="$(as_service rclone lsf "$REMOTE" --include 'alertavida-*.db' | sort | tail -n1)"
if [ -z "$NEWEST" ]; then
    echo "No backup found on $REMOTE" >&2
    exit 1
fi
echo "$NEWEST"

echo "== 2/6: download into $SCRATCH (scratch, not the live path) =="
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0770 "$SCRATCH"
as_service rclone copy "$REMOTE/$NEWEST" "$SCRATCH/"
RESTORED="$SCRATCH/$NEWEST"
ls -l "$RESTORED"

echo "== 3/6: SHA-256 against the local copy =="
if [ -f "$LOCAL_BACKUPS/$NEWEST" ]; then
    SUM_REMOTE="$(sha256sum "$RESTORED" | cut -d' ' -f1)"
    SUM_LOCAL="$(sha256sum "$LOCAL_BACKUPS/$NEWEST" | cut -d' ' -f1)"
    if [ "$SUM_REMOTE" != "$SUM_LOCAL" ]; then
        echo "SHA-256 MISMATCH: restored=$SUM_REMOTE local=$SUM_LOCAL" >&2
        exit 1
    fi
    echo "identical (${SUM_REMOTE:0:16}…)"
    LOCAL_COPY="$LOCAL_BACKUPS/$NEWEST"
else
    echo "no local copy of $NEWEST (pruned?) — skipping the byte comparison"
    LOCAL_COPY=""
fi

echo "== 4-5/6: integrity + row counts (restored vs local copy) =="
# Paths as argv to a quoted heredoc, never pasted into Python source (#133).
as_service "$VENV_PY" - "$RESTORED" "$LOCAL_COPY" <<'PY'
import sqlite3
import sys

TABELAS = ("alertas", "eventos", "incidentes", "incidente_membros", "correlacao_observacoes")


def contar(caminho):
    # immutable=1, not just mode=ro: a read-only connection to a WAL-mode
    # file still creates -wal/-shm beside it, which left stray files in
    # the backups directory on the first run. Backups never change, so
    # immutable is safe here (it would NOT be for the live database).
    conexao = sqlite3.connect(f"file:{caminho}?mode=ro&immutable=1", uri=True)
    try:
        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]
        versao = conexao.execute("PRAGMA user_version").fetchone()[0]
        linhas = {t: conexao.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABELAS}
        ultima = conexao.execute("SELECT MAX(visto_ultima_vez) FROM alertas").fetchone()[0]
    finally:
        conexao.close()
    return integridade, versao, linhas, ultima


restaurado, local = sys.argv[1], sys.argv[2]
integridade, versao, linhas, ultima = contar(restaurado)
print(f"integrity_check: {integridade}")
print(f"user_version: {versao}")
for tabela, n in linhas.items():
    print(f"{tabela}: {n}")
print(f"ultima rodada no backup: {ultima}")
if integridade != "ok":
    raise SystemExit("integrity_check did not return ok")
if linhas["alertas"] == 0:
    raise SystemExit("restored database has no alerts")
if local:
    _, _, linhas_local, _ = contar(local)
    diferentes = [t for t in TABELAS if linhas[t] != linhas_local[t]]
    if diferentes:
        raise SystemExit(f"row count mismatch vs local copy: {diferentes}")
    print("row counts equal to the local copy")
PY

echo "== 6/6: current release opens the restored copy =="
as_service env ALERTAVIDA_DB_PATH="$RESTORED" "$VENV_PY" - <<'PY'
from alertavida.database import buscar_snapshots, criar_banco
from alertavida.domain.enums import FonteDado

criar_banco()  # migrations run against the scratch copy only
for fonte in (FonteDado.CEMADEN, FonteDado.EONET):
    print(f"{fonte.value}: {len(buscar_snapshots(fonte))} snapshots")
PY

if [ "${KEEP:-0}" = "1" ]; then
    echo "scratch copy kept at $SCRATCH (KEEP=1) — delete it when done"
else
    rm -rf "$SCRATCH"
    rmdir --ignore-fail-on-non-empty "$DATA_DIR/restore-drill"
fi
echo "=== RESTORE DRILL: ALL CHECKS PASSED — $NEWEST ==="
