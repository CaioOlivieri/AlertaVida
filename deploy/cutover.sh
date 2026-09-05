#!/usr/bin/env bash
# deploy/cutover.sh — E4: move the REAL database into production. Only run
# this after deploy/validate-drain.sh and deploy/validate-backup.sh have
# both passed against a disposable copy — see deploy/README.md.
#
# Fixed order, do not reorder:
#   1. stop the service (nothing may hold the destination open)
#   2. dated pre-cutover snapshot of the source, kept until Phase 2
#   3. remove leftover -wal/-shm from the disposable test copy
#   4. move the real database into place, fix ownership/permissions
#   5. verify the moved file (integrity_check + row count vs. the snapshot);
#      abort and restore the snapshot if either disagrees
#   6. start the service again
#
#   sudo bash deploy/cutover.sh <path-to-real-alertavida.db>
#
set -euo pipefail

REAL_DB="${1:?usage: cutover.sh <path-to-real-alertavida.db>}"

SERVICE_USER=alertavida
SERVICE_GROUP=alertavida
LIVE_DB=/var/lib/alertavida/alertavida.db
SNAPSHOT_DIR=/var/backups/alertavida
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [ ! -f "$REAL_DB" ]; then
    echo "Real database not found at $REAL_DB" >&2
    exit 1
fi

if [ -f "${REAL_DB}-wal" ] || [ -f "${REAL_DB}-shm" ]; then
    echo "Refusing to move: $REAL_DB has -wal/-shm siblings, meaning it may" >&2
    echo "have uncommitted frames. With nothing else connected to it, run:" >&2
    echo "  python3 -c \"import sqlite3; sqlite3.connect('$REAL_DB').execute('PRAGMA wal_checkpoint(TRUNCATE)')\"" >&2
    echo "then re-run this script." >&2
    exit 1
fi

echo "== 1/6: stopping the service =="
systemctl stop alertavida.service

echo "== 2/6: pre-cutover snapshot (kept until Phase 2 replaces this host) =="
mkdir -p "$SNAPSHOT_DIR"
SNAPSHOT_PATH="$SNAPSHOT_DIR/pre-cutover-$TIMESTAMP.db"
python3 -c "
import sqlite3
src = sqlite3.connect('$REAL_DB')
dst = sqlite3.connect('$SNAPSHOT_PATH')
src.backup(dst)
dst.close()
src.close()
"
chmod 600 "$SNAPSHOT_PATH"
echo "snapshot: $SNAPSHOT_PATH"

echo "== 3/6: removing disposable test copy's -wal/-shm (if present) =="
rm -f "${LIVE_DB}-wal" "${LIVE_DB}-shm"

echo "== 4/6: moving the real database into place =="
mv "$REAL_DB" "$LIVE_DB"
chown "$SERVICE_USER:$SERVICE_GROUP" "$LIVE_DB"
chmod 660 "$LIVE_DB"

echo "== 5/6: verifying the moved database against the snapshot =="
if ! python3 -c "
import sqlite3
import sys

live = sqlite3.connect('$LIVE_DB')
integrity = live.execute('PRAGMA integrity_check').fetchone()[0]
n_live = live.execute('SELECT COUNT(*) FROM alertas').fetchone()[0]
live.close()

snap = sqlite3.connect('$SNAPSHOT_PATH')
n_snap = snap.execute('SELECT COUNT(*) FROM alertas').fetchone()[0]
snap.close()

print(f'integrity_check: {integrity}')
print(f'alertas: moved={n_live} snapshot={n_snap}')

sys.exit(0 if (integrity == 'ok' and n_live == n_snap) else 1)
"; then
    echo "Verification FAILED — restoring from the pre-cutover snapshot and aborting." >&2
    echo "The service is left STOPPED; the moved file was NOT started against." >&2
    # cp, not mv: keep $SNAPSHOT_PATH itself intact as the safety net even
    # after using it to restore — it stays until Phase 2 closes either way.
    cp "$SNAPSHOT_PATH" "$LIVE_DB"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$LIVE_DB"
    chmod 660 "$LIVE_DB"
    exit 1
fi

echo "== 6/6: starting the service against the real database =="
systemctl start alertavida.service
# status is display-only; the real gate is systemctl start's own exit code.
systemctl status alertavida.service --no-pager || true

echo
echo "Cutover complete. Real data now lives at $LIVE_DB."
echo "Pre-cutover snapshot kept at $SNAPSHOT_PATH — do not delete until Phase 2 closes."
echo "=== CUTOVER: ALL CHECKS PASSED ==="
