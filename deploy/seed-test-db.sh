#!/usr/bin/env bash
# deploy/seed-test-db.sh — E2 setup: copy an existing database into the
# live path as a DISPOSABLE test copy, via the WAL-safe .backup() API (not
# `cp`). Use this to validate the service and backup timer before ever
# running cutover.sh against a real database. Run with:
#
#   sudo bash deploy/seed-test-db.sh <path-to-source-db>
#
set -euo pipefail

SOURCE_DB="${1:?usage: seed-test-db.sh <path-to-source-db>}"
SERVICE_USER=alertavida
SERVICE_GROUP=alertavida
LIVE_DB=/var/lib/alertavida/alertavida.db

if [ ! -f "$SOURCE_DB" ]; then
    echo "Source database not found at $SOURCE_DB" >&2
    exit 1
fi

echo "== Copying $SOURCE_DB -> $LIVE_DB (disposable test copy) =="
# Paths go in as argv to a quoted heredoc, never pasted into the Python
# source: this runs as root, and a path containing a quote would otherwise
# become code (#133).
python3 - "$SOURCE_DB" "$LIVE_DB" <<'PY'
import sqlite3
import sys

src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
PY
chown "$SERVICE_USER:$SERVICE_GROUP" "$LIVE_DB"
chmod 660 "$LIVE_DB"

echo "Done. $LIVE_DB is a disposable copy — the source at $SOURCE_DB is untouched."
