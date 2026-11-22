status: in-progress
sources: `deploy/azure/create-vm.sh`, `deploy/heartbeat.py`, `deploy/alertavida-heartbeat.{service,timer}`, `deploy/cutover.sh`, `deploy/README.md`, issues #134 and #141
updated: 2026-11-22

# Phase 2: the collector moves to an Azure for Students VM

[[decisions/systemd-vps-deployment]] (#78) ran the collector on WSL as a
stopgap and deferred **Phase 2 — an always-on host** to September 2026. It
did not happen until 2026-11-22.

## Why it could not wait any longer (measured, #134)

- The collector ran **~14 %** of the time after the 2026-11-13 audit
  (completed rounds / possible rounds, journal).
- Not a software fault. The WSL autostart already existed (a hand-installed
  Windows Startup script, 2026-10-14), and Windows never slept on its own.
  The PC was shut down by hand: 43 of 44 shutdown/restart events in 14 days
  came from the Start menu or the logon screen, 1 from Windows Update.
- Leaving the PC on was ruled out by the maintainer: frequent power spikes
  where it lives.

Every hour off during the rainy season is corpus that dormant #63 can never
get back.

## Why Azure for Students

Constraints set by the maintainer (2026-11-16): **no spending, no credit
card.** Options measured:

| Option | Outcome |
|---|---|
| Google Cloud `e2-micro`, Oracle Always Free, AWS free tier | All require a credit card, even at zero cost |
| Brazilian VPS paid by Pix/boleto | Cheapest found R$ 14–21/month (DokeHost, HomeHost); none under R$ 10 |
| Old laptop / Android at home | Free, but still on the house's power and internet |
| **Azure for Students** | **No card**; USD 100 credit for 12 months, renewable while a student; free-tier VM hours; when the credit runs out the subscription is **disabled, not billed** |

## The host

`deploy/azure/create-vm.sh`, measured against the subscription on
2026-11-22 rather than assumed:

- **Region `northcentralus`.** The student subscription carries an Azure
  Policy allowing only `brazilsouth`, `italynorth`, `spaincentral`,
  `northcentralus` and `canadacentral`. The free-tier sizes are **not
  offered to it in `brazilsouth`**; `northcentralus` offers
  `Standard_B2ats_v2` and `Standard_B2pts_v2`. Distance is irrelevant to a
  5-minute poller.
- **`Standard_B2ats_v2`** (2 vCPU AMD, 1 GiB; 887 MB usable) — x86 so every
  wheel installs as on the dev machine. The collector peaks at ~70 MB.
- **Ubuntu 24.04 LTS**, 64 GiB Premium SSD (the P6 size the free tier
  covers), Standard static public IP (not covered — the expected credit
  burn, to be measured).
- **SSH key only.** `passwordauthentication no`, `permitrootlogin
  without-password`; a password login attempt is refused (tested). NSG:
  inbound port 22 only. Unattended security upgrades on.

`deploy/install.sh` ran unchanged (it installed Python 3.13 through `uv`
although the image ships 3.12).

## Migration (2026-11-22)

1. WSL: `alertavida.service` and both timers disabled; a WAL-safe backup
   taken **after** the stop; backup and stopped live database compared —
   identical row counts, `integrity_check` ok.
2. Copied to the VM, SHA-256 matched, `deploy/cutover.sh`:
   `alertas: moved=1649 snapshot=1649`, `=== CUTOVER: ALL CHECKS PASSED ===`.
3. First round on the VM: every alert `inalterado` — no spurious new or
   resolved alert, i.e. the database continued seamlessly.
4. **Bug found:** `cutover.sh` ran `systemctl start`, not `enable`, so the
   service would not survive a reboot (the README's `enable` step had been
   skipped). Fixed in the script (`enable --now`). Proved by rebooting the
   VM on purpose: the round in progress drained on shutdown
   (`KillSignal=SIGINT`) and collection resumed 13 s after boot.
5. WSL decommissioned: the Windows Startup script removed (byte-identical
   copy in `deploy/wsl/alertavida-wsl.vbs`); the old database kept untouched
   for a week as a fallback.
6. **A third hand-installed piece, found after the PC rebooted:** a Windows
   scheduled task `AlertaVida-WSL` (created 2026-09-06 03:52, right after the
   handoff suggested it), running `wsl.exe -d Ubuntu-26.04 --exec /bin/true`
   at every logon. It woke WSL (~1.3 GB of `vmmemWSL`) with nothing left to
   run. The audit missed it because it only looked at the Startup folder.
   Removed by the maintainer on 2026-11-22 (deleting a root-folder task needs
   an elevated shell); definition kept in `deploy/wsl/AlertaVida-WSL-task.xml`
   with the machine name, Windows account and SID stripped. Verified after:
   no scheduled task references `wsl`, Startup folder holds only
   `desktop.ini`.

## Backups

Local backup timer as before (30 days). The Drive upload moved to a
**dedicated Google account** with `scope = drive.file` — see
[[decisions/off-host-backup-upload]]. First upload under #133's sandboxing:
`0 differences found`, `=== UPLOAD: ALL CHECKS PASSED ===`.

## Failure alerting: a dead-man's switch

On an always-on host, silence means something broke — so the right tool is
an external check that alerts on missing pings, not a local `OnFailure=`
(which cannot report a dead host). On WSL the same check would have paged on
every deliberate shutdown.

`deploy/heartbeat.py` (every 5 min) pings healthchecks.io (free, no card)
when `MAX(visto_ultima_vez)` is at most 15 min old, `/fail` otherwise. The
check URL lives in `/etc/alertavida/heartbeat.env` (`0640 root:alertavida`),
never in git.

**Proved end to end on 2026-11-22:** collector stopped on purpose at
18:57:54 UTC; heartbeats at 7.2 and 12.4 min stayed OK; at 17.8 min the
script sent `/fail`; the maintainer received **"DOWN | AlertaVida-Coletor"**
at 16:13 BRT; collector restarted automatically, next heartbeat OK, **"UP"**
e-mail at 16:14.

**Found while setting it up:** the unit first used `ReadOnlyPaths` for the
database directory, and the read failed with `unable to open database file`
— a read-only SQLite connection to a WAL database still creates the `-shm`
file. Reproduced on the VM before the timer was armed; the unit uses
`ReadWritePaths` and the script opens the database with `mode=ro`.

## Security, checked on the VM

Only port 22 listens; key-only SSH; pending security updates applied at
setup; one stranger's login attempt in the first 30 minutes (normal internet
scanning). All four system units sandboxed (#133): `systemd-analyze security`
1.2 / 0.5 / 1.2 / 1.2. Recommended to the maintainer and done: a passphrase
on the SSH private key (used through `ssh-agent` with an 8 h lifetime) and
2-step verification on the backup account. Recommended, maintainer's to do:
2-step verification on the Microsoft account that owns the subscription —
whoever controls it controls the VM.

## Still open (closes #141)

- **Uptime over the first 7 days** on the VM, same method as #134.
- **Monthly credit burn** (Cost Management), and the projection that USD 100
  lasts 12 months.
- Delete the old WSL database after that week.
