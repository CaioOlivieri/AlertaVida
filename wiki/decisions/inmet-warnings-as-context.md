status: implemented
sources: `src/alertavida/domain/aviso.py`, `src/alertavida/sources/inmet.py`, `src/alertavida/ingestion/avisos.py`, `src/alertavida/database.py` (`registrar_avisos`, `avisos_vigentes`), `src/alertavida/scheduler.py`, `tests/test_contrato_inmet.py`, [[raw/analise-inmet-2026-11-23]], issue #153
updated: 2026-11-23

# INMET warnings are context for incidents, never alerts

AlertaVida had no Brazilian meteorological source; EONET has no Brazilian
event in 60 days (#124). INMET — the WMO-registered alerting authority for
Brazil (OID `2.49.0.0.76.0`) — publishes official severe-weather warnings.

## The decision (maintainer, 2026-11-23): option A

**One INMET warning covers 589 to 3,206 municipalities** — on 2026-11-23 a
single "Tempestade / Perigo Potencial" covered 3,059 municipalities in 19
states for a whole day. It is a regional forecast of conditions, not an
observed event at a place, and it collides with
[[decisions/municipality-is-the-incident-boundary]] (#129).

| Option | Outcome |
|---|---|
| **A. Context** — warnings in their own table with IBGE codes and validity; an alert is *annotated* with the warnings in force in its municipality at its onset | **Adopted.** Fits #129 and the identity-vs-cascade split: a warning is the *conditions* an alert happened under, not the same event |
| B. One `Alerta` per (warning, municipality) | ~3,000 alerts per warning, ~18k a day of forecast noise. Rejected |
| C. One `Alerta` at the polygon centroid | One point for 19 states. Rejected |

No `Alerta` and no `Incidente` is ever made from a warning.

## How it is built

- **`AvisoMeteorologico`** (`domain/aviso.py`) — frozen: CAP identifier,
  `id_aviso` + `id_sequencia`, event, `SeveridadeAviso` (Perigo Potencial /
  Perigo / Grande Perigo ≙ CAP Moderate / Severe / Extreme), aware UTC
  window, IBGE codes (7 digits, validated), `encerrado`.
- **`InmetSource`** (`sources/inmet.py`) — not a `DataSource` (it produces no
  `Alerta`s); same transport as the others (`fetch_com_retry`: retry,
  size cap, HTTPS-only redirects, `FalhaDeColeta`). Reads `hoje` + `futuro`,
  de-duplicates by CAP identifier, discards malformed items with a log line.
- **Time zone — the #127 trap, caught before it reached the database.** The
  JSON labels `data_inicio` with `Z`, but the official CAP of the same warning
  says `onset ...T00:00:00-03:00`. The collector reads `inicio`/`fim`
  (`"2026-11-24 00:00"`) as UTC−3 and never trusts the `Z`.
- **Persistence** — `avisos_meteorologicos` (one row per CAP message,
  `UNIQUE codigo_cap`) and `aviso_municipios` (`WITHOUT ROWID`, primary key
  `(codibge, aviso_id)` so the lookup by municipality is the index). Additive
  `CREATE TABLE IF NOT EXISTS`, no `user_version` step needed.
- **Lifecycle by validity, not by absence.** A warning ends at `fim` or when
  `encerrado`; a new `id_sequencia` supersedes the previous message of the
  same `id_aviso`, even if the old one had a longer window. The absence rule
  that broke EONET (#124) does not apply: warnings never pass through
  `ChangeDetector`.
- **Annotation computed at read time** — `avisos_vigentes(codibge, instante)`.
  Not materialised on the alert: a warning can be extended or closed after
  the alert arrived, and the annotation should reflect the latest known
  state. Instants compared with `julianday()`, not as strings (fractional
  seconds and offsets differ).
- **Collected every 30 minutes**, in a separate scheduler job (`avisos`),
  outside the alert pipeline. Warnings change a few times a day (59 in 12
  days) and the payload is ~280 KB (a base64 icon per warning, ignored). A
  collection failure is logged and touches nothing else. `monitor.py` runs
  it once after the alert round.
- **Daily contract test** (`tests/test_contrato_inmet.py`, CI job
  `contrato`): every live warning parses with 0 discards and carries IBGE
  codes; the first warning's `inicio`/`fim` equal its CAP `onset`/`expires`.
  The endpoint is the portal's backend, not a documented API, and has no
  published licence — this test is the early warning.

## Verified (2026-11-23)

- Contract test against the live endpoint: both tests passed.
- One-shot run on a copy of the production database: `INMET (avisos): 3
  vigentes ou futuros (3 novos, 0 descartados)`; 3 warnings, **6,854**
  `(municipality, warning)` rows.
- **First real annotation:** CEMADEN alert 3592, hydrological, **Rio de
  Janeiro (3304557)**, onset 2026-11-23 03:20 UTC → under INMET warning
  *Tempestade / Perigo Potencial*, 2026-11-23 03:00 → 2026-11-24 02:59 UTC.
  1 of 16 active CEMADEN alerts annotated at that moment.
- Lookup plan: `SEARCH m USING PRIMARY KEY (codibge=?)`, then the warning by
  rowid — no scan.

## Limits recorded

- **No backfill.** Only the live JSON carries IBGE codes; the RSS history and
  the CAP messages do not. Alerts created before the deploy are not
  annotated.
- Pending until a week has run on the VM: warning counts and supersede /
  expiry behaviour checked against the RSS history.
