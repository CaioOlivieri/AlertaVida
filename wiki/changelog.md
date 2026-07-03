status: verified
sources: [[raw/context-md-2026-06-11.pt.md]] (§10)
updated: 2026-06-21

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
| 2026-06-11 | feat: habilita WAL e busy_timeout no SQLite para concorrencia ingestao/dispatcher |
| 2026-06-11 | feat: scheduler loga relatorio por rodada via reporting.py compartilhado |
| 2026-06-14 | Camada 4 Parte C.1 complete — `NasaEonetSource` (second `DataSource`). Builds `Alerta` directly (not `from_dict`) due to v3 payload shape: GeoJSON `[lon, lat]`, no severity (`nivel_risco=INDETERMINADO`), category→`TipoEvento` via `CATEGORIA_EONET_PARA_TIPO`, most-recent-fix selection by date. Production query `status=open`. `cobrade_codigo` left None/INDETERMINADA (numeric COBRADE deferred to C.2). Synthetic fixtures in `tests/fixtures/eonet/`. Two chained commits (C.1.a fixtures + C.1.b source), reuses parametrized contract test. 252 tests, CI green |
| 2026-06-14 | Maintainability review Fase 1 — low-risk cleanup: `Alerta` imported under TYPE_CHECKING in orquestrador (dropped F821 ignore), dead `backports.zoneinfo` fallback removed, `_migrar_banco` docstring corrected, test-data layout documented. No behavior change |
| 2026-06-14 | Maintainability review Fase 2 / A1 — extracted shared HTTP transport to `sources/_http.py` (`fetch_com_retry` raising `FalhaDeColeta`, `parse_json`, `RespostaHTTP`/`Opener`). `CemadenSource`/`NasaEonetSource` lost ~50 duplicated lines each; retry tests consolidated into `tests/sources/test_http.py`. 253 tests |
| 2026-06-14 | Maintainability review Fase 2 / A2 — `aplicar_resultado_deteccao` uses `UPDATE … RETURNING id` via `_executar_retornando_id` (eliminates the per-event SELECT); ATUALIZADO and REATIVADO branches merged (REATIVADO adds `status_interno='ATIVO'`). No behavior change. 253 tests |
| 2026-06-21 | Camada 4 Parte C.2 complete — `EVENTO_EONET_PARA_COBRADE` dict + `mapear_eonet` in `domain/cobrade.py`; wired into `NasaEonetSource._montar_alerta`; `cobrade_codigo` / `fonte_classificacao` set per EONET category. 262 tests |
| 2026-06-21 | Camada 4 Parte C.3 complete — `NasaEonetSource()` added to source list in `monitor.py` and `scheduler.py`; two-source orchestration tests updated. 263 tests |
| 2026-07-02 | Maintainability review Fase 3 (issue #8) — dead schema fields removed: `AlertaSnapshot.nivel_risco`/`.tipo_evento` (never read by `detectar_mudancas`, `buscar_snapshots` SELECT trimmed to match), `EventoDetectado.schema_versao` (outbox INSERT already hardcoded `1`), and the `alertas.assinatura` column (always `NULL`, superseded by `ult_atualizacao`; dropped via idempotent `ALTER TABLE ... DROP COLUMN` in `_migrar_banco`). No behavior change. 290 tests |
| 2026-07-02 | Maintainability review issue #10 closed — Camada 4 C.3 verified complete (both sources wired, multi-source failure isolation tested, wiki already reflected EONET as integrated); issue was never closed after the work landed |
| 2026-07-02 | Maintainability review issue #11 (C1/C2/D3/D4) — deleted orphan `scripts/export_context.py` (predated the wiki, unreferenced) and `scripts/inspect_eonet_payload.py` (purpose served, Camada 4 C.1-C.3 complete); dropped speculative `idx_uf`/`idx_evento`/`idx_nivel` indexes (no query uses them; `idx_fonte`/`idx_escopo_geografico` kept); persisted `Alerta.descricao` (column + INSERT + event payload — was write-only despite `NasaEonetSource` populating it since C.1). 295 tests |
| 2026-07-02 | Maintainability review issue #18 (A/B/C) — removed `ResultadoDeteccao.codigos_resolvidos` (redundant with `eventos` filtered by `RESOLVIDO`, investigated wiring it in first and found no non-redundant use); documented `eventos.tentativas` as inert until a real retry policy exists (`wiki/components/events.md`); left `EventBus.handler_count` as-is (test-only utility, low impact). 295 tests |
| 2026-07-02 | **Bug fix (issue #30), found investigating #19** — every CEMADEN alert since Camada 4 A.2 was classified `tipo_evento=INDETERMINADO` / `cobrade_codigo=NULL`: `CemadenSource` read a nonexistent `tipoevento` key (real key is `evento`, compound `"<categoria> - <nível>"`), and even the right key's value never matched the bare-category mapping tables. `_categoria_do_evento` now splits correctly; test fixtures rewritten to the real payload shape (they previously tested a shape the API never sent); daily contract test hardened with a classification-rate assertion so acceptance-rate-only checks can't mask this again. Verified against the live CEMADEN endpoint. 298 tests |
| 2026-07-02 | SDD practices adopted from spec-kit evaluation (issue #33) — full tooling adoption rejected (dual sources of truth vs the wiki; see [[decisions/sdd-practices-from-spec-kit]]); five practices adopted as conventions: [[patterns/spec-checklist]] (quality gate against specs, born from #30), [[patterns/layer-convergence]] (declared-vs-real audit, born from #10/#30), `## Clarifications` section in layer pages (seeded in [[projects/layer-5-correlation]]), dependency/parallel markers for issue batches ([[patterns/ai-agent-workflow]]), explicit-skip rule. Docs only, no code |
