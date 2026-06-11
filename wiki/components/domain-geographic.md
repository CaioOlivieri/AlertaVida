status: integrated
sources: `src/alertavida/domain/geographic.py`
updated: 2026-06-11

# domain-geographic

Geographic scope classification (Parte A.1):

- `FaixaGeografica` — named tuple defining a buffer zone around Brazil.
- `classificar_escopo(lat, lon)` — returns `EscopoGeografico` (BRASIL, PROXIMO, INTERNACIONAL) via bbox comparison (four numeric comparisons, no shapely dependency).
- Buffers configurable via env var `ALERTAVIDA_BUFFER_PROXIMO_GRAUS` (default 5° ~500km).
- Computed at ingestion time only — never at query time. Reclassification requires `scripts/reclassificar_escopos.py`.
