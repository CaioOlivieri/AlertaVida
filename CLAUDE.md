# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

`CONTEXT.md` is the project's living document — it tracks every architectural decision, the 7-layer roadmap, and a dated changelog. **Read it before any non-trivial work** and update it (sections 8 and 10) whenever a new architectural decision is made or a layer milestone is reached.

## Commands

Install (editable mode + dev deps):
```powershell
pip install -e ".[dev]"
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
python -m pytest -v               # all tests
python -m pytest tests/test_monitor.py::test_montar_alerta_descarta_sem_codigo  # single test
```
The full suite must run in **< 1 second** — `time.sleep` is mocked everywhere it appears. If a test starts taking real time, that's a regression.

## Architecture

The system is built **layer by layer** following the roadmap in `CONTEXT.md` §3. Each layer must be functional and tested before moving on. Current state:

- **Camada 1 (Ingestão)** — DONE. `monitor.py` fetches from CEMADEN with retry+backoff, `database.py` persists to SQLite with dedup by `cod_alerta` PK, `scheduler.py` wraps everything in APScheduler.
- **Camada 2 (Domínio)** — Part 1 (src layout) is done. Part 2 (Pydantic models in `src/alertavida/domain/`) is implemented with 68 tests passing; revisions tracked in issue #1, blocked by investigation in issue #2. Part 3 (wiring `montar_alerta()` → `Alerta`, `database.py` accepting `Alerta`) is the next blocking work after #1 and #2 close.
- **Camadas 3–7** — blocked. Don't pre-build for them. The eventual target structure (`ingestion/`, `events/`, `sources/`, `api/`, `notifications/` subpackages) is documented in `CONTEXT.md` §4 but migration happens **as each layer is worked on**, not upfront.

### Key flow (current)

`scheduler.agendar_ingestao()` → APScheduler job every 5 min → `monitor.executar_ingestao()` → `fetch_alertas_com_retry()` (urllib + 4 attempts, 2/4/8s backoff, no retry on 4xx except 408/429) → `normalize_alert_list()` → for each item: `montar_alerta()` (pure dict→dict mapper) → `alerta_existe()` / `salvar_alerta()` against `data/alertavida.db`.

### Domain layer (Camada 2)

`src/alertavida/domain/` contains frozen Pydantic v2 models (`Alerta`, `Municipio`, `Coordenadas`) and enums (`NivelRisco`, `TipoEvento`). `Alerta.from_dict()` is the canonical entry point: it accepts the raw CEMADEN-style dict (with field-name fallbacks) and raises `ValueError` on missing/invalid required fields. `TipoEvento.from_string` returns `OUTROS` for unknowns; `NivelRisco.from_string` raises. Both normalize accents/case before matching.

The integration with `monitor.py`/`database.py` is **not yet wired** — `montar_alerta()` still returns a dict, `salvar_alerta()` still takes a dict. Part 3 of Camada 2 will replace both.

### Resilience invariants (don't break these)

- **Counter assertion in `executar_ingestao`** — `novos + ja_existentes + descartados + erros == total_recebido`. If you add a new outcome path, increment the matching counter, otherwise the assertion catches it.
- **Per-item `try/except` in the ingestion loop** — one bad alert must never stop the rest of the batch. Errors are counted, not raised.
- **Retry only on 5xx / 408 / 429 / URLError / socket.timeout** — 4xx (other than 408/429) re-raise immediately. Don't widen this.
- **`BackgroundScheduler` + `time.sleep(1)` loop** — don't switch to `BlockingScheduler`; the background variant is what gives clean `Ctrl+C` shutdown on Windows and prepares for FastAPI integration in Camada 5.
- **`max_instances=1, coalesce=True, misfire_grace_time=60`** on the scheduler job — prevents pile-up if a round runs longer than the interval.
- **UTF-8 stdout reconfigure at top of `monitor.py`** — Windows consoles default to cp1252; without this, accented place names crash `print`.

## Conventions

- **Language split:** domain code in **Portuguese** (`Alerta`, `Municipio`, `cod_alerta`, `nivel_risco`); infrastructure in **English** (`scheduler`, `database`, `monitor`). Don't mix.
- **Imports:** absolute, prefixed with `alertavida.` (e.g. `from alertavida.database import salvar_alerta`). Stdlib → third-party → local.
- **Type hints required** on all functions (Python 3.13).
- **Tests use mocks** for network and `time.sleep`. Anything touching the real CEMADEN endpoint or sleeping for real does not belong in the suite.
- **Commits:** `tipo(escopo): descrição` in Portuguese. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Scope is the layer when applicable: `feat(camada-2): ...`. Keep commits small and independently revertible.
- **Error handling:** never bare `except:`. Always log with context. Decide explicitly between re-raise / retry / fallback.

## Working notes

- The SQLite DB lives at `data/alertavida.db` (gitignored, created on first run via `criar_banco()`). The path is computed relative to `database.py`, so it works regardless of CWD.
- `pyproject.toml` is the single source for deps and tooling config. No `requirements.txt`.
- `pythonpath = ["src"]` is set in pytest config, so tests import `alertavida.*` directly without needing the package installed (though `pip install -e .` is still the recommended dev setup).
- Remote: `origin` aponta para o repositório privado no GitHub (`CaioOlivieri/AlertaVida`). Use `git push origin main` para publicar.

### Fontes de dados planejadas (Camadas 3–4)
- **CEMADEN** — ativo (Camada 1). Alertas hidrológicos em tempo real.
- **INMET** — previsto. Dados meteorológicos de estações automáticas.
- **NASA EONET** — previsto. Eventos naturais globais (incêndios, tempestades).
- **NOAA NOMADS / GFS** — previsto para camada preditiva. Formato GRIB2, 
  bibliotecas `xarray`/`cfgrib`. ECMWF open data como upgrade de qualidade.

## Segurança

- Credenciais ficam em `.env` (gitignored). Nunca hardcode chaves, tokens ou senhas no código.
- `.env.example` documenta as variáveis necessárias sem valores reais — esse sim vai pro git.
- `data/alertavida.db` é gitignored — nunca commitar dados reais.
- Ao adicionar nova fonte de dados (INMET, NASA EONET, Cell Broadcast), a chave vai para `.env` primeiro, depois referenciada via `os.getenv()` no código.
- Nunca expor coordenadas precisas de infraestrutura crítica (estações CEMADEN, torres de comunicação) em logs públicos ou respostas de API sem ofuscação.