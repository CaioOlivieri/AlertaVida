status: integrated
sources: `src/alertavida/sources/nasa_eonet.py`
updated: 2026-08-07

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
| Date | `geometry[].date` per fix → the series is split in two (see "Two instants", below), never picked by list order |
| Municipality | not provided → `None` |
| COBRADE | via `mapear_eonet` (C.2): `cobrade_codigo` from `EVENTO_EONET_PARA_COBRADE` dict; `fonte_classificacao` = `MAPEADA_POR_NOME` if mapped, `INDETERMINADA` otherwise |

`CATEGORIA_EONET_PARA_TIPO` maps only categories with an unambiguous COBRADE group
(`wildfires`, `floods`, `severeStorms`, `volcanoes`, `landslides`); anything else falls to
`TipoEvento.INDETERMINADO` (invariant 10 — each source maps its own terminology).

## Two instants from one geometry series (#57)

An EONET event arrives **already aggregated**: `geometry[]` is a time series —
"the pairing of a specific date/time with a location" (EONET v3 docs) — with 1..N
fixes (median 1, max 52 in the empirical inspection). `_fixes_validos` returns the
whole validated series in payload order and `_montar_alerta` takes two extremes
from it **by date, never by list position** (the API does not guarantee chronological
ordering):

| Field | Fix used | Why |
|---|---|---|
| `data_criacao` | **earliest** | Event onset. Camada 5 measures correlation windows against estimated onset, not against the latest observation — see [[projects/layer-5-correlation]], Round 1 Q1 |
| `ult_atualizacao` | **latest** | Most recent published observation |
| `coordenadas` | **latest** | Best current position estimate |

Malformed fixes (`type != Point`, short or non-numeric `coordinates`, missing or
unparseable `date`) are skipped while building the series, so a corrupt earliest fix
never becomes the onset; the event is discarded (`ValueError` → counted as
`descartados`) only if **no** fix survives.

Single-fix events — the vast majority — get `data_criacao == ult_atualizacao`.
Before #57, `data_criacao` carried the *latest* fix and `ult_atualizacao` was
hard-coded `None`; the change therefore also makes EONET alerts eligible for
`ATUALIZADO` detection in [[components/domain-detector]], which compares
`ult_atualizacao` against the stored snapshot.

## Constructor

Keyword-only with injectable `url`, `opener`, `timeout_segundos`. Production query is
`status=open&limit=500`. The `RespostaHTTP` Protocol and `Opener` type used for
strict-by-contract typing live in [[components/sources-http]].

## Integrated (C.3)

The orchestrator now runs `executar_ingestao([CemadenSource(), NasaEonetSource()])` in
both `monitor.py` and `scheduler.py`. Multi-source orchestration tests cover the
two-source configuration.
