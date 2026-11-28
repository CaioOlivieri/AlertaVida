status: implemented
sources: `src/alertavida/acervo/{exportar,site}.py`, `src/alertavida/database.py` (`rodadas`, `registrar_rodada`, `consultar_avisos_vigentes`), `scripts/extrair_rodadas_journal.py`, `deploy/alertavida-acervo.{service,timer}`, [[raw/cobertura-journal-wsl-2026-11-24]], [[raw/cobertura-journal-vm-2026-11-24]], issue #158, PRs #160–#164
updated: 2026-11-28

# The first consumer is an open archive, built from the daily backup

## Why (measured on the 2026-11-23/24 backups)

After seven months AlertaVida had no consumer. The outbox delivered 6,856
events to a logger; Camada 5 had never put alerts from two sources in one
incident (0 cross-source observations of 4,251, 0 merges, every CEMADEN
incident with one alert — see [[projects/layer-5-correlation]], frozen the
same day). What the project does have, and nobody publishes as far as we
found, is a **per-alert history of CEMADEN alerts** in UTC (#127), with the
INMET warnings in force at each onset (#153). CEMADEN's site shows the live
panel and monthly counts.

| Option | Outcome |
|---|---|
| Real-time alerts to the public | Rejected. The official channel exists (Defesa Civil Alerta, cell broadcast; SMS 40199). A third party alerting carries trust and legal risk — in June 2026 an intrusion sent a false alert to ~30 million people. |
| Public API on the VM | Not now: opens a port beyond 22 on a 1 GiB host and changes the security posture, for readers who do not exist yet. |
| **Static archive generated from the backup** | **Adopted** (maintainer, 2026-11-23). Zero new attack surface on the VM, free to host anywhere, a dataset researchers and journalists can cite. |

## What was built

1. **Coverage as data.** The database recorded each alert's
   `visto_ultima_vez`, never when the collector ran — so "no alert" and
   "collector off" were indistinguishable, and the collector ran ~15 % of the
   time before 2026-11-22. Now:
   - `rodadas` (#161): one row per (round, source) at the end of every
     completed round; `coletados` NULL ⇔ that source failed (`CHECK`); a
     killed round leaves no row (invariant 27).
   - Before the table, coverage was extracted from the journals with
     `scripts/extrair_rodadas_journal.py` (#160, #162): WSL 2,462 rounds
     (2026-09-28 → 2026-11-22), VM 397 rounds up to the deploy, cut exactly
     at the first `rodadas` row. **Nothing exists before 2026-09-28T23:49Z.**
   - **Measure in windows, not rounds.** Every restart fires an off-grid round,
     so `rounds ÷ possible` reached 100.4 % on the VM. Windows (5 min CEMADEN,
     30 min INMET) with at least one successful collection: VM 99.2 %, WSL
     15.5 %. Only windows already finished at the backup instant count.
2. **Export** (`python -m alertavida.acervo.exportar`, #163): opens the
   newest backup with `mode=ro&immutable=1`; five CSVs (alerts, warnings,
   warning municipalities, alert↔warning annotation, per-day coverage);
   `DICIONARIO.md` generated from the same column definitions as the CSV
   headers; `metadados.json` names the backup by SHA-256. Same backup, same
   bytes. The annotation is the #153 rule itself
   (`consultar_avisos_vigentes`), not a copy.
3. **Site** (`python -m alertavida.acervo.site`, #164): plain HTML + one CSS
   from the export only; active alerts, last 30 days with coverage, one page
   per municipality; relative links; every source string escaped; Brasília
   time on screen, UTC in the CSVs; "not an official alert channel" with
   199 / 193 / 40199 on every page.
4. **Timer** (`alertavida-acervo.timer`, 00:30 daily, after the backup):
   writes `/var/lib/alertavida/acervo/{export,site}`; no network; only that
   directory writable (`StateDirectory=`); `systemd-analyze security` 0.5.

## Verified

- Export of `alertavida-20261124T000500Z.db` on the VM: 931 alerts, 10
  warnings, 13,574 warning-municipality rows, 21 annotations, 59 coverage
  rows; identical locally; backup byte-identical afterwards, no `-wal`/`-shm`.
- 5 random alerts match the database; 5 active alerts match the live CEMADEN
  panel after Brasília → UTC; 28 of 28 active alerts still on the panel.
- Site: 436 pages, 2.6 MB; 2,211 links, 0 broken, 0 absolute; 0 pages with
  unbalanced tags; two generations identical.
- Unit run on the VM: `Result=success`, `/var/lib/alertavida` still `2770`.

## The site, redesigned for phones (2026-11-28)

The first site was functional and ugly, and on a phone its alert table
scrolled sideways — which axe flagged as a **serious** violation
(`scrollable-region-focusable`: the scrolling region could not be reached by
keyboard). Redesigned mobile-first: alerts as semantic lists, one memorable
element (the 30-day strip of alerts per day over collection coverage, so a
reader sees at a glance when "no alert" may mean "collector off"), plain
language for people who do not know the project, provenance moved to the
Dados page. Verified in an isolated Chromium (no network, read-only, no
capabilities) with axe-core, hash-pinned, versioned in
`scripts/verificacao_site/`: 0 violations and no sideways scroll on three
pages, at 360 and 1280 px, light and dark. The audit also caught two
regressions of the redesign itself before review (label-widened strip
columns; the last date label pushing the page 8 px past the screen).

## Limits recorded

- **Resolution time is when the collector noticed**, not when the alert left
  the panel: the third consecutive round without it. With the collector off,
  the real exit can be days earlier — `cobertura.csv` is how a reader judges.
- **An INMET warning annotates only if the collector saw it.** Collection
  began 2026-11-23T13:46Z; a warning that left the active list before that
  (the one over alert 3592, Rio, seen only on the #153 validation copy)
  annotates nothing in production.
- **`aviso_municipios` is the growing table**: 13,574 rows from 10 warnings.
  At a few warnings a day that is millions of rows a year — fine for SQLite,
  but the CSV may need compression before publication.
- **Not verified:** rendering in a real browser at phone width (no browser
  available in the session); the structure is tested.

## Not done here — publication

Waits for the data licence. CEMADEN's site content is CC BY-ND 3.0 ("no
derivatives"), which may or may not cover the alert data; CEMADEN set up a
working group in 2025 for its 2026–2027 Open Data Plan. The INMET endpoint
has no published licence. The maintainer files a Fala.BR (LAI) request; the
answer goes to `raw/` verbatim, and publication (GitHub Pages from a
separate repo with a deploy key — the VM stays outbound-only — plus a
quarterly Zenodo deposit with a DOI) gets its own issue.
