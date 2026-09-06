# Deploying AlertaVida

Minimal VPS + systemd. No Docker, no PaaS, no orchestrator — see
[[decisions/systemd-vps-deployment]] for why. One process, one SQLite file,
zero exposed ports.

## Provision (manual, cannot be automated from here)

- A small VPS (1 vCPU / 512MB–1GB RAM is enough), Debian/Ubuntu-family.
- SSH key access; disable password auth.
- Firewall: SSH only. Nothing else listens until Camada 6 (FastAPI).

## One-time setup

`deploy/install.sh` does steps 1–5 below. It never touches any database,
and it should never touch anything outside `/opt/alertavida`,
`/var/lib/alertavida`, `/etc/systemd/system`, and `/usr/local/bin` (where
`uv` is installed) — including the *source* repository it clones from, if
that source is a local path rather than a URL. Any change outside that set
(caught once already: an unqualified `git clone` from a same-filesystem
local path hardlinks objects, so the subsequent `chown -R` on the clone
silently reassigned ownership of files still shared with the source
checkout — fixed with `--no-hardlinks`) is a bug in this script, not
expected behavior. Review it before running:

```bash
sudo bash deploy/install.sh <repo-url-or-local-path> <branch>
# e.g. sudo bash deploy/install.sh https://github.com/CaioOlivieri/AlertaVida.git main
```

What it does:

1. Creates the dedicated `alertavida` system user (no login shell, no home
   directory of its own beyond `/opt/alertavida`).
2. Creates `/opt/alertavida` (the git checkout — code only) and
   `/var/lib/alertavida` (persistent data, **outside** the checkout so a
   `git pull` can never touch it), with the group-shared permissions
   described in "File permissions" below.
3. Installs a pinned `uv` version system-wide to `/usr/local/bin` (fixed
   version, fixed path — systemd units have no shell profile to resolve
   `PATH` or "latest" from). `uv` is used only here and in the "Update
   cycle" below; the running service invokes the venv's own interpreter
   directly (see [[decisions/systemd-vps-deployment]] — `uv run` fails
   under this unit's `ProtectSystem=strict`).
4. Clones the given ref into `/opt/alertavida` and runs `uv sync --frozen`
   as the `alertavida` user, creating `/opt/alertavida/.venv`.
5. Copies the three unit files into `/etc/systemd/system/` and runs
   `systemctl daemon-reload`.

Then start it:

```bash
systemctl enable --now alertavida.service
systemctl status alertavida.service
journalctl -u alertavida -f
```

Note: this does **not** arm `alertavida-backup.timer` — there is no database
to back up yet at this point (`deploy/backup.sh` exits 1 against an empty
`/var/lib/alertavida`). `deploy/cutover.sh` arms the timer once the real
database is in place; see "Migrating an existing database" below.

`deploy/uninstall.sh` reverses steps 1, 3 and 5. It never touches step 2's
`/var/lib/alertavida` (the live database) unless you pass `--purge-data` —
and even then it refuses without a snapshot newer than 7 days in
`/var/backups/alertavida/` and a typed confirmation.

## Migrating an existing database

If a database already exists inside a git checkout (e.g. from running the
scheduler manually during development), it needs to move to
`/var/lib/alertavida/alertavida.db` — **never `cp` a database that might be
in WAL mode**; a raw copy can read the main file mid-checkpoint while
committed pages still sit in the `-wal` file. `deploy/cutover.sh` does this
safely, in a fixed order that must not be reordered:

```bash
sudo bash deploy/cutover.sh <path-to-existing-alertavida.db>
```

1. **Stops the service first** — nothing may hold the destination path open
   while it changes underneath.
2. Takes a dated, `.backup()`-safe snapshot into `/var/backups/alertavida/`
   (outside both the checkout and `/var/lib/alertavida`) — kept until the
   permanent host (Phase 2) replaces this one; not subject to the daily
   backup timer's retention pruning.
3. Removes any leftover `-wal`/`-shm` files at the destination (from a
   prior test database) — a stale WAL next to a freshly moved main file is
   exactly the inconsistency this whole approach avoids.
4. Moves the real database into place, fixes ownership/permissions.
5. Verifies the moved file (`integrity_check` + row count vs. the snapshot);
   aborts and restores the snapshot if either disagrees.
6. Starts the service again and arms `alertavida-backup.timer`. This is the
   first point a real database exists to back up — `deploy/install.sh` can't
   arm it earlier (`deploy/backup.sh` exits 1 against an empty database),
   and a README-only manual step is exactly the failure mode this issue hit
   twice already (once for the install `cp`, once for a validation script
   aborting silently). Confirm it landed:

   ```bash
   systemctl list-timers alertavida-backup.timer
   ```

Refuses to run if the *source* database itself has `-wal`/`-shm` siblings
(checkpoint it first with nothing else connected).

**Validate before, not after**: run `deploy/validate-drain.sh` and
`deploy/validate-backup.sh` against a disposable copy of the database
*before* running `cutover.sh` against the real one. See "Validation" below.

## Update cycle

```bash
cd /opt/alertavida
sudo -u alertavida git pull
sudo -u alertavida /usr/local/bin/uv sync --frozen
systemctl restart alertavida.service
```

`systemctl restart` sends `KillSignal=SIGINT` (not the systemd default
SIGTERM) — see [[decisions/systemd-vps-deployment]] for why this matters:
without it, a restart mid-round could permanently orphan an alert from any
Incidente ([[decisions/incident-lifecycle-wiring]]). `TimeoutStopSec=360`
gives an in-flight round room to actually finish before systemd escalates
to SIGKILL.

## When it stops and stays stopped: `start request repeated too quickly`

`alertavida.service` caps restarts at `StartLimitBurst=5` per
`StartLimitIntervalSec=300`, so a persistent failure — a database
permission problem, a missing `.venv`, a half-finished `uv sync` — stops
retrying instead of logging ~8,640 attempts a day. The trade-off is that
**systemd will not bring the service back on its own**, and it goes quiet
rather than noisy. `systemctl status alertavida.service` then shows:

```
Failed to start alertavida.service: start request repeated too quickly
```

That message is the rate limiter tripping, not the actual fault. The real
cause is the *first* failure in the burst:

```bash
journalctl -u alertavida --since "1 hour ago" | head -50
```

Fix that cause first. Then the failed state must be cleared explicitly —
`systemctl start` alone keeps refusing until it is:

```bash
systemctl reset-failed alertavida.service
systemctl start alertavida.service
systemctl status alertavida.service
```

`systemctl is-active` reporting `failed` (rather than `inactive`) is the
signal to look for this specifically — see the stopgap check below.

## Backups

`alertavida-backup.timer` runs `deploy/backup.sh` once a day (plus up to a
10-minute random delay). It writes a timestamped, WAL-safe copy to
`/var/lib/alertavida/backups/` and prunes copies older than
`ALERTAVIDA_BACKUP_RETENTION_DAYS` (default 30).

Check backups landed:

```bash
systemctl list-timers alertavida-backup.timer
ls -la /var/lib/alertavida/backups/
```

`deploy/validate-backup.sh` automates the full check: runs the backup unit
once, restores the newest file into a third scratch path, runs `PRAGMA
integrity_check`, and compares row counts against the live database.

## WeatherNext surge watch (issue #70)

Two independent jobs support the Round 2 centroide-vs-risco discriminator
([[projects/layer-5-correlation]]): a daily forecast check
(`scripts/weathernext_surge_watch.py`) and a high-frequency raw CEMADEN
capture gated on it (`scripts/weathernext_cemaden_capture.py`). Design
recorded in [[decisions/weathernext-surge-watch-design]].

**Not installed by `deploy/install.sh` and does not run as `alertavida`.**
Both scripts need the BigQuery `bq` CLI authenticated with the maintainer's
own Google credentials (Application Default Credentials under
`~/.config/gcloud/`) — the `alertavida` service account has no reason to
read those and no login shell to run `bq` interactively even if it did. They
run as **user systemd units** (`systemctl --user`), installed under your own
`~/.config/systemd/user/`, no root needed to install or enable:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/weathernext-surge-watch.service deploy/weathernext-surge-watch.timer \
   deploy/weathernext-cemaden-capture.service deploy/weathernext-cemaden-capture.timer \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now weathernext-surge-watch.timer
systemctl --user enable --now weathernext-cemaden-capture.timer
```

**User units only run while you have an active session, unless lingering is
enabled** — without it, both timers stop the moment you log out. Enable it
once (needs root, one time only):

```bash
sudo loginctl enable-linger "$USER"
```

This host is WSL — same caveat as ["This deployment is a stopgap on
WSL"](#this-deployment-is-a-stopgap-on-wsl-not-the-permanent-host) below:
lingering keeps the units running across logout, but **not** across a
Windows reboot or WSL shutdown. If the rainy season needs this covered
through a Windows restart, that is the same Phase 2 (always-on host) gap
already tracked there — nothing new introduced by this issue.

Verify:

```bash
systemctl --user list-timers 'weathernext-*'
cat data/weathernext_surge_watch.json   # generated after the first run
ls data/weathernext_cemaden_captures/   # populated only once watch_mode is true
```

`data/` here is the git checkout's own `data/` (gitignored) — not
`/var/lib/alertavida` — because these jobs run as the maintainer, not
`alertavida` (see the decision page for why).

## File permissions

The SQLite file is created with the process's `UMask=0007` (both units) —
new files are `0660` (owner + group read/write), not the `0644` a bare
`umask 022` produces (the file's actual mode under interactive development
use today, world-readable). `/var/lib/alertavida` itself is `2770`
(setgid, so new files inherit the group) owned by `alertavida:alertavida`.

That leaves routine maintenance — `scripts/reclassificar_escopos.py`,
copying the database for `EXPLAIN QUERY PLAN` work (#89) — needing access
too. Two options, pick the one that matches the host:

- **Shared group** — **not verified** against a real second user on this
  install (the maintainer is not currently a member). Requires adding your
  login to the `alertavida` group — `sudo usermod -aG alertavida
  <your-username>` — **and starting a new login session** (a plain `sudo
  usermod` does not take effect in an already-open shell; `sg alertavida -c
  '<command>'` picks it up immediately without logging out). Once active,
  your user can read and write the database directly, no `sudo` needed.
- **`sudo -u alertavida` per command** (verified below), no group change —
  run against `/opt/alertavida`, not a personal checkout: `alertavida` has
  no login shell, and the maintainer's own home directory is typically not
  traversable by other users (`drwxr-x---`), so `sudo -u alertavida` cannot
  reach a script under a personal checkout regardless. Under `sudo -u
  alertavida`, `HOME` resolves to `/opt/alertavida` itself, which **is**
  writable by that user — unlike the systemd unit, where
  `ProtectSystem=strict` makes `/opt` read-only (see
  [[decisions/systemd-vps-deployment]]) and is why `ExecStart=` cannot use
  `uv run` there. See "The `ALERTAVIDA_DB_PATH` trap" below for the exact
  command.

### The `ALERTAVIDA_DB_PATH` trap

`db_path()` (`src/alertavida/database.py`) resolves from `ALERTAVIDA_DB_PATH`,
falling back to `data/alertavida.db` **relative to the checkout** when the
variable is unset. The unit file sets it to
`/var/lib/alertavida/alertavida.db` — but a plain shell in a checkout does
not inherit that. Running `python -m alertavida.monitor` or
`scripts/reclassificar_escopos.py` from there without the variable set
**silently creates a new, empty database in `data/`** instead of touching
production — no error, no warning.

Three more things compound this for the `sudo -u alertavida` path
specifically, each verified against this install:

- `sudo -u alertavida VAR=value cmd` is rejected by Ubuntu's default
  `env_reset` — use `sudo -u alertavida env VAR=value cmd` instead, the same
  pattern `deploy/install.sh` already uses for `runuser`.
- `uv` itself needs a writable `HOME` to run at all — that's why it fails
  under the unit (`ProtectSystem=strict` makes `/opt` read-only there) but
  works fine under `sudo -u alertavida`, where `HOME` resolves to the
  writable `/opt/alertavida` (verified by the `uv sync --frozen` in "Update
  cycle" above). The command below still calls the venv's own interpreter
  directly (`/opt/alertavida/.venv/bin/python`) rather than `uv run`, since
  it needs no `HOME` at all to import the package.
- Paths must be absolute and under `/opt/alertavida` — not a relative
  script path, which resolves against whatever directory the caller
  happened to be in (`sudo` does not change cwd), and not a personal
  checkout path, per the traversal problem above.

Verified end to end on this install:

```bash
sudo -u alertavida env ALERTAVIDA_DB_PATH=/var/lib/alertavida/alertavida.db \
  /opt/alertavida/.venv/bin/python -c "from alertavida.database import db_path; print(db_path())"
# -> /var/lib/alertavida/alertavida.db

sudo -u alertavida env ALERTAVIDA_DB_PATH=/var/lib/alertavida/alertavida.db \
  /opt/alertavida/.venv/bin/python /opt/alertavida/scripts/reclassificar_escopos.py
```

## This deployment is a stopgap on WSL, not the permanent host

WSL does not survive a Windows reboot or sleep/suspend — `agendar_ingestao`
resuming here closes the collection gap *today*, but it is not what issue
#78 originally specified as the target host. **Phase 2 — a VPS that stays
up through reboots — remains necessary** and is deferred to a separate
session in September 2026, ahead of the October–March rainy season. Running
this install script on the real VPS when that session starts is the same
`deploy/install.sh` used here.

Check whether it's still collecting:

```bash
systemctl is-active alertavida.service
journalctl -u alertavida --since "10 minutes ago" | grep "Rodada concluída"
```

If `systemctl is-active` prints anything other than `active`, or the
`journalctl` line above finds nothing in the last ~10 minutes (rounds run
every 5), collection has stopped — check `systemctl status alertavida.service`
for why, and whether the WSL instance itself is still running at all.

## Validation

Run in this exact order against a **disposable** copy of the database
before ever pointing the service at the real one:

1. `deploy/install.sh` — sets up the user, directories and units. No
   database touched. Idempotent — prove it by running it twice.
2. `deploy/seed-test-db.sh <path-to-any-db>` — puts a **disposable**
   `.backup()` copy at the live path
   (`/var/lib/alertavida/alertavida.db`), then `deploy/validate-drain.sh` —
   starts the service, waits for a round to begin, restarts mid-round, and
   asserts the strict order `Iniciando rodada` → `aguardando rodada em
   andamento encerrar...` → `Rodada concluída` → a fresh `Scheduler
   iniciado.`, retrying (up to 5×) if a round finishes before the restart
   lands rather than accepting an inconclusive race as a pass. Normally
   takes seconds; if the service hangs it waits up to 5 × 370s ≈ 31 min
   before reporting FAILED — that is the script working, not hanging.
3. `deploy/validate-backup.sh` — proves the backup/restore path is sound
   *before* trusting it with the real dataset: stops the service (so the
   comparison isn't racing a live round), runs the backup unit, restores
   into a third path, `PRAGMA integrity_check`, row-count comparison
   against the source, restarts the service afterward.
4. Only once 2 and 3 both pass: `deploy/cutover.sh` against the real
   database.

Real `systemctl status` and `journalctl` output from all of this is pasted
into the PR that closes #78, per `wiki/_schema.md` rule 1 (assert only what
was actually run, never inferred).
