status: integrated
sources: `src/alertavida/database.py`
updated: 2026-07-21

# database

SQLite persistence layer. Key contracts:

- `conectar()` — `@contextlib.contextmanager` that opens a connection with `PRAGMA busy_timeout=5000`, `yield`s it from *inside* a `with conexao:` block, and closes it in `finally`. `sqlite3.Connection` used as a context manager only controls the **transaction** (commit on success / rollback on exception) — it never closes the connection, so a naive `contextlib.closing()` swap would silently drop the rollback that keeps `aplicar_resultado_deteccao` atomic (issue #40). Because the `yield` sits inside the transactional `with`, an exception raised in the caller's `with conectar() as conexao:` block is thrown back into that inner `with conexao:` before the connection closes — commit/rollback semantics are unchanged, the connection just no longer leaks to the GC. Call sites are unchanged: `with conectar() as conexao:`.
- `criar_banco()` — idempotent schema bootstrap. Enables `PRAGMA journal_mode=WAL`, calls `_verificar_compatibilidade_schema()` first (raises `SchemaIncompativelError` on pre-A.1 schemas), then `CREATE TABLE IF NOT EXISTS`, then `_migrar_banco()` (additive ALTER TABLE).
- `buscar_snapshots(fonte: FonteDado)` — reads all alert snapshots (any status) with safety net via `FonteDado.from_string()`.
- `aplicar_resultado_deteccao(resultado, alertas_por_codigo, agora)` — single transaction: INSERT/UPDATE alerts + INSERT outbox events. UPDATE branches (ATUALIZADO/REATIVADO/RESOLVIDO) use `UPDATE … RETURNING id` via the `_executar_retornando_id` helper — one query instead of UPDATE-then-SELECT. ATUALIZADO and REATIVADO share one branch (REATIVADO adds `status_interno = 'ATIVO'`).

DB lives at `data/alertavida.db` (gitignored). Path computed relative to `database.py`, works regardless of CWD. `pythonpath = ["src"]` in pytest config.
