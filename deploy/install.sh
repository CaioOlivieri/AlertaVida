#!/usr/bin/env bash
# deploy/install.sh — E1: service account, directories, and systemd units.
#
# Does NOT touch any database. Designed to be idempotent — safe to re-run
# — but that claim is only trusted once actually run twice against the same
# target and both outputs inspected, not from reading the script
# (wiki/_schema.md rule 1). Run as root (this script calls no `sudo` itself
# — invoke it with `sudo bash deploy/install.sh ...`):
#
#   sudo bash deploy/install.sh <repo-url-or-local-path> <branch>
#
set -euo pipefail

REPO_SOURCE="${1:?usage: install.sh <repo-url-or-local-path> <branch>}"
BRANCH="${2:?usage: install.sh <repo-url-or-local-path> <branch>}"

SERVICE_USER=alertavida
SERVICE_GROUP=alertavida
APP_DIR=/opt/alertavida
DATA_DIR=/var/lib/alertavida
BACKUP_DIR="$DATA_DIR/backups"
UV_BIN=/usr/local/bin/uv
# Pinned, not "latest" — this is the only place `uv` touches the network as
# root. The version matches what this deploy was built and tested against.
# A full checksum pin would need re-vendoring on every uv bump; a pinned
# version number over HTTPS from astral.sh's own domain is the accepted
# trade-off for a one-time, root-run bootstrap step (recorded in
# wiki/decisions/systemd-vps-deployment.md). Distinct from — and not
# governed by — invariants 24/25, which are about the *application's own*
# HTTP transport (sources/_http.py), not install-time tooling.
UV_VERSION=0.11.15

add_safe_directory() {
    # Avoids git's "detected dubious ownership" refusal, which fires
    # whenever the invoking UID (root, here) differs from a repository
    # path's owning UID — true for $APP_DIR once it belongs to
    # $SERVICE_USER, and true for a local $REPO_SOURCE owned by whichever
    # user is running this install (never root on a dev machine).
    local path="$1"
    if ! git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$path"; then
        git config --global --add safe.directory "$path"
    fi
}

is_local_path() {
    case "$1" in
        http://*|https://*|ssh://*|*@*:*) return 1 ;;
        *) return 0 ;;
    esac
}

echo "== 1/7: system user =="
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "created $SERVICE_USER"
else
    echo "$SERVICE_USER already exists, skipping"
fi

echo "== 2/7: directories =="
mkdir -p "$APP_DIR" "$BACKUP_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR" "$DATA_DIR"
# setgid so files the service creates keep the shared group; group rwx so a
# maintainer added to $SERVICE_GROUP (see README "File permissions") can
# read/write without sudo -u.
chmod 2770 "$DATA_DIR" "$BACKUP_DIR"

echo "== 3/7: git safe.directory (both paths, needed before any git command below) =="
add_safe_directory "$APP_DIR"
if is_local_path "$REPO_SOURCE"; then
    add_safe_directory "$(readlink -f "$REPO_SOURCE")"
fi

echo "== 4/7: uv $UV_VERSION (system-wide, fixed path — install-time only, see UV_VERSION comment above) =="
if [ ! -x "$UV_BIN" ] || [[ "$("$UV_BIN" --version 2>/dev/null)" != "uv $UV_VERSION "* ]]; then
    curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin sh
else
    echo "uv $UV_VERSION already present at $UV_BIN, skipping install"
fi

echo "== 5/7: application code =="
if [ ! -d "$APP_DIR/.git" ]; then
    # --no-hardlinks: a local-path REPO_SOURCE on the same filesystem as
    # $APP_DIR (e.g. testing against a checkout under /var/tmp, or any
    # on-disk clone) makes a plain `git clone` hardlink object files rather
    # than copy them. The chown -R a few lines down then flips ownership of
    # those SHARED inodes, silently reassigning files still living inside
    # REPO_SOURCE's own .git/objects/ to $SERVICE_USER. Harmless (a few
    # extra copied objects) when REPO_SOURCE is a URL, so unconditional.
    git clone --no-hardlinks "$REPO_SOURCE" "$APP_DIR"
else
    git -C "$APP_DIR" fetch "$REPO_SOURCE" "$BRANCH"
fi
git -C "$APP_DIR" checkout "$BRANCH"
git -C "$APP_DIR" pull "$REPO_SOURCE" "$BRANCH" --ff-only

if [ ! -d "$APP_DIR/deploy" ]; then
    echo "The ref '$BRANCH' does not contain deploy/ — the deploy artifacts" >&2
    echo "must be COMMITTED on the ref being installed, not just present in" >&2
    echo "someone's working tree." >&2
    exit 1
fi

# git clone/checkout above ran as root; hand the tree to the service user.
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR"

echo "== 6/7: python dependencies (creates \$APP_DIR/.venv, used directly by ExecStart) =="
runuser -u "$SERVICE_USER" -- env HOME="$APP_DIR" "$UV_BIN" --directory "$APP_DIR" sync --frozen

echo "== 7/7: systemd units =="
cp "$APP_DIR/deploy/alertavida.service" \
   "$APP_DIR/deploy/alertavida-backup.service" \
   "$APP_DIR/deploy/alertavida-backup.timer" \
   /etc/systemd/system/
systemctl daemon-reload

echo
echo "Done. No database has been touched."
echo "Next: seed a disposable test database before starting the service — see deploy/README.md."
