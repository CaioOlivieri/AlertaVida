status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]]
updated: 2026-06-11

# Glossary

Domain terms remain in **Portuguese** in the code. Their English definitions are below.

| Term | Definition |
|---|---|
| `Alerta` | Pydantic v2 frozen model representing a single alert event from any source. |
| `cod_alerta` | Source-specific alert identifier. `str` after Parte A.1 (CEMADEN uses numeric strings, EONET uses `EONET_5421`). |
| `snapshot` | `AlertaSnapshot` — previous state of an alert used by `ChangeDetector` to detect changes. |
| `rodadas_ausente` | Counter of consecutive successful rounds where an alert was absent from the feed. Triggers `AlertaResolvido` at `RODADAS_PARA_RESOLVER` (default 3). |
| `outbox` | Transactional outbox pattern: INSERT into `alertas` and `eventos` in the same SQLite transaction to eliminate dual-write. |
| `escopo_geografico` | `EscopoGeografico` enum (BRASIL, PROXIMO, INTERNACIONAL) — computed at ingestion time, never at query time. |
| `COBRADE` | Brazilian disaster classification taxonomy used to normalize `TipoEvento` into standard subgroups (`HIDROLOGICO`, `GEOLOGICO`, etc.). |
| `fonte_classificacao` | `FonteClassificacao` enum (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) — provenance of the COBRADE classification. |
| `surrogate key` | `id INTEGER PRIMARY KEY AUTOINCREMENT` replacing the old composite PK. `UNIQUE (fonte, cod_alerta)` enforces business uniqueness. |
| `encadeado` | Chained-commit style: each sub-part is its own prompt, commit, CI run, and recap before the next. Introduced in Camada 4. |
| `FalhaDeColeta` | Typed exception wrapping a round-level collection failure (network exhausted, unrecoverable HTTP, JSON parse error). Distinguished from per-alert errors (counted as `descartados`). |
