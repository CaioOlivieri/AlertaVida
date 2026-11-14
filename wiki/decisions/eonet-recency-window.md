status: implemented
sources: `src/alertavida/sources/nasa_eonet.py`, `tests/sources/test_nasa_eonet.py`, issue #124, EONET v3 API (measured 2026-11-13/14), production backup `alertavida-20261114T135031Z.db`
updated: 2026-11-14

# EONET: a 60-day recency window instead of `limit=500`

`NasaEonetSource` requested `status=open&limit=500`. On 2026-11-13 EONET had
**7,245** open events, returned most-recent-first, so every round saw only the
500 most recently updated — every collection report since at least
2026-09-28 reads `EONET: 500 coletados`.

`ChangeDetector` resolves an alert by absence after 3 rounds
([[decisions/alert-resolution-by-inference]]). An event that slid out of the
top 500 was therefore marked `AlertaResolvido` while still open upstream:
**184 of the 229 EONET alerts in `RESOLVIDO` were still open in the API**
(2026-11-13 backup). The truncation, not the source, decided what
"resolved" meant.

**Adopted: `status=open&days=60`, no `limit`.** Ingestion stays global.

## "Open" in EONET does not mean "happening"

It only means NASA never closed the event. Measured 2026-11-14:

| Query | Events | Most recent fixes |
|---|---|---|
| `status=open` | 7,245 | back to 2002 |
| `status=open` + Brazil/PROXIMO bbox | 857 | 852 wildfires, 2024–2025; none in the last 60 days |
| `status=open&days=60` | 86 | 2026-09-15 … 2026-11-12 |
| `status=open&days=30` | 39 | 2026-10-15 … 2026-11-12 |

The `days` parameter filters on the event's geometry dates: the oldest
latest-fix in the `days=60` answer is exactly 60 days before the query.

With the window, leaving the feed means "no observation in 60 days", which
is what the absence rule should mean. A new fix brings the event back as
`AlertaReativado`. Without `limit`, nothing truncates.

## Alternatives considered and rejected (with the numbers)

- **Brazil bbox filter + reactivate the 184** — the first plan, agreed with
  the maintainer from the 2026-11-13 audit, dropped after measuring. It would
  have ingested 857 wildfires last observed in 2024–2025 as active alerts
  (one `Incidente` each), resolved all 500 current alerts by absence, and
  re-resolved the 184 three rounds after reactivating them. The audit's
  claim that "831 open EONET events in Brazil are not being collected" was
  wrong in spirit: they are open, not live.
- **Global, no limit** — 7,245 events per round (~5 MB), almost all stale;
  ~6,500 new alerts and incidents on the first round. Fixes truncation but
  not the meaning of "open".
- **`days=30`** — 39 events. Rejected in favour of 60 by the maintainer:
  a single-fix event stays visible for two months, enough for Camada 5's
  correlation window and for a slow-moving fire to get its next fix.

## Relationship to earlier decisions

- [[decisions/decision-record]] "Global NASA EONET ingestion (no `bbox`
  filter on request)" — **still holds.** The window is temporal, not
  spatial.
- [[decisions/decision-record]] "EONET production query is `status=open`" —
  holds, narrowed: open **and** observed in the window. That row rejected
  `status=all&days=30` (mostly closed history); `status=open&days=60` is a
  different query.

## The 184 falsely resolved alerts stay resolved

Their last fixes are April–June 2026, five to seven months before this
change. Under the new definition they are correctly resolved; reactivating
them would mark as active events nobody has observed since mid-year. Their
`AlertaResolvido` events in the outbox keep the wrong *reason* (truncation,
not staleness); this page is the record of that.

## Expected effect of the deploy

Projected from the live API and the 2026-11-14 backup:

- 86 events collected, all `INTERNACIONAL` (70 wildfires, 2 severe storms,
  14 sea/lake ice → `INDETERMINADO`).
- Of the 501 EONET alerts `ATIVO`: 74 stay in the feed, **427 are resolved
  three rounds after the deploy** (~15 min), together with their
  `Incidente`s — one burst of `AlertaResolvido` / `IncidenteResolvido`.
- 12 new alerts (`AlertaCriado`), 0 reactivations.

The burst is the correction, not a regression. Real post-deploy numbers are
recorded below once measured (`_schema.md` rule 1).

## Recorded finding: EONET says nothing about Brazil right now

No open EONET event inside the Brazil/PROXIMO bbox has a fix in the last 60
days; the most recent Brazilian one is from 2025, despite the August–October
fire season in between. For a Brazilian alert product EONET is currently
context, not signal. The meteorological gap is INMET's to fill.
