#!/usr/bin/env bash
# Thin wrapper so alertavida-backup.service has a stable ExecStart= path.
# The actual backup logic lives in backup.py — it uses sqlite3.Connection's
# .backup() API (WAL-safe), not the sqlite3 CLI, since that binary is not
# assumed to be present on the deploy target. See backup.py's module
# docstring for why a plain `cp` would be unsafe here.
#
# Runs the venv's own interpreter directly, not `uv run` — same reason as
# alertavida.service's ExecStart: ProtectSystem=strict makes /opt/alertavida
# read-only, and `uv run` needs a writable HOME even with a fully populated
# cache. `uv` is install-time only.
set -euo pipefail

exec /opt/alertavida/.venv/bin/python /opt/alertavida/deploy/backup.py
