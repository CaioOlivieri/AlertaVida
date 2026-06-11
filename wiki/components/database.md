status: integrated
sources: `src/alertavida/database.py`
updated: 2026-06-11

# database

SQLite persistence layer. Key contracts:

- `criar_banco()` — idempotent schema bootstrap. Calls `_verificar_compatibilidade_schema()` first (raises `SchemaIncompativelError` on pre-A.1 schemas), then `CREATE TABLE IF NOT EXISTS`, then `_migrar_banco()` (additive ALTER TABLE).
- `buscar_snapshots_ativos(fonte: FonteDado)` — reads current alert snapshots with safety net via `FonteDado.from_string()`.
- `aplicar_resultado_deteccao(resultado, alertas_por_codigo, agora)` — single transaction: INSERT/UPDATE alerts + INSERT outbox events.

DB lives at `data/alertavida.db` (gitignored). Path computed relative to `database.py`, works regardless of CWD. `pythonpath = ["src"]` in pytest config.
