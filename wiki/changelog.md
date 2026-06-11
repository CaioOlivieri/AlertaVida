status: verified
sources: [[raw/context-md-2026-06-11.pt.md]] (§10)
updated: 2026-06-11

# Changelog

Immutable record translated from the original Portuguese in [[raw/context-md-2026-06-11.pt.md]] (§10). New entries: one line per relevant change.

| Date | Change |
|---|---|
| 2026-04-27 | Initial [[raw/context-md-2026-06-11.pt]] creation |
| 2026-04-27 | Camada 1 partial: monitor + database integration, dedup by cod_alerta, pure function montar_alerta, unit tests (6 passing), GitHub repo |
| 2026-04-28 | Camada 1 fixes: error counter, UTF-8 encoding, sanity assertion for counters (7 tests passing) |
| 2026-04-28 | Exponential backoff retry in CEMADEN request, 4xx vs 5xx distinction (11 tests passing) |
| 2026-04-28 | Automatic scheduling with APScheduler (BackgroundScheduler), graceful Ctrl+C shutdown, requirements.txt (15 tests passing) |
| 2026-04-28 | **Camada 1 complete** — system runs continuously as service, resists network failures, cleans up on exit |
| 2026-04-29 | Camada 2 Part 1 complete: src layout refactoring, `pyproject.toml`, `alertavida` package 0.2.0 (15 tests passing) |
| 2026-05-01 | Camada 2 Part 2: 68 tests passing (revisions in issues #1 and #2). Claude Code installed, CLAUDE.md created. Data honesty principle formalized. AI agent workflow documented (§9) |
| 2026-05-01 | **Camada 2 complete** — Part 3 integrated, `pick_value()` removed, 68 tests passing |
| 2026-05-02 | Camada 3 — empirical wsAlertas2 inspection: status, ult_atualizacao and codibge fields mapped |
| 2026-05-02 | Camada 3 — database migration: lifecycle columns + eventos (outbox) table |
| 2026-05-02 | Camada 3 — pure ChangeDetector implemented, 79 tests passing |
| 2026-05-02 | Camada 3 — detector integration in executar_ingestao with transactional outbox, 81 tests |
| 2026-05-02 | **Camada 3 complete** — EventBus, OutboxDispatcher, scheduler job, 88 tests passing |
| 2026-05-03 | Automated test infrastructure: uv + uv.lock, pytest-cov/randomly/ruff, GitHub Actions CI (Ubuntu + Windows), conftest.py with db_temporario fixture, integration marker, daily CEMADEN contract test |
| 2026-05-04 | Pre-Camada 4 — multi-source ingestion design: roadmap renumbered (4-8 with new Camada 5 Correlation), architectural decisions on EscopoGeografico, surrogate key, global EONET ingestion, configurable bands. [[raw/context-md-2026-06-11.pt]] updated before code |
| 2026-05-05 | Pre-Camada 4 Parte A — empirical analysis of 4 CEMADEN samples (240 alerts, 01-02/05/2026) confirmed absence of COBRADE field and taxonomy limited to 2 physical types × 3 levels. Decisions: TipoEvento refactor to COBRADE subgroups; cobrade_codigo + FonteClassificacao on Alerta; granularity limited to subgroup in Camada 4; Parte A subdivided into A.1 (destructive) + A.2 (additive COBRADE); versioned CEMADEN fixtures in tests/fixtures/; data/* in gitignore. [[raw/context-md-2026-06-11.pt]] updated before code |
| 2026-05-07 | Camada 4 Parte A.1 — A.1.1, A.1.3 committed with CI green. A.1.2 committed LOCAL (not pushed). A.1.4 complete and committed. Push pending |
| 2026-05-09 | Camada 4 Parte A.1.4 complete — detector, database, monitor, tests and scripts/reclassificar_escopos.py. cod_alerta str, surrogate key + UNIQUE (fonte, cod_alerta), coordenadas required, escopo_geografico pre-computed at ingestion. 120 tests passing |
| 2026-05-11 | Camada 4 Parte A.2 complete — domain/cobrade.py with EVENTO_CEMADEN_PARA_COBRADE (2 entries based on empirical inspection) and validar_formato. FonteClassificacao enum. cobrade_codigo and fonte_classificacao fields on Alerta with validators. Corresponding columns via idempotent _migrar_banco(). 139 tests, CI green Ubuntu + Windows |
| 2026-05-12 | Item 8 of test cycle complete — direct database.py tests (11 tests covering compatibility check, additive migration, current schema creation, idempotence). Retroactive discovery: A.1 introduced schema break without automatic migration — SchemaIncompativelError added. Legacy schema fixtures versioned in tests/fixtures/schemas_legados.py. 150 tests, CI green |
| 2026-05-12 | Pre-Parte B — architectural design registered before implementation. Decisions documented in decision record |
| 2026-05-13 | Camada 4 Parte B.0 complete — fonte as Alerta attribute, propagated through stack (domain + infra). Two chained commits: B.0.a (domain, intentionally red CI) + B.0.b (infra, green CI). 183 tests, 0.58s |
| 2026-05-16 | Camada 4 Parte B.1 complete — DataSource interface + CemadenSource extraction + contract test infra. Two chained commits, both CI green. 205 tests |
| 2026-05-17 | Camada 4 Parte B.2.a complete — isolated orchestrator in ingestion/orquestrador.py. Three chained commits (B.2.a + hardening-1 + hardening-2), all CI green. 223 tests |
| 2026-05-17 | Camada 4 Parte B.2.b complete — monitor.py reduced to pure entrypoint (46 lines), scheduler.py adjusted. 222 tests. **Parte B inteira complete (8 chained commits, 8 green CIs, zero rollback)** |
| 2026-05-18 | Camada 4 Parte C.0.a — empirical NASA EONET v3 payload inspection. Report in docs/analise_eonet_2026-05-18.md (now [[raw/analise-eonet-2026-05-18.md]]). diagnostico_banco.py promoted to versioned utility. **Next: C.1 — implement NasaEonetSource** |
| 2026-06-11 | Bug 1 fix: resolved alert reappearing now emits `AlertaReativado` and reactivates the row (no more IntegrityError crash-loop). `buscar_snapshots_ativos` renamed to `buscar_snapshots` (returns all statuses). New counter `reativados` in `RelatorioFonte`. [[decisions/alert-reactivation-instead-of-crash]] |
| 2026-06-11 | Bug 2 fix: duplicate `cod_alerta` within the same source batch deduplicated (first kept, each duplicate increments `descartados`), eliminating runtime crash. Invariant 22 added |
| 2026-06-11 | Bug 3 fix: `_normalize_payload` raises `FalhaDeColeta` for unknown dict format or non-list/non-dict payload instead of silently returning []. Invariant 23 added |
| 2026-06-11 | Open-source preparation: Apache-2.0 license, package metadata (PEP 639), README, SECURITY.md, CI hardening (least-privilege permissions + lint), dependabot |
| 2026-06-11 | fix: restaura reconfigure UTF-8 e config de logging no entrypoint monitor |
| 2026-06-11 | fix: padroniza processado_em da outbox em UTC-aware |
