status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]], [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-07-02

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
