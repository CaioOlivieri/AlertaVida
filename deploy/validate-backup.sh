#!/usr/bin/env bash
# deploy/validate-backup.sh — E3: proves the backup/restore path is sound
# BEFORE the real database ever depends on it. Stops the service first so
# the live database is a fixed point during the comparison — otherwise a
# round landing mid-check inserts rows and produces a spurious mismatch.
# Restarts the service afterward if it was running. Run with:
#
#   sudo bash deploy/validate-backup.sh [scratch-dir]
#
set -euo pipefail

SCRATCH_DIR="${1:-/tmp/alertavida-backup-validation}"
LIVE_DB=/var/lib/alertavida/alertavida.db
BACKUP_DIR=/var/lib/alertavida/backups

mkdir -p "$SCRATCH_DIR"

WAS_ACTIVE=false
if systemctl is-active --quiet alertavida.service; then
    WAS_ACTIVE=true
fi

restore_service_state() {
    if [ "$WAS_ACTIVE" = true ]; then
        echo "== Restarting the service (it was running before this check) =="
        systemctl start alertavida.service
    fi
}
trap restore_service_state EXIT

if [ "$WAS_ACTIVE" = true ]; then
    echo "== Stopping the service so the live DB is static during this check =="
    systemctl stop alertavida.service
fi

echo "== Running the backup unit once =="
systemctl start alertavida-backup.service
# Type=oneshot: the start above already blocks until the unit finishes and
# gates on its exit code. status is display-only — an already-finished
# oneshot unit reports inactive/dead (exit 3), which must not abort us.
systemctl status alertavida-backup.service --no-pager || true

NEWEST_BACKUP=""
for f in "$BACKUP_DIR"/alertavida-*.db; do
    [ -e "$f" ] || continue
    if [ -z "$NEWEST_BACKUP" ] || [ "$f" -nt "$NEWEST_BACKUP" ]; then
        NEWEST_BACKUP="$f"
    fi
done
if [ -z "$NEWEST_BACKUP" ]; then
    echo "No backup file found in $BACKUP_DIR" >&2
    exit 1
fi
echo "Newest backup: $NEWEST_BACKUP"

RESTORED="$SCRATCH_DIR/restored-$(date -u +%Y%m%dT%H%M%SZ).db"
cp "$NEWEST_BACKUP" "$RESTORED"

echo "== Integrity check + row-count comparison (service stopped, live DB static) =="
python3 -c "
import sqlite3

restored = sqlite3.connect('$RESTORED')
integrity = restored.execute('PRAGMA integrity_check').fetchone()[0]
print(f'PRAGMA integrity_check ({\"$RESTORED\"}): {integrity}')

live = sqlite3.connect('$LIVE_DB')
mismatches = []
for table in ('alertas', 'eventos', 'incidentes'):
    n_live = live.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    n_restored = restored.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    status = 'OK' if n_live == n_restored else 'MISMATCH'
    if n_live != n_restored:
        mismatches.append(table)
    print(f'{table}: live={n_live} restored={n_restored} [{status}]')

restored.close()
live.close()

if integrity != 'ok':
    raise SystemExit('integrity_check did not return ok')
if mismatches:
    raise SystemExit(f'row count mismatch in: {mismatches}')
"

echo
echo "Restored copy kept at $RESTORED for inspection — delete manually when done."
echo "=== VALIDATE-BACKUP: ALL CHECKS PASSED ==="
