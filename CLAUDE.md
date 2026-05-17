# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

`CONTEXT.md` is the project's living document — it tracks every architectural decision, the 8-layer roadmap, and a dated changelog. **Read it before any non-trivial work** and update it (sections 8 and 10) whenever a new architectural decision is made or a layer milestone is reached.

## Commands

Install:
```powershell
uv sync --extra dev
```

One-shot ingestion run (debug):
```powershell
python -m alertavida.monitor
```

Continuous service (runs immediately, then every 5 minutes; `Ctrl+C` to stop):
```powershell
python -m alertavida.scheduler
```

Tests:
```powershell
uv run pytest                          # 222 testes, sem integração (padrão)
uv run pytest -m integration -v        # só teste de contrato CEMADEN (bate na API real)
uv run pytest tests/test_monitor.py::test_montar_alerta_descarta_sem_codigo  # teste único
```
The full suite must run in **< 1 second** — `time.sleep` is mocked everywhere. Integration tests are excluded by default via `addopts = ["-m", "not integration"]` in `pyproject.toml`.

## Architecture

The system is built **layer by layer** following the roadmap in `CONTEXT.md` §3. Each layer must be functional and tested before moving on. Current state:

- **Camada 1 (Ingestão)** — DONE. `monitor.py` fetches from CEMADEN with retry+backoff, `database.py` persists to SQLite with dedup by `cod_alerta` PK, `scheduler.py` wraps everything in APScheduler. Schema compatibility is enforced explicitly in `criar_banco()` via `_verificar_compatibilidade_schema()`, which raises `SchemaIncompativelError` on pre-A.1 schemas (missing `id` or `fonte` columns). See CONTEXT.md §8 row "Verificação explícita de schema antes de `_migrar_banco()`".
- **Camada 2 (Domínio)** — DONE. `src/alertavida/domain/` has frozen Pydantic v2 models (`Alerta`, `Municipio`, `Coordenadas`) and enums (`NivelRisco`, `TipoEvento`) fully integrated with ingestion and persistence.
- **Camada 3 (Detecção de Mudanças e Eventos)** — DONE. Pure `ChangeDetector`, transactional Outbox Pattern, in-memory EventBus, and `OutboxDispatcher` scheduled every 30 seconds are implemented and covered by 88 tests.
- **Camada 4 (Ingestão Multi-Fonte)** — in progress. Subdivided into four parts (defined 2026-05-05, see CONTEXT.md §3): Parte A.1 (destructive refactor of domain + database: surrogate key, `cod_alerta` as TEXT, `municipio` optional, `coordenadas` required, `EscopoGeografico` enum, `TipoEvento` refactored to COBRADE subgroups, `geographic.py`, `scripts/reclassificar_escopos.py`) — DONE 2026-05-09; Parte A.2 (additive: `cobrade.py` module, `cobrade_codigo` field, `FonteClassificacao` enum, new nullable columns) — DONE 2026-05-11; Parte B (CemadenSource as `DataSource`, refactor `monitor.py` into orchestrator) — re-subdivided 2026-05-12 into B.0 (add `fonte` to `Alerta` model) + B.1 (`sources/base.py` with `DataSource` ABC, `ResultadoColeta`, `FalhaDeColeta`; `sources/cemaden.py` extracted from `monitor.py`; contract test infrastructure) + B.2 (`ingestion/orquestrador.py` with `executar_ingestao`, `RelatorioFonte`, `RelatorioIngestao`; `monitor.py` reduced to entrypoint). Parte B.0 DONE 2026-05-13 in two encadeados commits: B.0.a (d28cf56, domain: `FonteDado` enum, `fonte` field on `Alerta`/`AlertaSnapshot`/`EventoDetectado`, `Annotated[FonteDado, Strict()]` cirúrgico) — CI temporarily red by design, 10 tests in `test_monitor.py`; B.0.b (a5f5062, infra: `ResultadoDeteccao.fonte_por_codigo`, `aplicar_resultado_deteccao` without `fonte` param, `buscar_snapshots_ativos(fonte: FonteDado)`) — CI verde. Parte B.1 DONE 2026-05-16 in two encadeados commits, both with CI verde: B.1.a (90aa977, infra: sources/base.py with DataSource ABC + ResultadoColeta frozen + FalhaDeColeta exception; sources/contrato.py with verificar_contrato_data_source parametrized; tests/fixtures/sources_fake.py with FakeDataSource; 196 tests); B.1.b (c9d9592, extraction: sources/cemaden.py with CemadenSource(DataSource) migrating HTTP+retry+backoff+_montar_alerta+_normalize_payload+escopo+COBRADE from monitor.py; keyword-only constructor with injectable url/opener/timeout_segundos; Protocol _RespostaHTTP PEP 544 for strict-by-contract typing; monitor.py simplified, test_monitor.py reduced to 3 orchestration tests, test_contrato_cemaden.py exercising full CemadenSource flow; 205 tests, 37s CI). Parte C (NasaEonetSource). Execution order: A.1 → A.2 → B.0 → B.1 → B.2 → C. A.1 is destructive (PK shape, enum values change); A.2 is purely additive; B.0/B.1/B.2 are encadeados (each commit + CI verde + recap before the next). Do not merge any of these in the same commit. Parte B.2.a DONE 2026-05-17 in three encadeados commits: B.2.a (`5044a7d`) + hardening-1 (`c77864d`) + hardening-2 (`059a6d5`); 223 tests. Parte B.2.b DONE 2026-05-17: `monitor.py` reescrito como entrypoint puro (46 linhas), `scheduler.py` ajustado com `criar_banco()` no startup, `tests/test_monitor.py` reescrito (2 testes puros de `_formatar_relatorio`), 222 tests total. Parte B inteira (B.0 + B.1 + B.2.a + B.2.b) DONE. Next: Item 7 (DB_PATH explícito) or Parte C (NasaEonetSource).
- **Camadas 5–8** — blocked. Don't pre-build for them. The eventual target structure (`ingestion/`, `events/`, `sources/`, `correlation/`, `api/`, `notifications/` subpackages) is documented in `CONTEXT.md` §4 but migration happens **as each layer is worked on**, not upfront.

### Key flow (current)

`scheduler.agendar_ingestao()` → APScheduler (`ingestao` job every 5 min + `dispatcher` job every 30s) → `monitor.executar_ingestao()` → `CemadenSource().coletar()` (encapsulates urllib + 4 attempts, 2/4/8s backoff, no retry on 4xx except 408/429; JSON parse; normalize payload; map each item to Alerta with escopo + COBRADE classification; raises FalhaDeColeta on round-level failure) → `ResultadoColeta(alertas, descartados, coletado_em)` → `buscar_snapshots_ativos()` → `detectar_mudancas()` → `aplicar_resultado_deteccao()` (single transaction: alerts + outbox events). After B.2, `monitor.executar_ingestao` will be replaced by `ingestion.orquestrador.executar_ingestao(sources: list[DataSource])` accepting multiple sources.

### Domain layer (Camada 2)

`src/alertavida/domain/` contains frozen Pydantic v2 models (`Alerta`, `Municipio`, `Coordenadas`) and enums (`NivelRisco`, `TipoEvento`, and — after Parte A.2 of Camada 4 — `FonteClassificacao`). `Alerta.from_dict()` is the canonical entry point: it accepts the raw source-style dict (with field-name fallbacks) and raises `ValueError` on missing/invalid required fields. After Parte A.1 of Camada 4: `TipoEvento` values are COBRADE subgroups (`HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`); `TipoEvento.from_string` returns `INDETERMINADO` for unknowns; `NivelRisco.from_string` raises. Both normalize accents/case before matching. After Parte A.2: `Alerta` carries `cobrade_codigo: str | None` (subgroup-level only — e.g. `1.2.0.0.0` for hydrological, `1.1.3.0.0` for mass movements) and `fonte_classificacao: FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) registering provenance of the classification. Mapping logic lives in `domain/cobrade.py`.

Integration with `monitor.py`/`database.py` is complete: `montar_alerta()` returns `Alerta`, and `database.py` persists through `aplicar_resultado_deteccao()`.

After Parte B.0 of Camada 4: `Alerta` carries `fonte: Annotated[FonteDado, Strict()]` (strict cirúrgico via `Annotated`, NOT global `strict=True` in `model_config`). `FonteDado(StrEnum)` in `domain/enums.py` is a closed set (CEMADEN, EONET, INMET, INPE) — no INDETERMINADA, because source is always known at coletion time. `FonteDado.from_string` raises on unknown values (aligned with `NivelRisco.from_string`, not with `TipoEvento.from_string`). `Alerta.from_dict(data, *, fonte: FonteDado)` requires `fonte` as keyword-only. `AlertaSnapshot.fonte` and `EventoDetectado.fonte` mirror this. `ResultadoDeteccao.fonte_por_codigo: dict[str, FonteDado]` is populated by `detectar_mudancas` for every code in `codigos_vistos ∪ codigos_ausentes` — the detector tells infra everything it needs to persist a round, no separate parameter propagation.

### Resilience invariants (don't break these)

- **Counter assertion in `executar_ingestao`** — `novos + atualizados + inalterados + descartados + erros == total_recebido`. If you add a new outcome path, increment the matching counter, otherwise the assertion catches it.
- **Per-item `try/except` in the ingestion loop** — one bad alert must never stop the rest of the batch. Errors are counted, not raised.
- **Retry only on 5xx / 408 / 429 / URLError / socket.timeout** — 4xx (other than 408/429) re-raise immediately. Don't widen this.
- **Transactional outbox** — INSERTs into alerts and outbox events must happen in the same SQLite transaction. Do not split them.
- **`ChangeDetector` is pure** — no I/O, no database, no network. Do not introduce side effects.
- **`BackgroundScheduler` + `time.sleep(1)` loop** — don't switch to `BlockingScheduler`; the background variant is what gives clean `Ctrl+C` shutdown on Windows and prepares for FastAPI integration in Camada 5.
- **`max_instances=1, coalesce=True, misfire_grace_time=60`** on the scheduler job — prevents pile-up if a round runs longer than the interval.
- **UTF-8 stdout reconfigure at top of `monitor.py`** — Windows consoles default to cp1252; without this, accented place names crash `print`.
- **`escopo_geografico` is computed at ingestion time, never at query time** — changing buffer env vars (`ALERTAVIDA_BUFFER_PROXIMO_GRAUS`, etc.) only affects new alerts. Re-classification of existing rows requires running `scripts/reclassificar_escopos.py`. Don't recompute on read paths.
- **`TipoEvento` values are COBRADE subgroups, not source terminology** — after Parte A.1, the enum is `HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`. Do not introduce values that mirror a specific source's vocabulary (`RISCO_HIDROLOGICO`, `MOVIMENTOS_DE_MASSA`, etc.). Each `DataSource` implements its own mapping to these neutral values. Violating this re-couples the domain to a single source.
- **`cobrade_codigo` and `fonte_classificacao` change atomically** — any UPDATE that changes the COBRADE classification of an `Alerta` MUST update `cobrade_codigo` and `fonte_classificacao` in the same transaction. Updating one without the other breaks the audit trail and means future reclassifications (Camada 5) cannot tell direct mappings from inferred ones. No exceptions.
- **Schema check before `_migrar_banco()`** — `criar_banco()` calls `_verificar_compatibilidade_schema()` as its first instruction inside the `with sqlite3.connect(...)` block. Detects pre-A.1 schemas (tables `alertas` missing column `id` or `fonte`) and raises `SchemaIncompativelError`. Do NOT bypass this check and do NOT reorder it after `CREATE TABLE` — `_migrar_banco()` is purely additive (it ALTER TABLE ADD COLUMN for `cobrade_codigo` and `fonte_classificacao`) and would silently corrupt a C3 schema into a C3+A.2 chimera if allowed to run on a pre-A.1 database. The `IF NOT EXISTS` in `CREATE TABLE` masks the incompatibility otherwise.
- **`Alerta.fonte` is `Annotated[FonteDado, Strict()]`, never a raw string** — every `Alerta` instance carries its origin as a frozen `FonteDado` enum. `Alerta.from_dict(data, *, fonte: FonteDado)` requires `fonte` as keyword-only enum. `Alerta(fonte="CEMADEN", ...)` raises `ValidationError` (Strict blocks coerção). `aplicar_resultado_deteccao` reads `alerta.fonte.value` (not a parameter). Mismatching `Alerta.fonte` against the source that produced it is a domain invariant violation — Pydantic frozen guarantees it cannot drift after construction. Do NOT add `strict=True` to `model_config` globally — would break coerção in other fields (datetimes, other enums).
- **`ResultadoDeteccao.fonte_por_codigo` is populated for EVERY code in `codigos_vistos ∪ codigos_ausentes`** — `detectar_mudancas` builds this map from `Alerta.fonte` (for current alerts) and `AlertaSnapshot.fonte` (for codes only in `snapshots_banco`). `aplicar_resultado_deteccao` trusts this contract and uses `resultado.fonte_por_codigo[cod]` to find fonte for UPDATEs of non-event rows (visto_ultima_vez, rodadas_ausente). Breaking the contract causes `KeyError` in runtime, not silent corruption. Do NOT pass `fonte` as a separate parameter to `aplicar_resultado_deteccao` — it was removed in B.0.b precisely to eliminate this propagation.
- **`buscar_snapshots_ativos` reads `fonte` from the row via `FonteDado.from_string`** — not hardcoded from the `fonte` parameter. Safety net: if the `fonte` column in the database has an invalid value (corruption, failed migration, manual intervention), it raises `ValueError` on read instead of propagating silently into the domain. The parameter `fonte: FonteDado` filters the WHERE clause; the row's `fonte` populates `AlertaSnapshot.fonte`.
- **`DataSource.coletar()` is side-effect-free except for network reads** — no `print`, no database writes, no file system mutation. Returns `ResultadoColeta` (frozen). All persistence is the orchestrator's responsibility. Violating this re-couples ingestion to persistence and breaks the Adapter pattern.
- **Orchestrator isolates failures per source** — `executar_ingestao()` wraps each `source.coletar()` call in `try/except FalhaDeColeta`. A failed source is recorded with `falha_coleta=True` in its `RelatorioFonte` and the loop continues with the next source. Do NOT let a source failure abort the entire round. Any exception other than `FalhaDeColeta` is a bug and must propagate (no bare `except:`).
- **`RelatorioFonte` counters obey the sanity assertion per source** — `coletados == novos + atualizados + inalterados + descartados + erros`. This is the per-source version of the global assertion that existed in `executar_ingestao` pre-B. The orchestrator must assert this for each `RelatorioFonte` after the pipeline runs.
- **`CemadenSource.coletar()` captures ONLY `ValueError` when mapping each raw item to Alerta** — bugs internos (TypeError, AttributeError, KeyError) MUST propagate so they surface in diagnostics, not get silently counted as descartado. Tested by `test_propaga_typeerror_como_bug` and `test_propaga_attributeerror_como_bug` in `tests/sources/test_cemaden.py`. Do NOT widen the except clause inside the per-item loop to include other exception types.
- **Round-level failures in `CemadenSource.coletar()` (URLError, HTTPError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError) MUST be wrapped in `FalhaDeColeta(fonte=self.fonte, causa=<legível>, original=<exc>)` and raised with `from exc`** to preserve the exception chain. Do NOT let raw transport exceptions leak from `coletar()` — the orchestrator (B.2) catches `FalhaDeColeta` specifically and continues with other sources; raw exceptions would abort the whole round.

### Observability

- Logging uses stdlib `logging`. Each module defines its own logger with `logging.getLogger(__name__)`.
- Logging configuration belongs only in entrypoints (`monitor.py` and `scheduler.py`, inside `if __name__ == "__main__"`).
- `LOG_LEVEL` environment variable controls verbosity (default `INFO`).
- `DEBUG` level includes per-alert detail (municipality, state, event type, and risk level).

## Conventions

- **Language split:** domain code in **Portuguese** (`Alerta`, `Municipio`, `cod_alerta`, `nivel_risco`); infrastructure in **English** (`scheduler`, `database`, `monitor`). Don't mix.
- **Imports:** absolute, prefixed with `alertavida.` (e.g. `from alertavida.database import salvar_alerta`). Stdlib → third-party → local.
- **Type hints required** on all functions (Python 3.13).
- **Tests use mocks** for network and `time.sleep`. Anything touching the real CEMADEN endpoint or sleeping for real does not belong in the suite.
- **Integration tests** are marked with `@pytest.mark.integration` and excluded from the default run. They hit real external APIs and belong in scheduled CI jobs, not in every push.
- **Commits:** `tipo(escopo): descrição` in Portuguese. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Scope is the layer when applicable: `feat(camada-2): ...`. Keep commits small and independently revertible.
- **Error handling:** never bare `except:`. Always log with context. Decide explicitly between re-raise / retry / fallback.

## Working notes

- The SQLite DB lives at `data/alertavida.db` (gitignored, created on first run via `criar_banco()`). The path is computed relative to `database.py`, so it works regardless of CWD.
- `pyproject.toml` is the single source for deps and tooling config. No `requirements.txt`.
- `pythonpath = ["src"]` is set in pytest config, so tests import `alertavida.*` directly without needing the package installed (though `pip install -e .` is still the recommended dev setup).
- Remote: `origin` aponta para o repositório privado no GitHub (`CaioOlivieri/AlertaVida`). Use `git push origin main` para publicar.

### Fontes de dados planejadas (Camada 4)
- **CEMADEN** — ativo (Camada 1). Alertas hidrológicos em tempo real.
- **INMET** — previsto. Dados meteorológicos de estações automáticas.
- **NASA EONET** — previsto. Eventos naturais globais (incêndios, tempestades). Ingestão é global (sem filtro `bbox` na requisição); filtragem Brasil/Próximo/Internacional acontece no domínio via `EscopoGeografico`, calculada por `geographic.classificar_escopo()` na ingestão.
- **NOAA NOMADS / GFS** — previsto para camada preditiva. Formato GRIB2, 
  bibliotecas `xarray`/`cfgrib`. ECMWF open data como upgrade de qualidade.

- `uv.lock` is committed — run `uv sync --extra dev --frozen` to reproduce the exact environment. Do not use `pip install` directly.
- CI runs on every push via `.github/workflows/test.yml` (Ubuntu + Windows matrix). The `contrato CEMADEN` job runs daily at 09:00 UTC via schedule only.
- `tests/conftest.py` provides the `db_temporario` fixture (tmp SQLite + monkeypatched DB_PATH) — use it in any test that needs a real database.
- Pre-A.1 databases (Camada 2 or Camada 3 schemas) have NO migration path to the current schema. `criar_banco()` raises `SchemaIncompativelError` when it detects one. Recreating the database is the only path — A.1 introduced a structural break (PK composta → surrogate key) that SQLite does not support via `ALTER TABLE`. Document each future destructive schema change in CONTEXT.md §10 and add a matching detection rule in `_verificar_compatibilidade_schema()` if applicable.
- Parte B sub-parts (B.0/B.1/B.2) are encadeadas — each is its own Cursor prompt, commit, CI run, and recap before the next. B.0 was further split into B.0.a (domain, intentionally red CI) and B.0.b (infra, green CI) — same encadeado principle. Never start B.1 with B.0 not yet green on CI. See CONTEXT.md §3 (Parte B subdivision) and §8 (architectural decisions) for the full design rationale.

## Segurança

- Credenciais ficam em `.env` (gitignored). Nunca hardcode chaves, tokens ou senhas no código.
- `.env.example` documenta as variáveis necessárias sem valores reais — esse sim vai pro git.
- `data/alertavida.db` é gitignored — nunca commitar dados reais.
- Ao adicionar nova fonte de dados (INMET, NASA EONET, Cell Broadcast), a chave vai para `.env` primeiro, depois referenciada via `os.getenv()` no código.
- Nunca expor coordenadas precisas de infraestrutura crítica (estações CEMADEN, torres de comunicação) em logs públicos ou respostas de API sem ofuscação.
