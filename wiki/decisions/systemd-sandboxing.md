status: implemented
sources: `deploy/alertavida.service`, `deploy/alertavida-backup.service`, `deploy/alertavida-upload.service`, `deploy/cutover.sh`, `deploy/seed-test-db.sh`, `deploy/validate-backup.sh`, issue #133
updated: 2026-11-22

# systemd sandboxing for the three system units; no shell values in root-run Python

Found by the 2026-11-13 audit ([[audit-2026-11-13]]), done on the Azure VM
right after the Phase 2 cutover (#141).

## Sandboxing

The collector reads payloads from two outside sources every five minutes.
If a dependency that parses them were ever exploited, the attacker's code
would run with whatever the unit allows. #78 set the basics —
`NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, one writable
directory — and `systemd-analyze security` rated all three units **8.5
EXPOSED**.

Added to all three: private `/tmp` and devices; kernel tunables, modules,
logs, clock, hostname and control groups protected; other processes
invisible (`ProtectProc=invisible`, `ProcSubset=pid`); no namespaces,
realtime, SUID/SGID or W+X memory; no capabilities at all; syscalls limited
to `@system-service` minus `@privileged @resources`; native architecture
only. Network: `AF_INET AF_INET6 AF_UNIX` for the collector and the upload
(outbound HTTPS + local DNS); the backup gets `PrivateNetwork=true` and
`AF_UNIX` only — it copies a local file and has no reason to reach anything.

### Measured on the VM (2026-11-22, systemd 255, Ubuntu 24.04)

| Unit | Before | After |
|---|---|---|
| `alertavida.service` | 8.5 EXPOSED | **1.2 OK** |
| `alertavida-backup.service` | 8.5 EXPOSED | **0.5 SAFE** |
| `alertavida-upload.service` | 8.5 EXPOSED | **1.2 OK** |

Verified with real runs after installing the units:

- collector restarted: full round, `CEMADEN: 6 coletados`, `EONET: 83
  coletados`, no error, `NRestarts=0` — DNS, HTTPS and SQLite writes all work
  under the filter;
- backup: `Backup gravado em .../alertavida-20261122T171551Z.db`,
  `Result=success`.

- upload (verified 2026-11-22, once rclone was configured — #141):
  `0 differences found`, `=== UPLOAD: ALL CHECKS PASSED ===`;
- heartbeat, added later with the same block (#141): 1.2 OK, pings sent.

## No shell values pasted into root-run Python

`cutover.sh`, `seed-test-db.sh` and `validate-backup.sh` ran blocks like:

```
python3 -c "
src = sqlite3.connect('$REAL_DB')
"
```

The shell pastes the path into the Python source before Python sees it, so a
path containing a quote becomes code — run as root. Proved before fixing: the
`main` version of `seed-test-db.sh`'s block, given a source directory named
`x'); import os; os.system('touch PWNED'); ('`, **created `PWNED`**.

Every block now uses `python3 - "$A" "$B" <<'PY' ... PY`: a quoted heredoc
(the shell substitutes nothing inside it) with paths read from `sys.argv`.
The same malicious directory run through the new blocks: no `PWNED`,
integrity checks and row counts pass, the path is printed as data.

Exploiting the old form needed whoever runs these root scripts to pass a
crafted path, so the practical risk was low; the fix costs nothing and
removes the class.

## Still open from #133

- **Drive OAuth scope:** resolved in #141 — a dedicated account with
  `scope = drive.file` ([[decisions/off-host-backup-upload]]).
