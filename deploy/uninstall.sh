#!/usr/bin/env bash
# deploy/uninstall.sh — reverses install.sh. By default leaves
# /var/lib/alertavida (the live database) and the alertavida user alone;
# pass --purge-data to also remove the data directory and the user — that
# requires a recent snapshot in /var/backups/alertavida (refuses otherwise)
# and a typed confirmation. Run with:
#
#   sudo bash deploy/uninstall.sh [--purge-data]
#
set -euo pipefail

PURGE_DATA=false
if [ "${1:-}" = "--purge-data" ]; then
    PURGE_DATA=true
fi

SERVICE_USER=alertavida
APP_DIR=/opt/alertavida
DATA_DIR=/var/lib/alertavida
SNAPSHOT_DIR=/var/backups/alertavida
CONFIRMATION_TEXT="DELETE ALERTAVIDA DATA"

echo "== stopping and disabling units =="
systemctl disable --now alertavida.service alertavida-backup.timer 2>/dev/null || true

echo "== removing unit files =="
rm -f /etc/systemd/system/alertavida.service \
      /etc/systemd/system/alertavida-backup.service \
      /etc/systemd/system/alertavida-backup.timer
systemctl daemon-reload

echo "== removing application code ($APP_DIR) =="
rm -rf "$APP_DIR"

if [ "$PURGE_DATA" = true ]; then
    RECENT_SNAPSHOT="$(find "$SNAPSHOT_DIR" -name '*.db' -mtime -7 2>/dev/null | head -n1)"
    if [ -z "$RECENT_SNAPSHOT" ]; then
        echo "Refusing --purge-data: no snapshot newer than 7 days found in $SNAPSHOT_DIR." >&2
        echo "Take one first (deploy/cutover.sh writes one automatically) before" >&2
        echo "deleting the live database." >&2
        exit 1
    fi

    echo "This PERMANENTLY DELETES the live database at $DATA_DIR."
    echo "Recent snapshot found: $RECENT_SNAPSHOT"
    read -r -p "Type '$CONFIRMATION_TEXT' to confirm: " TYPED
    if [ "$TYPED" != "$CONFIRMATION_TEXT" ]; then
        echo "Confirmation text did not match — aborting, nothing in $DATA_DIR removed." >&2
        exit 1
    fi

    echo "== --purge-data confirmed: removing $DATA_DIR =="
    rm -rf "$DATA_DIR"
    echo "== removing system user $SERVICE_USER =="
    userdel "$SERVICE_USER" 2>/dev/null || true
else
    echo "== leaving $DATA_DIR and the $SERVICE_USER user in place =="
    echo "   (pass --purge-data to also remove them)"
fi

echo "Done."
