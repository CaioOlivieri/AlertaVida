status: implemented
sources: `src/alertavida/sources/nasa_eonet.py`
updated: 2026-06-14

# sources-nasa-eonet

NASA EONET v3 `DataSource` implementation (Camada 4 Parte C.1). Global natural events
(wildfires, severe storms, volcanoes, floods). Brazil/Próximo/Internacional filtering
happens in the domain (`classificar_escopo`), not at the source — see
[[decisions/geographic-scope-bbox]] and the "Global NASA EONET ingestion" decision.

Encapsulates:

- HTTP GET with 4 attempts (immediate, 2s, 4s, 8s backoff), no retry on 4xx (except 408/429). Shares the retry shape with [[components/sources-cemaden]].
- Payload normalization (`_normalize_payload`): extracts `events[]`, raises `FalhaDeColeta` on unknown format (invariant 23).
- Per-event mapping via `_montar_alerta` (catches only `ValueError` — `TypeError`/`AttributeError`/`KeyError` propagate as bugs).
- Round-level failures wrapped in `FalhaDeColeta(fonte=EONET, ...)` with `from exc`.

## Why direct `Alerta` construction (not `Alerta.from_dict`)

The v3 payload shape diverges from CEMADEN, so `from_dict` does not fit:

| Aspect | Handling in `NasaEonetSource` |
|---|---|
| Coordinates | `geometry[].coordinates` = `[lon, lat]` (GeoJSON order, nested) |
| Severity | EONET has none → `nivel_risco = NivelRisco.INDETERMINADO` (data honesty) |
| Type | `categories[].id` (English) → `TipoEvento` via `CATEGORIA_EONET_PARA_TIPO` |
| Date | `geometry[].date` per fix → **most recent fix by date** (`_fix_mais_recente`), not list order |
| Municipality | not provided → `None` |
| COBRADE | `cobrade_codigo=None` / `INDETERMINADA` in C.1 — numeric mapping is C.2 |

`CATEGORIA_EONET_PARA_TIPO` maps only categories with an unambiguous COBRADE group
(`wildfires`, `floods`, `severeStorms`, `volcanoes`, `landslides`); anything else falls to
`TipoEvento.INDETERMINADO` (invariant 10 — each source maps its own terminology).

## Constructor

Keyword-only with injectable `url`, `opener`, `timeout_segundos`. Production query is
`status=open&limit=500`. Local `_RespostaHTTP` Protocol (PEP 544) for strict-by-contract
typing of the HTTP response.

## Not yet wired (C.3)

The orchestrator still runs `executar_ingestao([CemadenSource()])`. Adding
`NasaEonetSource()` to the source list in `monitor.py` / `scheduler.py` (plus multi-source
orchestration tests) is [[projects/layer-4-multi-source-ingestion]] Part C.3.
