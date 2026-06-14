status: in-progress
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-06-14

# Layer 4: Multi-Source Ingestion (in progress)

Adapter pattern with `DataSource` interface. Parallel ingestion of independent sources coexisting in the `alertas` table with `fonte` column as discriminator. No cross-source correlation — that belongs to Camada 5.

## A.1 — Destructive domain + database refactor (DONE 2026-05-09)

Surrogate key (`id INTEGER PRIMARY KEY AUTOINCREMENT`) + `UNIQUE (fonte, cod_alerta)`; `cod_alerta` as TEXT; `municipio` optional, `coordenadas` required; `EscopoGeografico` enum; `TipoEvento` refactored to COBRADE subgroups; `geographic.py`; `scripts/reclassificar_escopos.py`. 120 tests.

## A.2 — Additive COBRADE taxonomy (DONE 2026-05-11)

`domain/cobrade.py` with `EVENTO_CEMADEN_PARA_COBRADE` (2 entries); `FonteClassificacao` enum; `cobrade_codigo` and `fonte_classificacao` fields on `Alerta`; additive migration via `_migrar_banco()`. 139 tests.

## B.0 — fonte as Alerta attribute (DONE 2026-05-13)

Two chained commits (B.0.a domain, B.0.b infra; CI temporarily red between them). `FonteDado(StrEnum)`, `fonte: Annotated[FonteDado, Strict()]` on `Alerta`/`AlertaSnapshot`/`EventoDetectado`. `fonte_por_codigo` on `ResultadoDeteccao`. Schema unchanged. 183 tests.

## B.1 — DataSource interface + CemadenSource extraction (DONE 2026-05-16)

Two chained commits (B.1.a contract infra, B.1.b extraction; both CI green). `sources/base.py`: `DataSource` ABC, `ResultadoColeta`, `FalhaDeColeta`. `sources/cemaden.py`: `CemadenSource(DataSource)` with injectable constructor. Contract test infrastructure (`tests/sources/contrato.py`). Local `_RespostaHTTP` Protocol (PEP 544) for strict-by-contract typing. 205 tests.

## B.2.a — Isolated orchestrator (DONE 2026-05-17)

Three chained commits (B.2.a + hardening-1 + hardening-2; all CI green). `ingestion/orquestrador.py`: `executar_ingestao(sources, *, agora=None) -> RelatorioIngestao`. `RelatorioFonte`/`RelatorioIngestao` with `__post_init__` invariants. `FakeDataSource.com_rodadas` for multi-round tests. `TipoEventoDetectado` StrEnum. 223 tests.

## B.2.b — monitor.py as pure entrypoint (DONE 2026-05-17)

`monitor.py` reduced to 46 lines (entrypoint only). `scheduler.py` adjusted: `criar_banco()` at startup, imports from canonical namespaces. 222 tests. **Parte B inteira concluída (8 chained commits, 8 green CIs).**

## Planned sources

- **CEMADEN** — active (Camada 1). Hydrological real-time alerts.
- **INMET** — planned. Meteorological data from automatic stations.
- **NASA EONET** — next. Global natural events (wildfires, storms). Global ingestion, domain-level Brazil/Próximo/Internacional filtering.
- **NOAA NOMADS / GFS** — planned for predictive layer. GRIB2 format, `xarray`/`cfgrib`.

## C.0.a — EONET v3 empirical inspection (DONE 2026-05-18)

`scripts/inspect_eonet_payload.py` (441 lines) captured real EONET v3 data: 500 open events (497 wildfires), 328 events last 30 days, 0 open in Brazil, 3 in history. Geometry 100% Point. Report in `docs/analise_eonet_2026-05-18.md` (now [[raw/analise-eonet-2026-05-18.md]]).

## C.1 — NasaEonetSource (DONE 2026-06-14)

`NasaEonetSource(DataSource)` in `sources/nasa_eonet.py`. Same pattern as `CemadenSource` (keyword-only injectable `url`/`opener`/`timeout`, HTTP GET + retry/backoff, `_normalize_payload`, `FalhaDeColeta` on round failure), but builds `Alerta` **directly** instead of via `from_dict` because the v3 payload diverges:

- coordinates from `geometry[].coordinates` `[lon, lat]` (GeoJSON, nested)
- no severity → `nivel_risco = INDETERMINADO` (data honesty)
- category `id` (English) → `TipoEvento` via module-local `CATEGORIA_EONET_PARA_TIPO` (invariant 10)
- `geometry[].date` per fix → uses the **most recent fix by date**, not list order

Production query is `status=open` (active events only). `cobrade_codigo` left None / `FonteClassificacao.INDETERMINADA` — numeric COBRADE deferred to C.2 (atomic invariant respected). Synthetic fixtures in `tests/fixtures/eonet/`. Two chained commits (C.1.a fixtures + C.1.b source). Reuses `verificar_contrato_data_source`. 24 new tests, 252 total, CI green.

**Scope note:** wiki's original C.1 bullet folded COBRADE mapping into C.1; split out to C.2 to avoid assigning numeric COBRADE codes against the official Defesa Civil table under uncertainty ("não inventar mapeamentos baseado em suposição").

## C.2 — EONET COBRADE mapping (next)

Expand `domain/cobrade.py` with `EVENTO_EONET_PARA_COBRADE` + `mapear_eonet`, and wire it into `NasaEonetSource._montar_alerta` (replacing the C.1 `cobrade=None`). Map relevant categories to COBRADE codes: wildfires → CLIMATOLOGICO, severeStorms → METEOROLOGICO, floods → HIDROLOGICO, volcanoes/landslides → GEOLOGICO. `TipoEvento` mapping already exists in the source (C.1).

## C.3 — Orchestrator integration

`monitor.py` and `scheduler.py` include `NasaEonetSource()` in sources list. Multi-source orchestration tests.

## COBRADE granularity note

Camada 4 classifies only to subgroup level (e.g., `1.2.0.0.0` for hydrological, `1.1.3.0.0` for mass movements). Subtype distinction requires topography, urban density, INMET data — Camada 5's problem. Heuristic inference in Camada 4 would violate data honesty.
