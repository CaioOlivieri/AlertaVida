status: blocked
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-07-02

# Layer 5: Event Correlation (blocked)

**Concept:** `Incidente` = aggregate of N `Alerta`s referring to the same physical event observed by different sources.

Example: a flood in Recife may produce CEMADEN (level ALTO), NASA EONET (severeStorms), and INMET (accumulated rainfall) alerts — all describing the same event.

**Algorithm (initial):**
- Same time window (e.g., ±6h)
- Geographic distance below threshold (e.g., 50 km)
- Compatible event types (explicit per-pair rule)

**Prerequisite:** spatial indexing. SQLite R-Tree in current phase; PostGIS when migrating to Postgres in Camada 6.

## Clarifications

*(Per [[decisions/sdd-practices-from-spec-kit]]: before technical planning of
this layer starts, run a structured clarification round with the maintainer and
record every question + answer here — not in chat history. The spec above has
placeholder numbers (±6h, 50 km) that are illustrations, not decisions.)*

Open questions to resolve before planning:

- Time window: what value, and is it symmetric? Does it vary by event type
  (a wildfire correlates over days; a flash flood over hours)?
- Distance threshold: single radius or per-event-type? Point-to-point distance
  or bbox overlap?
- Cross-source confidence: do sources with `nivel_risco=INDETERMINADO` (EONET)
  correlate on equal footing with classified CEMADEN alerts?
- Compatible-type pairs: which (TipoEvento × TipoEvento) pairs correlate?
  Explicit table, no inference.
- Incident lifecycle: does an `Incidente` resolve when all member alerts
  resolve? Can it reactivate?
- Correlation is retroactive or forward-only (does a new alert join an
  existing incident, re-evaluate old ones, or both)?

*(No entries yet — layer has not started.)*
