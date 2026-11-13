#!/usr/bin/env bash
# deploy/upload.sh — off-host copy of the local backups to Google Drive
# (issue #120). Invoked by alertavida-upload.service, once a day.
#
# The local backups in /var/lib/alertavida/backups live on the same disk as
# the database they protect; this is the copy that survives losing the host.
#
# This script NEVER deletes anything, locally or on the remote:
#   - local retention has a single owner, deploy/backup.py
#     (ALERTAVIDA_BACKUP_RETENTION_DAYS, set in alertavida-backup.service);
#   - the remote is append-only (`--immutable` refuses to overwrite a file
#     that already exists there with different content).
#
# The rclone credential lives in /var/lib/alertavida/rclone/rclone.conf,
# created by a one-time manual `rclone config` (see deploy/README.md). It is
# never committed.
set -euo pipefail

export RCLONE_CONFIG=/var/lib/alertavida/rclone/rclone.conf
SRC=/var/lib/alertavida/backups
DST=gdrive:AlertaVida/backups
MARKER=/var/lib/alertavida/last_upload_ok

# 1. Send whatever is not on the remote yet.
rclone copy "$SRC" "$DST" --include "alertavida-*.db" --immutable

# 2. Verify size and hash of every local backup against the remote. A
#    mismatch exits non-zero here (set -e), before the marker is written.
rclone check "$SRC" "$DST" --include "alertavida-*.db" --one-way

# 3. Record the last verified upload.
date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"

echo "=== UPLOAD: ALL CHECKS PASSED — $(cat "$MARKER") ==="
