status: integrated
sources: [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-06-11

# Code Conventions

- **Language split:** domain code in Portuguese (`Alerta`, `Municipio`, `cod_alerta`, `nivel_risco`); infrastructure in English (`scheduler`, `database`, `monitor`).
- **Imports:** absolute, prefixed with `alertavida.` (e.g. `from alertavida.database import salvar_alerta`). Order: stdlib → third-party → local.
- **Type hints required** on all functions (Python 3.13).
- **Naming:** variables/functions: `snake_case`, classes: `PascalCase`, constants: `UPPER_SNAKE_CASE`.
- **Error handling:** never bare `except:`. Always log with context. Decide explicitly between re-raise / retry / fallback.

## Observability

- Logging uses stdlib `logging`. Each module defines its own logger with `logging.getLogger(__name__)`.
- Logging configuration belongs only in entrypoints (`monitor.py` and `scheduler.py`, inside `if __name__ == "__main__"`).
- `LOG_LEVEL` environment variable controls verbosity (default `INFO`).
- `DEBUG` level includes per-alert detail (municipality, state, event type, and risk level).

## Technical principles

1. TDD when possible — write the test before the function, especially for AI-generated code.
2. Unit tests at every layer — no tests means no scale.
3. Structured logging from the start — know what the system does in production.
4. Configuration via environment variables — never hardcoded. Use `.env` + `pydantic-settings` (future).
5. Type hints on every function.
6. Pydantic for all external data I/O — validation at the system boundary.
7. Frequent descriptive commits — every meaningful change is one commit.
8. Minimal but present README.
9. Mocks in network/time tests — suite must run in < 1 second.
10. Data honesty — the domain model faithfully represents what the source provides, without inventing precision. Optional fields when the source delivers sporadically, required when guaranteed. Enrichment of missing data is the sources layer's (Camada 4) responsibility, not the domain layer's (Camada 2).
