status: implemented
sources: `deploy/`, `src/alertavida/scheduler.py`, issue #78
updated: 2026-09-05

# systemd + VPS deployment, not Docker

Camada 5 v1 shipped (#61) and the scheduler ran, but only from an
interactive terminal on the maintainer's laptop: no `deploy/` directory, no
unit files, no Dockerfile, no operating runbook. WSL does not survive a
reboot, so the collector stopped every time the terminal or the machine did
— confirmed stopped for 8 days (since 2026-08-28T12:50Z) at the time this
issue was picked up. The October–March rainy season is the only window with
real event volume for dormant #63's calibration; a month of downtime during
it cannot be recovered.

**Adopted: a minimal VPS + systemd, unit files versioned in this repo. No
Docker, no PaaS, no orchestrator.** The workload is one process, one SQLite
file, zero exposed ports — `Restart=`, `WantedBy=multi-user.target` and
journald cover restart, boot survival and logs with nothing more than an ini
file. `uv.lock` already gives the reproducibility a container would add, and
a misconfigured bind mount is a new way to lose the database that *is*
#63's dataset. Docker becomes worth it at Camada 6, once FastAPI + Postgres
make this genuinely multi-service.

## Database path moves outside the git checkout

`ALERTAVIDA_DB_PATH` (env-var override on `db_path()`, #22) is set in the
unit file to `/var/lib/alertavida/alertavida.db` — outside `/opt/alertavida`,
the checkout `git pull` operates on. Before #78 the default resolved to
`data/alertavida.db` *inside* the checkout; on a permanent host, a `git
pull` landing on top of that path would be one accidental `.gitignore` edit
away from clobbering the dataset. `deploy/README.md` documents the
migration path via `sqlite3.Connection.backup()` (see below) with a
row-count check before the original file is removed.

## Backup uses the `.backup()` API, not the `sqlite3` CLI

The issue spec called for `sqlite3 ... ".backup ..."` from the CLI. The
`sqlite3` binary is not installed on the environment this was built and
validated against, and is not something the deploy runbook should assume —
so `deploy/backup.py` reimplements the same operation through
`sqlite3.Connection.backup()`, the stdlib API every Python 3 ships with. The
underlying operation is identical: SQLite's online backup, safe against a
concurrent WAL writer. A plain `cp` was never on the table either way — it
can read the main file mid-checkpoint while committed pages still sit in
the `-wal` file, producing an inconsistent copy (see
[[decisions/sqlite-wal-busy-timeout]]). `alertavida-backup.timer` runs
`backup.sh` (a thin wrapper, stable `ExecStart=` target) daily, with a
10-minute `RandomizedDelaySec` and N-day retention (`ALERTAVIDA_BACKUP_DIR`,
default 30 days).

## Signal handling: option (c) — both signals, plus a real drain

`systemctl stop`/`restart` sends SIGTERM by default. `scheduler.py`'s only
graceful-shutdown path was `try/except (KeyboardInterrupt, SystemExit)`
around `scheduler.start()` (issue #21) — SIGTERM raises neither in Python,
so the process would die by the OS's default disposition and
`scheduler.shutdown()` would never run. This matters because of
[[decisions/incident-lifecycle-wiring]]: persistence commits before
correlation runs, in a separate transaction. A process killed between them
leaves an alert durably `CRIADO` with no `incidente_membros` row, and the
next round classifies it INALTERADO — it is never correlated, permanently.
Every `systemctl restart` during a deploy was a chance to hit that window.

Three options were on the table (issue #78's design point):

- **(a) `KillSignal=SIGINT` only** — zero code change, routes systemd's stop
  through the existing handler. But today's `shutdown(wait=False)` doesn't
  wait for a running job regardless of which signal triggers it — it stops
  the scheduler from starting new work and returns immediately, so the
  window stays open.
- **(b) a real SIGTERM handler only** — explicit, but the same
  `wait=False` limitation applies: catching the signal without waiting
  just formalizes the race instead of closing it.
- **(c) both, plus `TimeoutStopSec=` and `shutdown(wait=True)`** — chosen.

**Decided: (c).** `alertavida.service` sets `KillSignal=SIGINT`, so
`systemctl stop`/`restart` routes through the pre-existing
`except (KeyboardInterrupt, SystemExit)` branch. `scheduler.py` additionally
registers a `signal.signal(signal.SIGTERM, ...)` handler as a second line of
defense — for anything that sends SIGTERM directly, bypassing the unit's
`KillSignal` (a bare `kill`, a future process supervisor, a systemd
`KillMode` edge case). Both paths now call `scheduler.shutdown(wait=True)`
instead of the original `wait=False` — the change that actually closes the
window, since `wait=True` blocks until the executor's in-flight job
(running on its own worker thread, not the thread handling the signal)
finishes before `start()` returns.

`TimeoutStopSec=360` in the unit gives that wait room to complete before
systemd escalates to SIGKILL. Sized from the worst case for one ingestion
round: two sources run sequentially
(`src/alertavida/ingestion/orquestrador.py`), each retrying up to
`MAX_TENTATIVAS=4` times at `TIMEOUT_SEGUNDOS=30` with `2s+4s+8s` backoff
between attempts (`src/alertavida/sources/_http.py`) —
`4 × 30 + 14 = 134s` per source, `268s` for both, plus margin.

**Consequence for #87 (orphan alert on restart):** this closes the
graceful-restart path entirely — the dominant case (`systemctl
stop`/`restart`) can no longer produce the orphaned-alert window described
in [[decisions/incident-lifecycle-wiring]]'s "Correlation failure is
permanent" section. What #87 still needs to cover after this: SIGKILL
(OOM, `systemctl kill -s KILL`, a VM host outage) and any crash inside
`_correlacionar_rodada` itself, neither of which a stop-signal change can
fix. #87's scope narrows to those, and should be re-scoped explicitly on
whichever issue actually starts that work.

## `ExecStart` runs the venv's interpreter directly, not `uv run`

First draft used `ExecStart=/usr/local/bin/uv run --frozen python -m
alertavida.scheduler`. Caught in review, then reproduced directly: with
`ProtectSystem=strict` (making `/opt/alertavida` — and therefore
`HOME=/opt/alertavida` — read-only), `uv run` fails even with a fully
populated cache, because it still opens `.git` metadata under its cache
directory:

```
error: Failed to initialize cache at .../.cache/uv
Caused by: failed to open .../sdists-v9/.git: Permission denied
```

Confirmed the isolation: writable `HOME` → cache populates fine; read-only
`HOME` → same failure; invoking `/opt/alertavida/.venv/bin/python` directly
with a read-only `HOME` → works. **Decided: `ExecStart` (both
`alertavida.service` and `backup.sh`) calls the venv's own interpreter
directly.** `uv` only runs at install time (`deploy/install.sh`'s `uv sync
--frozen`, which creates `.venv`); the running service never invokes it
again. Rejected loosening `ProtectSystem` or adding the `uv` cache to
`ReadWritePaths` — that would widen the sandbox to accommodate a tool the
runtime doesn't actually need.

`deploy/install.sh` also pins `uv` to a specific version
(`https://astral.sh/uv/<version>/install.sh`, not the mutable `.../
install.sh` "latest" endpoint) instead of trusting whatever `uv` happens to
publish as current on install day — the only place this deploy pulls
unpinned code from the network as root. A full checksum pin was considered
and rejected: it would need re-vendoring on every `uv` bump for a tool that
only ever runs once, at install time, as part of a manual, human-triggered
step — the version pin over HTTPS from `astral.sh`'s own domain is judged
sufficient for that risk profile. Distinct from — and not governed by —
invariants 24/25, which constrain the *application's own* HTTP transport
(`sources/_http.py`) at runtime, not this install-time bootstrap.

## Hygiene: database file permissions, and maintenance access

`UMask=0007` on both units — the SQLite file (and its `-wal`/`-shm`
siblings) are created `0660` (owner + group read/write), not the `0644` a
bare `umask 022` produces (the default the file has under interactive
development use today, world-readable). No security impact on a
single-user machine; on a shared permanent host it is the difference
between readable-by-anyone-with-a-shell and readable-only-by-`alertavida`
and its group.

`0007`, not `0077`: the maintainer's own user still needs read/write access
after cutover — `scripts/reclassificar_escopos.py` and #89's `EXPLAIN QUERY
PLAN` work both open the database directly, outside the service. **Decided:
add the maintainer's user as a supplementary member of the `alertavida`
group** (`sudo usermod -aG alertavida <user>`, new shell session or
`sg alertavida -c '...'` to pick it up immediately) rather than requiring
`sudo -u alertavida ...` for every maintenance script. Rejected `0077` +
always-`sudo -u alertavida`: correct on a locked-down multi-admin host, but
this is a single-maintainer machine where routine read/write access to the
project's own dataset is the common case, not the exception — the group
membership route is documented in `deploy/README.md` alongside the `sudo -u
alertavida` alternative for hosts where adding a login to the group is
undesirable.

## Validation is staged and self-verifying, not a single script

Run locally on the maintainer's WSL (which does have a working systemd —
`systemctl is-system-running` returns `running`). Split into ordered,
independently-authorized stages rather than one script, so a real `sudo`
run only ever executes something already reviewed line by line:

- `deploy/install.sh` (E1) — account, directories, units. Touches no
  database. Idempotent by construction (`git config --add safe.directory`
  for both the destination and, when local, the source — see next section
  — plus a version-checked `uv` install guard), proven by actually running
  it twice, not by inspection.
- `deploy/seed-test-db.sh` + `deploy/validate-drain.sh` (E2) — a
  **disposable** `.backup()` copy at the live path, then the restart/drain
  test. `validate-drain.sh` does not accept "the log line appeared" as
  proof — `scheduler.py`'s drain message logs unconditionally whether or
  not a round is actually in flight when the signal arrives, so the script
  asserts a strict line-order (`Iniciando rodada` → `aguardando rodada em
  andamento encerrar...` → `Rodada concluída` → a fresh `Scheduler
  iniciado.`, all after the moment the restart was issued) and retries
  (up to 5×) when a round finishes too fast to catch mid-flight, rather
  than passing on an inconclusive race.
- `deploy/validate-backup.sh` (E3) — proves backup/restore *before* the
  real dataset ever depends on it. Stops the service for the duration of
  the check (a round landing mid-comparison would insert rows and produce
  a spurious mismatch against the already-taken backup), runs the backup
  unit, restores into a third scratch path, `PRAGMA integrity_check`, row
  counts against the live copy — then restarts the service if it was
  running before.
- `deploy/cutover.sh` (E4) — only once E2 and E3 both pass. Fixed order:
  stop → dated pre-cutover snapshot (`/var/backups/alertavida/`, outside
  both the checkout and `/var/lib/alertavida`, kept until Phase 2 closes)
  → clear the disposable copy's `-wal`/`-shm` → move the real file → fix
  ownership → **verify the moved file against the snapshot**
  (`integrity_check` + alert count) before ever starting the service on
  it, aborting and restoring from the snapshot if either check disagrees →
  start. Refuses outright if the *source* database itself has `-wal`/`-shm`
  siblings (uncheckpointed frames).
- `deploy/uninstall.sh` — the reverse of E1. Never removes
  `/var/lib/alertavida` (the live database) without `--purge-data`, and
  even then refuses without a snapshot newer than 7 days in
  `/var/backups/alertavida/` plus a typed confirmation — a decommission
  script that can delete the project's only dataset needs more friction
  than a single flag.

Real `systemctl status` and `journalctl` output from all of this is pasted
into the PR that closes #78, per `_schema.md` rule 1 — nothing here is
asserted from reading the scripts alone. The permanent host (a VPS that
survives reboots) is explicitly out of scope for this pass — issue #78's
Phase 2, deferred to September 2026.

## `git safe.directory`, needed twice

`deploy/install.sh` runs `git clone`/`fetch`/`checkout`/`pull` as root
(simplest way to read a source path root wouldn't otherwise have access
to), then hands the tree to `alertavida` via `chown -R`. Git's "detected
dubious ownership" guard fires whenever the invoking UID differs from a
repository path's owning UID — true in **two** places here: reading a
locally-owned `REPO_SOURCE` as root (this WSL validation clones from the
maintainer's own checkout, not GitHub), and — the one that actually breaks
re-running the script — `git -C /opt/alertavida fetch ...` as root on a
second run, after the first run's `chown` made that tree
`alertavida`-owned. `install.sh` registers `safe.directory` (in root's own
git config) for both paths before any git command touches them, and the
idempotency claim in the script's header comment is only trusted once
proven by running it twice against the same target, not by reading it.
