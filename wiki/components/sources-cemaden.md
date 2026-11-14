status: integrated
sources: `src/alertavida/sources/cemaden.py`
updated: 2026-11-14

# sources-cemaden

CEMADEN-specific `DataSource` implementation (B.1.b). Encapsulates:

- JSON payload normalization (`_normalize_payload`).
- Per-item mapping to `Alerta` via `_montar_alerta` (catches only `ValueError` — `TypeError`/`AttributeError`/`KeyError` propagate as bugs).
- Geographic scope classification and COBRADE mapping.

HTTP transport (retry/backoff + JSON parse, both raising `FalhaDeColeta`) is shared via [[components/sources-http]] — `coletar()` calls `fetch_com_retry` then `parse_json`. Constructor: keyword-only with injectable `url`, `opener`, `timeout_segundos`.

## Timestamps are Brasília time (#127)

The painel sends `datahoracriacao` / `ult_atualizacao` without an offset, in
Brasília time. `_montar_alerta` calls `Alerta.from_dict(..., fuso_se_naive=FUSO_PAINEL_CEMADEN)`
(fixed UTC−3), so stored values are real UTC. Rows written before 2026-11-14 were
shifted +3h by a one-time migration; outbox payloads were not. See
[[decisions/cemaden-timestamps-brasilia-time]].
