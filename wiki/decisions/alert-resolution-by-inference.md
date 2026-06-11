status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# AlertaResolvido by Inference

CEMADEN's `status` field is always 1 — alerts are removed from the feed without prior notice. `AlertaResolvido` is inferred after 3 consecutive absent rounds (`RODADAS_PARA_RESOLVER=3`, configurable).

Only successful rounds count — network failures do not increment the counter. Resolution is verified via `json_extract(payload, '$.fonte')` and `json_extract(payload, '$.cod_alerta')` in the `eventos` table, not via a field on `RelatorioFonte` (resolved alerts did not come in the batch).
