status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]], [[raw/claude-md-2026-06-11.pt.md]], `src/alertavida/`
updated: 2026-07-17

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
| `sources/_http.py` | Shared transport: `fetch_com_retry` (retry/backoff + size cap → `FalhaDeColeta`), `parse_json`, `RespostaHTTP` Protocol, `Opener`, `opener_padrao` (HTTPS-only redirect policy) | `sources/cemaden.py`, `sources/nasa_eonet.py` | integrated |
| `sources/cemaden.py` | `CemadenSource(DataSource)`: HTTP + retry + backoff + payload normalization | `ingestion/orquestrador.py` | integrated |
| `sources/nasa_eonet.py` | `NasaEonetSource(DataSource)`: EONET v3 `status=open`, builds `Alerta` directly, category→`TipoEvento` map, `mapear_eonet` for COBRADE (C.2), most-recent-fix selection, `nivel_risco=INDETERMINADO` | `monitor.py`, `scheduler.py` | integrated |

## Current flow

```
scheduler.agendar_ingestao()
  → APScheduler (ingestao job every 5min + dispatcher job every 30s)
  → monitor.main()
    → executar_ingestao([CemadenSource(), NasaEonetSource()])
      → CemadenSource().coletar() (urllib + 4 attempts, 2/4/8s backoff)
      → NasaEonetSource().coletar() (urllib + 4 attempts, 2/4/8s backoff)
      → buscar_snapshots(fonte=CEMADEN)
      → buscar_snapshots(fonte=EONET)
      → detectar_mudancas(alertas, snapshots) per source
      → aplicar_resultado_deteccao() (single transaction: alerts + outbox events) per source
```
