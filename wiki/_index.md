status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]], [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-11-22

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
- [[handoff-2026-09-06]] — project state, machine map, field-data measurements and open-issue order as of 2026-09-06
- [[audit-2026-11-13]] — maintainability audit after the two-month pause: every finding with its status (fixed / corrected by measurement / filed as #129–#136 / left alone) and evidence

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
- [[decisions/weathernext-surge-watch-design]] — issue #70: mean table only (deterministic threshold indicator, not ensemble probability), `bq` CLI over the Python client (`--maximum_bytes_billed` as a CLI flag), runs as the maintainer not `alertavida` (ADC credential, not a service-account key), user systemd units with `%h` (no hardcoded username/home path)
- [[decisions/off-host-backup-upload]] — issue #120: daily rclone upload of the local backups to Google Drive (append-only remote), versioned after a month installed by hand; local retention has one owner (backup.py, 30 days) after a hand-installed script silently pruned at 7
- [[decisions/eonet-recency-window]] — issue #124: EONET query `status=open&days=60` instead of `limit=500`; the truncation was resolving still-open events by absence (184 of 229), and "open" upstream does not mean live (7,245 open, 86 observed in 60 days); global ingestion kept, Brazil-bbox + reactivation plan rejected after measuring
- [[decisions/cemaden-timestamps-brasilia-time]] — issue #127: the CEMADEN painel publishes naive Brasília time; the source declares UTC−3 (`parse_iso_utc(fuso_se_naive=)`), 756 stored rows migrated +3h once, gated by `PRAGMA user_version` (first versioned migration); outbox payloads left as history
- [[decisions/municipality-is-the-incident-boundary]] — maintainer decision 2026-11-16: one storm over two municipalities is two incidents; structural gate on different known IBGE codes (#129); 746 CEMADEN REVISAO rows become NAO_VINCULA by definition, #71 goes dormant
- [[decisions/systemd-sandboxing]] — issue #133: sandboxing directives on the three system units (systemd-analyze 8.5 EXPOSED → 1.2/0.5/1.2), and root-run deploy scripts pass paths as argv to quoted heredocs instead of pasting them into `python3 -c` (injection proved on the old form)
- [[decisions/phase2-azure-for-students]] — issue #141: production moved off WSL (~14 % uptime, PC shut down by hand, power spikes) to an Azure for Students VM (no card, no spending); region/size measured against the subscription's policy; cutover with `enable` bug found and fixed; dedicated backup account; healthchecks.io dead-man's switch proved end to end
