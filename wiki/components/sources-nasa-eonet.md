status: integrated
sources: `src/alertavida/sources/nasa_eonet.py`
updated: 2026-06-21

# sources-nasa-eonet

NASA EONET v3 `DataSource` implementation (Camada 4 Parte C.1). Global natural events
(wildfires, severe storms, volcanoes, floods). Brazil/Próximo/Internacional filtering
happens in the domain (`classificar_escopo`), not at the source — see
[[decisions/geographic-scope-bbox]] and the "Global NASA EONET ingestion" decision.

Encapsulates:

- Payload normalization (`_normalize_payload`): extracts `events[]`, raises `FalhaDeColeta` on unknown format (invariant 23).
- Per-event mapping via `_montar_alerta` (catches only `ValueError` — `TypeError`/`AttributeError`/`KeyError` propagate as bugs).

HTTP transport (retry/backoff + JSON parse, both raising `FalhaDeColeta(fonte=EONET, ...)`) is shared via [[components/sources-http]] — same module used by [[components/sources-cemaden]].

## Why direct `Alerta` construction (not `Alerta.from_dict`)

The v3 payload shape diverges from CEMADEN, so `from_dict` does not fit:

| Aspect | Handling in `NasaEonetSource` |
|---|---|
| Coordinates | `geometry[].coordinates` = `[lon, lat]` (GeoJSON order, nested) |
| Severity | EONET has none → `nivel_risco = NivelRisco.INDETERMINADO` (data honesty) |
| Type | `categories[].id` (English) → `TipoEvento` via `CATEGORIA_EONET_PARA_TIPO` |
| Date | `geometry[].date` per fix → **most recent fix by date** (`_fix_mais_recente`), not list order |
| Municipality | not provided → `None` |
| COBRADE | via `mapear_eonet` (C.2): `cobrade_codigo` from `EVENTO_EONET_PARA_COBRADE` dict; `fonte_classificacao` = `MAPEADA_POR_NOME` if mapped, `INDETERMINADA` otherwise |

`CATEGORIA_EONET_PARA_TIPO` maps only categories with an unambiguous COBRADE group
(`wildfires`, `floods`, `severeStorms`, `volcanoes`, `landslides`); anything else falls to
`TipoEvento.INDETERMINADO` (invariant 10 — each source maps its own terminology).

## Constructor

Keyword-only with injectable `url`, `opener`, `timeout_segundos`. Production query is
`status=open&limit=500`. The `RespostaHTTP` Protocol and `Opener` type used for
strict-by-contract typing live in [[components/sources-http]].

## Integrated (C.3)

The orchestrator now runs `executar_ingestao([CemadenSource(), NasaEonetSource()])` in
both `monitor.py` and `scheduler.py`. Multi-source orchestration tests cover the
two-source configuration.
