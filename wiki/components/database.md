status: integrated
sources: `src/alertavida/database.py`
updated: 2026-07-28

# database

SQLite persistence layer. Key contracts:

- `db_path()` — resolves the DB path per call from `ALERTAVIDA_DB_PATH`, falling back to the packaged `data/alertavida.db` when unset or blank (same pattern as `ALERTAVIDA_BUFFER_PROXIMO_GRAUS`). It is a function, not an import-time constant, so a later env change is honoured and importing the module has **no filesystem side effect** — the parent-dir `mkdir` moved into `conectar()` (issue #22 item A). `rm -rf data/ && uv run pytest` now leaves nothing behind.
- `conectar()` — `@contextlib.contextmanager` that opens a connection at `db_path()` (creating the parent dir), with `PRAGMA busy_timeout=5000` and `PRAGMA foreign_keys=ON` set **before** the transaction block (foreign-key enforcement is per-connection and a no-op inside a transaction — issue #22 item B), `yield`s it from *inside* a `with conexao:` block, and closes it in `finally`. `sqlite3.Connection` used as a context manager only controls the **transaction** (commit on success / rollback on exception) — it never closes the connection, so a naive `contextlib.closing()` swap would silently drop the rollback that keeps `aplicar_resultado_deteccao` atomic (issue #40). Because the `yield` sits inside the transactional `with`, an exception raised in the caller's `with conectar() as conexao:` block is thrown back into that inner `with conexao:` before the connection closes — commit/rollback semantics are unchanged, the connection just no longer leaks to the GC. Call sites are unchanged: `with conectar() as conexao:`.
- `criar_banco()` — idempotent schema bootstrap. Enables `PRAGMA journal_mode=WAL`, calls `_verificar_compatibilidade_schema()` first, then `CREATE TABLE IF NOT EXISTS`, then `_migrar_banco()` (additive ALTER TABLE). `eventos` is created with `FOREIGN KEY (agregado_id) REFERENCES alertas(id)` (`ON DELETE NO ACTION` — the outbox is an audit trail) plus the child-key index `idx_eventos_agregado_id`.
- `_verificar_compatibilidade_schema()` — two rejection paths, both raising `SchemaIncompativelError` with distinct messages: a pre-A.1 `alertas` table (missing `id`/`fonte`), and an `eventos` table that exists **without** the FK (pre-#22 database). Neither has an automatic migration — SQLite adds neither a surrogate PK nor a FK via `ALTER TABLE`, and `_migrar_banco()` stays additive-only. See [[decisions/foreign-key-eventos-agregado-id]].
- `buscar_snapshots(fonte: FonteDado)` — reads all alert snapshots (any status) with safety net via `FonteDado.from_string()`.
- `aplicar_resultado_deteccao(resultado, alertas_por_codigo, agora)` — single transaction: INSERT/UPDATE alerts + INSERT outbox events. UPDATE branches (ATUALIZADO/REATIVADO/RESOLVIDO) use `UPDATE … RETURNING id` via the `_executar_retornando_id` helper — one query instead of UPDATE-then-SELECT. ATUALIZADO and REATIVADO share one branch (REATIVADO adds `status_interno = 'ATIVO'`).

DB defaults to `data/alertavida.db` (gitignored), overridable via `ALERTAVIDA_DB_PATH`; the default is computed relative to `database.py`, so it works regardless of CWD. `pythonpath = ["src"]` in pytest config.
