status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# TipoEvento Refactored to COBRADE Subgroups

`TipoEvento` enum refactored from CEMADEN-specific values to COBRADE/EM-DAT standard subgroups: `HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`. Each `DataSource` implements its own mapping.

Camada 4 classifies only to subgroup level. Subtype distinction (flood vs flash flood vs waterlogging) belongs to Camada 5 with topography, urban density, and INMET data. `cobrade_codigo` + `FonteClassificacao` preserves audit trail for future reclassification.
