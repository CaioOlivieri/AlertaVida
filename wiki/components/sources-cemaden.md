status: integrated
sources: `src/alertavida/sources/cemaden.py`
updated: 2026-06-11

# sources-cemaden

CEMADEN-specific `DataSource` implementation (B.1.b). Encapsulates:

- HTTP GET with 4 attempts (immediate, 2s, 4s, 8s backoff), no retry on 4xx (except 408/429).
- JSON payload normalization (`_normalize_payload`).
- Per-item mapping to `Alerta` via `_montar_alerta` (catches only `ValueError` — `TypeError`/`AttributeError`/`KeyError` propagate as bugs).
- Geographic scope classification and COBRADE mapping.
- Round-level failures wrapped in `FalhaDeColeta` with `from exc`.

Constructor: keyword-only with injectable `url`, `opener`, `timeout_segundos`. Local `_RespostaHTTP` Protocol (PEP 544) for strict-by-contract typing of the HTTP response.
