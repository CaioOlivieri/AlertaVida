status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]], [[raw/claude-md-2026-06-11.pt.md]], `src/alertavida/`
updated: 2026-06-14

## Module wiring table (single source of truth)

| Module | Responsibility | Wired into | Status |
|---|---|---|---|
| `domain/alerta.py` | Frozen `Alerta` model with `fonte`, COBRADE fields, `from_dict()` | All ingestion + persistence | integrated |
| `domain/enums.py` | `FonteDado`, `TipoEvento`, `NivelRisco`, `EscopoGeografico`, `FonteClassificacao` | Every domain-aware module | integrated |
| `domain/municipio.py` | `Municipio` model | Via `Alerta` | integrated |
| `domain/coordenadas.py` | `Coordenadas` model | Via `Alerta` | integrated |
| `domain/detector.py` | `ChangeDetector`, `AlertaSnapshot`, `EventoDetectado`, `ResultadoDeteccao`, `TipoEventoDetectado` | `ingestion/orquestrador.py` | integrated |
| `domain/cobrade.py` | COBRADE subgroup mapping tables + validators | `sources/cemaden.py` | integrated |
| `domain/geographic.py` | `FaixaGeografica`, `classificar_escopo()` | `sources/cemaden.py` | integrated |
| `monitor.py` | Entrypoint: `main()` → `criar_banco()`, `executar_ingestao()`, prints formatted report via `formatar_relatorio()` | CLI entrypoint | integrated |
| `scheduler.py` | `agendar_ingestao()`: APScheduler `BackgroundScheduler` with `ingestao` (5min) + `dispatcher` (30s) jobs; logs per-run report via `formatar_relatorio()` | Production service | integrated |
| `reporting.py` | `formatar_relatorio()` — shared report formatter for ingestion output | `monitor.py`, `scheduler.py` | integrated |
| `database.py` | `criar_banco()`, `buscar_snapshots()`, `aplicar_resultado_deteccao()`, outbox INSERT | `orquestrador.py`, `scheduler.py` startup | integrated |
| `events.py` | In-memory `EventBus` (subscribe/publish), `OutboxDispatcher` | `scheduler.py` | integrated |
| `ingestion/orquestrador.py` | `executar_ingestao()`: orchestrates collect → detect → persist per source; `RelatorioFonte`, `RelatorioIngestao` | `monitor.py`, `scheduler.py` | integrated |
| `sources/base.py` | `DataSource` ABC, `ResultadoColeta` frozen, `FalhaDeColeta` exception | `ingestion/orquestrador.py` | integrated |
| `sources/_http.py` | Shared transport: `fetch_com_retry` (retry/backoff → `FalhaDeColeta`), `parse_json`, `RespostaHTTP` Protocol, `Opener` | `sources/cemaden.py`, `sources/nasa_eonet.py` | integrated |
| `sources/cemaden.py` | `CemadenSource(DataSource)`: HTTP + retry + backoff + payload normalization | `ingestion/orquestrador.py` | integrated |
| `sources/nasa_eonet.py` | `NasaEonetSource(DataSource)`: EONET v3 `status=open`, builds `Alerta` directly, category→`TipoEvento` map, most-recent-fix selection, `nivel_risco=INDETERMINADO` | not yet wired into orchestrator (C.3) | implemented |

## Current flow

```
scheduler.agendar_ingestao()
  → APScheduler (ingestao job every 5min + dispatcher job every 30s)
  → monitor.main()
    → executar_ingestao([CemadenSource()])
      → CemadenSource().coletar() (urllib + 4 attempts, 2/4/8s backoff)
      → ResultadoColeta(alertas, descartados, coletado_em)
      → buscar_snapshots(fonte=CEMADEN)
      → detectar_mudancas(alertas, snapshots)
      → aplicar_resultado_deteccao() (single transaction: alerts + outbox events)
```

Layer 4 Part C.1 (`NasaEonetSource`) is **implemented** but not yet in the orchestrator's
source list — production still runs `executar_ingestao([CemadenSource()])`. Next planned work:
C.2 (numeric EONET→COBRADE mapping) and C.3 (wire `NasaEonetSource()` into `monitor.py` /
`scheduler.py` + multi-source orchestration tests).
