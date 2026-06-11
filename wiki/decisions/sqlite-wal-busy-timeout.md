status: implemented
updated: 2026-06-11

# SQLite WAL + Busy Timeout

The scheduler runs two jobs in separate threads that both write to the same
SQLite database: ingestion (5min) and dispatcher (30s). Without WAL mode and
an explicit busy timeout, contention can cause `database is locked` errors.

Changes:
- New public helper `conectar()` opens a connection and sets
  `PRAGMA busy_timeout=5000` (5s wait before giving up).
- All internal `sqlite3.connect(DB_PATH)` calls replaced by `conectar()`.
- `criar_banco()` enables `PRAGMA journal_mode=WAL` at bootstrap (persistent
  per-file property).
- `events.py` now imports `conectar` instead of `DB_PATH`.

WAL allows concurrent reads while a write is in progress; busy_timeout avoids
immediate failure when a write lock is briefly held by the other thread.
