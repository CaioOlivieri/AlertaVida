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
uv run pytest                          # 88 testes, sem integração (padrão)
uv run pytest -m integration -v        # só teste de contrato CEMADEN (bate na API real)
uv run pytest tests/test_monitor.py::test_montar_alerta_descarta_sem_codigo  # teste único
```
The full suite must run in **< 1 second** — `time.sleep` is mocked everywhere. Integration tests are excluded by default via `addopts = ["-m", "not integration"]` in `pyproject.toml`.

## Architecture

The system is built **layer by layer** following the roadmap in `CONTEXT.md` §3. Each layer must be functional and tested before moving on. Current state:

- **Camada 1 (Ingestão)** — DONE. `monitor.py` fetches from CEMADEN with retry+backoff, `database.py` persists to SQLite with dedup by `cod_alerta` PK, `scheduler.py` wraps everything in APScheduler. Schema compatibility is enforced explicitly in `criar_banco()` via `_verificar_compatibilidade_schema()`, which raises `SchemaIncompativelError` on pre-A.1 schemas (missing `id` or `fonte` columns). See CONTEXT.md §8 row "Verificação explícita de schema antes de `_migrar_banco()`".
- **Camada 2 (Domínio)** — DONE. `src/alertavida/domain/` has frozen Pydantic v2 models (`Alerta`, `Municipio`, `Coordenadas`) and enums (`NivelRisco`, `TipoEvento`) fully integrated with ingestion and persistence.
- **Camada 3 (Detecção de Mudanças e Eventos)** — DONE. Pure `ChangeDetector`, transactional Outbox Pattern, in-memory EventBus, and `OutboxDispatcher` scheduled every 30 seconds are implemented and covered by 88 tests.
- **Camada 4 (Ingestão Multi-Fonte)** — in progress. Subdivided into four parts (defined 2026-05-05, see CONTEXT.md §3): Parte A.1 (destructive refactor of domain + database: surrogate key, `cod_alerta` as TEXT, `municipio` optional, `coordenadas` required, `EscopoGeografico` enum, `TipoEvento` refactored to COBRADE subgroups, `geographic.py`, `scripts/reclassificar_escopos.py`) — DONE 2026-05-09; Parte A.2 (additive: `cobrade.py` module, `cobrade_codigo` field, `FonteClassificacao` enum, new nullable columns) — DONE 2026-05-11; Parte B (CemadenSource as `DataSource`, refactor `monitor.py` into orchestrator) — re-subdivided 2026-05-12 into B.0 (add `fonte` to `Alerta` model) + B.1 (`sources/base.py` with `DataSource` ABC, `ResultadoColeta`, `FalhaDeColeta`; `sources/cemaden.py` extracted from `monitor.py`; contract test infrastructure) + B.2 (`ingestao/orquestrador.py` with `executar_ingestao`, `RelatorioFonte`, `RelatorioIngestao`; `monitor.py` reduced to entrypoint). Parte C (NasaEonetSource). Execution order: A.1 → A.2 → B.0 → B.1 → B.2 → C. A.1 is destructive (PK shape, enum values change); A.2 is purely additive; B.0/B.1/B.2 are encadeados (each commit + CI verde + recap before the next). Do not merge any of these in the same commit.
- **Camadas 5–8** — blocked. Don't pre-build for them. The eventual target structure (`ingestion/`, `events/`, `sources/`, `correlation/`, `api/`, `notifications/` subpackages) is documented in `CONTEXT.md` §4 but migration happens **as each layer is worked on**, not upfront.

### Key flow (current)

`scheduler.agendar_ingestao()` → APScheduler (`ingestao` job every 5 min + `dispatcher` job every 30s) → `monitor.executar_ingestao()` → `fetch_alertas_com_retry()` (urllib + 4 attempts, 2/4/8s backoff, no retry on 4xx except 408/429) → `normalize_alert_list()` → `montar_alerta()` returns `Alerta` → `buscar_snapshots_ativos()` → `detectar_mudancas()` → `aplicar_resultado_deteccao()` (single transaction: alerts + outbox events).

### Domain layer (Camada 2)

`src/alertavida/domain/` contains frozen Pydantic v2 models (`Alerta`, `Municipio`, `Coordenadas`) and enums (`NivelRisco`, `TipoEvento`, and — after Parte A.2 of Camada 4 — `FonteClassificacao`). `Alerta.from_dict()` is the canonical entry point: it accepts the raw source-style dict (with field-name fallbacks) and raises `ValueError` on missing/invalid required fields. After Parte A.1 of Camada 4: `TipoEvento` values are COBRADE subgroups (`HIDROLOGICO`, `GEOLOGICO`, `METEOROLOGICO`, `CLIMATOLOGICO`, `BIOLOGICO`, `INDETERMINADO`); `TipoEvento.from_string` returns `INDETERMINADO` for unknowns; `NivelRisco.from_string` raises. Both normalize accents/case before matching. After Parte A.2: `Alerta` carries `cobrade_codigo: str | None` (subgroup-level only — e.g. `1.2.0.0.0` for hydrological, `1.1.3.0.0` for mass movements) and `fonte_classificacao: FonteClassificacao` (DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA) registering provenance of the classification. Mapping logic lives in `domain/cobrade.py`.

Integration with `monitor.py`/`database.py` is complete: `montar_alerta()` returns `Alerta`, and `database.py` persists through `aplicar_resultado_deteccao()`.

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
- **`Alerta.fonte` consistent with `alertas.fonte` column** — after B.0, every `Alerta` instance carries its origin as a frozen field. `aplicar_resultado_deteccao()` reads `Alerta.fonte` to persist; do NOT pass `fonte` as a separate parameter (removed in B.0). `buscar_snapshots_ativos(fonte: str)` keeps the parameter because it queries by source. Mismatching `Alerta.fonte` against the source that produced it is a domain invariant violation — Pydantic frozen guarantees it cannot drift after construction.
- **`DataSource.coletar()` is side-effect-free except for network reads** — no `print`, no database writes, no file system mutation. Returns `ResultadoColeta` (frozen). All persistence is the orchestrator's responsibility. Violating this re-couples ingestion to persistence and breaks the Adapter pattern.
- **Orchestrator isolates failures per source** — `executar_ingestao()` wraps each `source.coletar()` call in `try/except FalhaDeColeta`. A failed source is recorded with `falha_coleta=True` in its `RelatorioFonte` and the loop continues with the next source. Do NOT let a source failure abort the entire round. Any exception other than `FalhaDeColeta` is a bug and must propagate (no bare `except:`).
- **`RelatorioFonte` counters obey the sanity assertion per source** — `coletados == novos + atualizados + inalterados + descartados + erros`. This is the per-source version of the global assertion that existed in `executar_ingestao` pre-B. The orchestrator must assert this for each `RelatorioFonte` after the pipeline runs.

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
- Parte B sub-parts (B.0/B.1/B.2) are encadeadas — each is its own Cursor prompt, commit, CI run, and recap before the next. Never start B.1 with B.0 not yet green on CI. See CONTEXT.md §3 (Parte B subdivision) and §8 (architectural decisions) for the full design rationale.

## Segurança

- Credenciais ficam em `.env` (gitignored). Nunca hardcode chaves, tokens ou senhas no código.
- `.env.example` documenta as variáveis necessárias sem valores reais — esse sim vai pro git.
- `data/alertavida.db` é gitignored — nunca commitar dados reais.
- Ao adicionar nova fonte de dados (INMET, NASA EONET, Cell Broadcast), a chave vai para `.env` primeiro, depois referenciada via `os.getenv()` no código.
- Nunca expor coordenadas precisas de infraestrutura crítica (estações CEMADEN, torres de comunicação) em logs públicos ou respostas de API sem ofuscação.
