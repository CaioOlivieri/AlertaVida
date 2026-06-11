status: blocked
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-06-11

# Layer 5: Event Correlation (blocked)

**Concept:** `Incidente` = aggregate of N `Alerta`s referring to the same physical event observed by different sources.

Example: a flood in Recife may produce CEMADEN (level ALTO), NASA EONET (severeStorms), and INMET (accumulated rainfall) alerts — all describing the same event.

**Algorithm (initial):**
- Same time window (e.g., ±6h)
- Geographic distance below threshold (e.g., 50 km)
- Compatible event types (explicit per-pair rule)

**Prerequisite:** spatial indexing. SQLite R-Tree in current phase; PostGIS when migrating to Postgres in Camada 6.
