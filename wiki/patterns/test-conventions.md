status: integrated
sources: [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-06-14

# Test Conventions

- **Tests use mocks** for network and `time.sleep`. Anything touching the real CEMADEN endpoint or sleeping for real does not belong in the default suite.
- **Integration tests** marked with `@pytest.mark.integration`, excluded from the default run (`addopts = ["-m", "not integration"]` in `pyproject.toml`). They hit real external APIs and belong in scheduled CI jobs.
- Full suite must run in **< 1 second** — `time.sleep` is mocked everywhere.
- `tests/conftest.py` provides `db_temporario` fixture (tmp SQLite + monkeypatched DB_PATH) — use it in any test that needs a real database.
- `pythonpath = ["src"]` in pytest config allows importing `alertavida.*` directly without package installed.
- `uv run pytest` is the canonical test command. `uv run pytest -m integration -v` for contract tests.
- Contract test infrastructure: `tests/sources/contrato.py` with `verificar_contrato_data_source(source_factory)` parametrized across all `DataSource` implementations.
- `FakeDataSource` in `tests/fixtures/sources_fake.py` implements the real `DataSource` interface — not `unittest.mock.Mock` (which hides signature errors).
- **Test data location (current reality):** CEMADEN tests use inline dicts inside `tests/sources/test_cemaden.py` (the `tests/fixtures/cemaden/` directory mentioned in the early decision record was never created). EONET tests use synthetic builders in `tests/fixtures/eonet/`. Legacy schema fixtures (pre-A.1/A.2 DBs) live in `tests/fixtures/schemas_legados.py`. Real captured payloads stay gitignored under `data/samples/`.
