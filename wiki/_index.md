status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]], [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-09-05

# AlertaVida Wiki Index

## Overview

**AlertaVida** is a real-time disaster alert system for the Brazilian public. It ingests data from multiple official sources (CEMADEN, NASA EONET, INMET, INPE) and delivers relevant alerts to users based on location. Mission: build a reliable, resilient, testable system — code that can save lives must not fail silently.

**Stack:** Python 3.13, Pydantic v2, APScheduler, SQLite (→ PostgreSQL), pytest, uv. Future: FastAPI, Next.js + Leaflet PWA.

## Pages

### Meta
- [[_schema]] — wiki discipline rules
- [[_integration-state]] — module-by-module wiring table
- [[_glossary]] — domain terminology
- [[changelog]] — project history (translated from §10)

### Projects (8-layer roadmap)
- [[projects/layer-1-ingestion]]
- [[projects/layer-2-domain]]
- [[projects/layer-3-events]]
- [[projects/layer-4-multi-source-ingestion]]
- [[projects/layer-5-correlation]]
- [[projects/layer-6-api]]
- [[projects/layer-7-visual-interface]]
- [[projects/layer-8-notification]]

### Components
- [[components/monitor]]
- [[components/scheduler]]
- [[components/database]]
- [[components/events]]
- [[components/ingestion-orquestrador]]
- [[components/sources-base]]
- [[components/sources-http]]
- [[components/sources-cemaden]]
- [[components/sources-nasa-eonet]]
- [[components/domain-models]]
- [[components/domain-detector]]
- [[components/domain-geographic]]
- [[components/domain-cobrade]]
- [[components/domain-incidente-correlacao]]
- [[components/reporting]]

### Patterns
- [[patterns/code-conventions]]
- [[patterns/test-conventions]]
- [[patterns/git-workflow]]
- [[patterns/ai-agent-workflow]]
- [[patterns/resilience-invariants]]
- [[patterns/security]]
- [[patterns/spec-checklist]] — quality gate against specs ("unit tests for English")
- [[patterns/layer-convergence]] — end-of-layer declared-vs-real audit

### Decisions
- [[decisions/decision-record]] — full table of all decisions
- [[decisions/surrogate-key-cod-alerta-text]]
- [[decisions/tipoevento-cobrade-classification]]
- [[decisions/fonte-as-strict-attribute]]
- [[decisions/outbox-pattern-eventbus]]
- [[decisions/alert-resolution-by-inference]]
- [[decisions/datasource-adapter-falha-de-coleta]]
- [[decisions/orchestrator-silent-reports]]
- [[decisions/schema-incompatibility-pre-a1]]
- [[decisions/geographic-scope-bbox]]
- [[decisions/scheduler-background-jobs]]
- [[decisions/alert-reactivation-instead-of-crash]]
- [[decisions/utc-timestamps-consistency]]
- [[decisions/sqlite-wal-busy-timeout]]
- [[decisions/shared-report-formatter]]
- [[decisions/sdd-practices-from-spec-kit]] — spec-kit evaluation: 5 practices adopted, tooling rejected
- [[decisions/template-method-http-datasource]] — HttpDataSource consolidates the CemadenSource/NasaEonetSource coletar() skeleton
- [[decisions/foreign-key-eventos-agregado-id]] — eventos→alertas FK declared in CREATE TABLE, no 12-step rebuild; cheap-now guardrail for Camada 6
- [[decisions/weathernext-anticipation-not-datasource]] — WeatherNext 2: rejected as DataSource, adopted as phased internal anticipation track (#68–#72)
- [[decisions/agregado-incidente-id]] — incident lifecycle events get a new agregado_incidente_id FK column, not a payload-only reference or a second outbox table; the #22 FK stays untouched
- [[decisions/rtree-spatial-index-blocking]] — R-Tree confirmed available on both CI OSes (empirical evidence in PR #76), used for the blocking spatial index; no fallback needed
- [[decisions/incidente-representante-blocking]] — a candidate incident's most recently joined member represents it for the blocking-stage decidir_correlacao call
- [[decisions/incident-lifecycle-wiring]] — issue #61 wiring: aplicar_resultado_deteccao returns alerta ids, merge-survivor is the older incident, REATIVADO/RESOLVIDO lifecycle handling walks the merge tree
- [[decisions/systemd-vps-deployment]] — issue #78: minimal VPS + systemd (no Docker), DB path moved outside the git checkout, backup via sqlite3.Connection.backup() (CLI not assumed present), KillSignal=SIGINT + a real SIGTERM handler + shutdown(wait=True) so a restart drains an in-flight round instead of orphaning an alert from #61's lifecycle
- [[decisions/incident-boundary-reconciliation-sweep]] — issue #87: a reconciliation sweep (not a shared-connection transaction) recovers an alert orphaned by a crash between avaliar_candidatos_correlacao and criar_incidente/adicionar_membro_incidente; invariant 4 gets an explicit exception for Camada 5's own persistence chain, with a written trigger for reconsidering the shared-connection design
