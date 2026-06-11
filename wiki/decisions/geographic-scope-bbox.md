status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# Geographic Scope via Bbox + Buffer

`EscopoGeografico` enum (BRASIL, PROXIMO, INTERNACIONAL) replaces boolean. `classificar_escopo()` uses four numeric comparisons (no shapely dependency) against a bbox with configurable buffer via `ALERTAVIDA_BUFFER_PROXIMO_GRAUS` (default 5° ~500km).

Scope is computed at ingestion time only — never at query time. Changing buffers only affects new alerts; reclassification requires `scripts/reclassificar_escopos.py`.

Global NASA EONET ingestion (no `bbox` filter on request) — geographic filtering happens in the domain, allowing users to view events outside Brazil when desired.
