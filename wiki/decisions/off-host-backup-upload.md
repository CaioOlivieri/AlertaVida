status: implemented
sources: `deploy/upload.sh`, `deploy/alertavida-upload.{service,timer}`, `deploy/backup.py`, issue #120, PR #122
updated: 2026-11-14

# Off-host backup copy: daily `rclone` upload to Google Drive

[[decisions/systemd-vps-deployment]] (#78) gave the collector a daily,
WAL-safe local backup in `/var/lib/alertavida/backups/`. Those copies sit on
the same disk — inside the same WSL virtual disk — as the database they
protect. Losing the host (a broken WSL install, a Windows reinstall, a dead
SSD) would take the database and every backup with it. The corpus that
dormant #63 is waiting for cannot be re-collected.

**Adopted: a daily `rclone` upload of the local backups to a Google Drive
folder (`gdrive:AlertaVida/backups`), run by a system unit as the
`alertavida` user.**

## History: installed by hand first, versioned later

The upload was installed directly on the host on 2026-10-14/15, with no
commit, issue or wiki page. The 2026-11-13 maintainability audit found it by
comparing `/etc/systemd/system/` against `deploy/`. #120 brought it into the
repository; until then `deploy/install.sh` could not recreate it and nothing
recorded how it was built.

Lesson worth keeping: **a change made directly on the host is invisible to
the next person who reads the repository** — including the maintainer after
a break. The handoff's "what is running" table was wrong for a month because
of it.

## Local retention has exactly one owner

The hand-installed script ran `find ... -mtime +7 -delete` after each
verified upload. `alertavida-backup.service` declares
`ALERTAVIDA_BACKUP_RETENTION_DAYS=30`, and a drop-in repeated the same 30 —
but the upload script's 7 always won, because it ran after the backup.
Evidence: on 2026-11-13 `backups/` held nothing older than 2026-11-06.

**Maintainer decision (2026-11-13): 30 days.** `deploy/upload.sh` no longer
deletes anything. Local pruning belongs to `deploy/backup.py` alone; the
redundant drop-in was removed. Two knobs controlling the same number was
the bug, not the value 7.

## The remote is append-only, by choice

`rclone copy --immutable` refuses to overwrite a remote file that already
exists with different content, and nothing prunes the Drive folder. It grows
by one backup a day (~3.6 MB as of 2026-11-14) with no cap. At that rate a
year is ~1.3 GB, well inside a free Drive quota. Revisit when the database
grows by an order of magnitude (a larger source like INMET/INPE, or Camada
6), not before.

## Order inside the script

1. `rclone copy --immutable` — send what the remote does not have yet.
2. `rclone check --one-way` — size and hash of every local backup against
   the remote. A mismatch exits non-zero (`set -e`).
3. Only then write the UTC time to `/var/lib/alertavida/last_upload_ok`.
4. Print `=== UPLOAD: ALL CHECKS PASSED ===` as the last line — the #78
   lesson: the absence of an explicit success line is the failure signal.

## Script lives in the checkout, not in `/usr/local/sbin`

The hand-installed unit ran `/usr/local/sbin/alertavida-upload.sh`, a copy
outside the checkout. The versioned unit runs
`/opt/alertavida/deploy/upload.sh` — the same shape as
`alertavida-backup.service` → `deploy/backup.sh` — so the script ships with
`git pull` and can never drift from the repository.

## The credential

`/var/lib/alertavida/rclone/rclone.conf` holds an OAuth refresh token for
the maintainer's Google account. It is created by a one-time manual
`rclone config` (runbook in `deploy/README.md`), is mode `0700` owned by
`alertavida`, and is never committed.

## Verified (2026-11-14, after redeploying PR #122)

- `/opt/alertavida` at `0df7d68`, same as `origin/main`.
- `diff` between `deploy/` and `/etc/systemd/system/` for all five units:
  empty. The drop-in and `/usr/local/sbin/alertavida-upload.sh`: gone.
- `systemctl show alertavida-backup.service`:
  `ALERTAVIDA_BACKUP_RETENTION_DAYS=30`, from the unit itself.
- A manual `alertavida-upload.service` run ended with `0 differences
  found`, `6 matching files` and
  `=== UPLOAD: ALL CHECKS PASSED — 2026-11-14T13:50:43Z ===`.
- No local backup was removed by that run (oldest kept: 2026-11-06).

## Open, not decided here

- **OAuth scope.** Whether the `gdrive` remote uses `scope = drive.file`
  (only files rclone created) or `drive` (the whole Drive) was not checked.
  `drive.file` is preferable; changing it needs a new `rclone config`.
- **Restore has never been exercised** from the Drive. The runbook
  documents the path; a drill would turn it into verified behavior.
