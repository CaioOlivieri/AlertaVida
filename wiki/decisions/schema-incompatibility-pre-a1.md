status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# Schema Incompatibility Detection for Pre-A.1

`criar_banco()` calls `_verificar_compatibilidade_schema()` as its first instruction inside the `with sqlite3.connect(...)` block. Detects pre-A.1 schemas (tables missing `id` or `fonte` columns) and raises `SchemaIncompativelError`.

The C3 → A.1 migration never existed (composite PK → surrogate key is not ALTER TABLE-able in SQLite). Without this check, post-A.2 `_migrar_banco()` would add COBRADE columns to C3 databases, creating C3+A.2 chimera. Verification aborts with clear error asking to recreate the database.

Decision Path 3 of the 2026-05-12 architectural discussion.
