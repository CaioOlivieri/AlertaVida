status: integrated
sources: `src/alertavida/database.py`
updated: 2026-06-14

# database

SQLite persistence layer. Key contracts:

- `conectar()` — opens a connection with `PRAGMA busy_timeout=5000` for multi-thread contention safety.
- `criar_banco()` — idempotent schema bootstrap. Enables `PRAGMA journal_mode=WAL`, calls `_verificar_compatibilidade_schema()` first (raises `SchemaIncompativelError` on pre-A.1 schemas), then `CREATE TABLE IF NOT EXISTS`, then `_migrar_banco()` (additive ALTER TABLE).
- `buscar_snapshots(fonte: FonteDado)` — reads all alert snapshots (any status) with safety net via `FonteDado.from_string()`.
- `aplicar_resultado_deteccao(resultado, alertas_por_codigo, agora)` — single transaction: INSERT/UPDATE alerts + INSERT outbox events. UPDATE branches (ATUALIZADO/REATIVADO/RESOLVIDO) use `UPDATE … RETURNING id` via the `_executar_retornando_id` helper — one query instead of UPDATE-then-SELECT. ATUALIZADO and REATIVADO share one branch (REATIVADO adds `status_interno = 'ATIVO'`).

DB lives at `data/alertavida.db` (gitignored). Path computed relative to `database.py`, works regardless of CWD. `pythonpath = ["src"]` in pytest config.
