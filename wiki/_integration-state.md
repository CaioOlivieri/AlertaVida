status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]], [[raw/claude-md-2026-06-11.pt.md]], `src/alertavida/`
updated: 2026-08-13 (issue #61)

## Module wiring table (single source of truth)

| Module | Responsibility | Wired into | Status |
|---|---|---|---|
| `domain/alerta.py` | Frozen `Alerta` model with `fonte`, COBRADE fields, `from_dict()` | All ingestion + persistence | integrated |
| `domain/tempo.py` | `parse_iso_utc(valor)` — parse ISO 8601, assume UTC if naive (issue #20) | `domain/alerta.py`, `sources/nasa_eonet.py` | integrated |
| `domain/enums.py` | `FonteDado`, `TipoEvento`, `NivelRisco`, `EscopoGeografico`, `FonteClassificacao` | Every domain-aware module | integrated |
| `domain/municipio.py` | `Municipio` model | Via `Alerta` | integrated |
| `domain/coordenadas.py` | `Coordenadas` model | Via `Alerta` | integrated |
| `domain/detector.py` | `ChangeDetector`, `AlertaSnapshot`, `EventoDetectado`, `ResultadoDeteccao`, `TipoEventoDetectado` | `ingestion/orquestrador.py` | integrated |
| `domain/cobrade.py` | COBRADE subgroup mapping tables + validators | `sources/cemaden.py` | integrated |
| `domain/geographic.py` | `FaixaGeografica`, `classificar_escopo()` | `sources/cemaden.py` | integrated |
| `monitor.py` | Entrypoint: `main()` → `criar_banco()`, `executar_ingestao()`, prints formatted report via `formatar_relatorio()` | CLI entrypoint | integrated |
| `scheduler.py` | `agendar_ingestao()`: APScheduler `BlockingScheduler` with `ingestao` (5min) + `dispatcher` (30s) jobs; blocks on `start()`, clean `Ctrl+C` shutdown (issue #21); logs per-run report via `formatar_relatorio()`; builds the EventBus via `criar_bus_producao()` once and injects it into `OutboxDispatcher` (issue #24) | Production service | integrated |
| `reporting.py` | `formatar_relatorio()` — shared report formatter for ingestion output | `monitor.py`, `scheduler.py` | integrated |
| `database.py` | `criar_banco()`, `buscar_snapshots()`, `aplicar_resultado_deteccao()`, outbox INSERT | `orquestrador.py`, `scheduler.py` startup | integrated |
| `database.py` — Incidente persistence (#59) | `incidentes`/`incidente_membros` tables, `agregado_incidente_id` FK on `eventos`; `criar_incidente`/`adicionar_membro_incidente`/`resolver_incidente`/`reativar_incidente`/`fundir_incidentes`, each its own outbox transaction; read helpers `buscar_incidente_atual`/`status_incidente`/`todos_membros_resolvidos` (#61) | `ingestion/orquestrador.py` (`_correlacionar_rodada`, #61) | integrated |
| `database.py` — Correlation blocking (#60) | `idx_alertas_espacial` R-Tree index (populated on alert `CRIADO`), `correlacao_observacoes` table, `avaliar_candidatos_correlacao()` (blocking → `domain.correlacao.decidir_correlacao` → instrumentation row per pair) | `ingestion/orquestrador.py` (`_abrir_ou_juntar_incidente`, #61) | integrated |
| `events.py` | In-memory `EventBus` (subscribe/publish), `OutboxDispatcher`, `log_handler`, `criar_bus_producao()` factory — no module-level singleton (issue #24) | `scheduler.py` (sole composition root) | integrated |
| `ingestion/orquestrador.py` | `executar_ingestao()`: orchestrates collect → detect → persist → correlate per source; `RelatorioFonte`, `RelatorioIngestao`. Since #61, wires Camada 5 Incidente lifecycle (`_abrir_ou_juntar_incidente`, `_correlacionar_rodada`) right after `aplicar_resultado_deteccao` — see [[components/ingestion-orquestrador]] | `monitor.py`, `scheduler.py` | integrated |
| `sources/base.py` | `DataSource` ABC (transport-agnostic), `ResultadoColeta` frozen, `FalhaDeColeta` exception | `ingestion/orquestrador.py` | integrated |
| `sources/_http.py` | Shared transport: `fetch_com_retry` (retry/backoff + size cap → `FalhaDeColeta`), `parse_json`, `RespostaHTTP` Protocol, `Opener`, `opener_padrao` (HTTPS-only redirect policy); `HttpDataSource(DataSource)` template method (shared `__init__` + concrete `coletar()`, issue #20) | `sources/cemaden.py`, `sources/nasa_eonet.py` | integrated |
| `sources/cemaden.py` | `CemadenSource(HttpDataSource)`: `URL`/`USER_AGENT` class constants + payload normalization | `ingestion/orquestrador.py` | integrated |
| `sources/nasa_eonet.py` | `NasaEonetSource(HttpDataSource)`: EONET v3 `status=open`, builds `Alerta` directly, category→`TipoEvento` map, `mapear_eonet` for COBRADE (C.2), most-recent-fix selection, `nivel_risco=INDETERMINADO` | `monitor.py`, `scheduler.py` | integrated |

## Current flow

```
scheduler.agendar_ingestao()
  → criar_bus_producao() → OutboxDispatcher(bus)   (built once, at wiring time)
  → APScheduler (ingestao job every 5min + dispatcher job every 30s)
  → monitor.main()
    → executar_ingestao([CemadenSource(), NasaEonetSource()])
      → CemadenSource().coletar() (urllib + 4 attempts, 2/4/8s backoff)
      → NasaEonetSource().coletar() (urllib + 4 attempts, 2/4/8s backoff)
      → buscar_snapshots(fonte=CEMADEN)
      → buscar_snapshots(fonte=EONET)
      → detectar_mudancas(alertas, snapshots) per source
      → aplicar_resultado_deteccao() (single transaction: alerts + outbox events) per source
      → _correlacionar_rodada() per source (issue #61, Camada 5)
        → CRIADO/REATIVADO-sem-membership: avaliar_candidatos_correlacao() (#60 blocking → #58 decidir_correlacao)
          → criar_incidente() / adicionar_membro_incidente() / fundir_incidentes()
        → REATIVADO-com-membership: reativar_incidente() se o Incidente estava RESOLVIDO
        → RESOLVIDO: resolver_incidente() se todos_membros_resolvidos()
```
