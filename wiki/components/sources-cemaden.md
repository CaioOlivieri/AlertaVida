status: integrated
sources: `src/alertavida/sources/cemaden.py`
updated: 2026-06-11

# sources-cemaden

CEMADEN-specific `DataSource` implementation (B.1.b). Encapsulates:

- JSON payload normalization (`_normalize_payload`).
- Per-item mapping to `Alerta` via `_montar_alerta` (catches only `ValueError` — `TypeError`/`AttributeError`/`KeyError` propagate as bugs).
- Geographic scope classification and COBRADE mapping.

HTTP transport (retry/backoff + JSON parse, both raising `FalhaDeColeta`) is shared via [[components/sources-http]] — `coletar()` calls `fetch_com_retry` then `parse_json`. Constructor: keyword-only with injectable `url`, `opener`, `timeout_segundos`.
