status: implemented
sources: [[decisions/decision-record]]
updated: 2026-07-02

# TipoEvento Refactored to COBRADE Subgroups

`TipoEvento` enum refactored from CEMADEN-specific values to COBRADE/EM-DAT standard subgroups: `HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`. Each `DataSource` implements its own mapping.

Camada 4 classifies only to subgroup level. Subtype distinction (flood vs flash flood vs waterlogging) belongs to Camada 5 with topography, urban density, and INMET data. `cobrade_codigo` + `FonteClassificacao` preserves audit trail for future reclassification.

## Correction (issue #30, 2026-07-02)

The empirical inspection this page's mapping was based on captured the right category **values** (`"Risco Hidrológico"`, `"Movimentos de Massa"`) but the implementation ended up reading a field name (`tipoevento`) that the real CEMADEN payload never sends, and never accounted for the value being compound (`"<categoria> - <nível>"`, e.g. `"Risco Hidrológico - Moderado"`) — the real key is `evento`. Result: every CEMADEN alert was silently classified `TipoEvento.INDETERMINADO` / `cobrade_codigo=NULL` since this mapping was introduced (Camada 4 A.2), undetected because the daily contract test only measured acceptance rate, not classification rate (both hardened in #30). `CemadenSource._categoria_do_evento` now splits `evento` on the first `" - "` before mapping. See `data/samples/cemaden_raw_*.json` (475 real items, 5 distinct compound values across the 2 known categories) for the verified real shape.
