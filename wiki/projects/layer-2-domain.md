status: done
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-06-11

# Layer 2: Domain Modeling

Pydantic v2 frozen models and enums, `src layout` refactor.

**Delivered in 3 parts:**
- Part 1 — src layout, `pyproject.toml`, `alertavida` package 0.2.0
- Part 2 — Pydantic models (`Alerta`, `Municipio`, `Coordenadas`, enums), 68 tests
- Part 3 — Integration: `montar_alerta()` returns `Alerta`, `database.py` receives `Alerta`

Now fully integrated with ingestion and persistence.
