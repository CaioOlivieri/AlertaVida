# AGENT.md

Instructions for AI agents working on this codebase.

---

## What this project does

**AlertaVida** — real-time disaster alert system for the Brazilian public. Ingests data from official sources (CEMADEN, NASA EONET, INMET, INPE), detects changes, persists via transactional outbox. Python 3.13, Pydantic v2, APScheduler, SQLite, pytest, uv.

```bash
python -m alertavida.scheduler   # continuous service (Ctrl+C to stop)
python -m alertavida.monitor     # one-shot debug run
```

---

## How to run

```bash
uv sync              # install everything (dev deps included via dependency-groups)
uv sync --frozen     # reproduce exact lock
uv run pytest        # full suite, < 1s (network and time.sleep are mocked)
uv run pytest -m integration -v   # CEMADEN contract test (hits real API)
```

---

## Architecture (modules under `src/alertavida/`)

- `monitor.py` — entrypoint (46 lines): `main()` → `criar_banco()`, `executar_ingestao()`, formatted report
- `scheduler.py` — APScheduler `BackgroundScheduler`: ingest job (5min) + dispatcher job (30s)
- `database.py` — SQLite persistence: schema bootstrap, snapshots, transactional outbox
- `events.py` — in-memory EventBus + `OutboxDispatcher`
- `domain/` — `Alerta`, enums (`FonteDado`, `TipoEvento`, etc.), `ChangeDetector`, COBRADE mapper, geographic classifier
- `ingestion/orquestrador.py` — `executar_ingestao()`: collects → detects → persists per source
- `sources/` — `DataSource` ABC, `CemadenSource`, `ResultadoColeta`, `FalhaDeColeta`

---

## Rules

- Domain code in Portuguese (`Alerta`, `cod_alerta`, `nivel_risco`); infrastructure in English (`scheduler`, `database`)
- Type hints required on all functions
- Never bare `except:`. Log with context. Decide: re-raise, retry, or fallback
- Tests mock network and `time.sleep` — suite must run in < 1s
- Commits: `tipo(escopo): descrição` in Portuguese. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Never modify `src/`, `tests/`, `scripts/`, `.github/`, `pyproject.toml`, `README.md`, `uv.lock`, `.gitignore` without explicit ask

---

## Knowledge base

This repo maintains a wiki in `./wiki/` (LLM-Wiki format). Before any architecture change or non-trivial work, read:

1. `wiki/_integration-state.md` — single source of truth on what is wired
2. `wiki/_schema.md` — discipline rules for this wiki

Before touching the ingestion pipeline (`sources/`, `ingestion/`, `monitor.py`, `scheduler.py`, `database.py`):
3. `wiki/patterns/resilience-invariants.md` — 20 invariants, must not break any

Discipline rules: only assert test/pipeline behavior based on real execution output (`uv run pytest`, logs in `wiki/raw/`) — never by inference. Every new architectural decision requires a page in `wiki/decisions/` + updating `_integration-state.md` when wiring changes. When learning something durable, do ingest: update the page.
