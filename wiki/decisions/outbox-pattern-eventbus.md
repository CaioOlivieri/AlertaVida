status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# Outbox Pattern + In-Memory EventBus

Transactional outbox: INSERT into `alertas` and `eventos` in the same SQLite transaction — eliminates dual-write. Natural path to Postgres LISTEN/NOTIFY and later message broker.

In-memory EventBus (~50 lines, no library) with subscribe/publish/handler_count. Replaceable by broker when needed. `OutboxDispatcher` processes pending events every 30s.

`events.py` keeps raw strings (no domain dependency) — messages cross process boundary via outbox SQL where strings are canonical representation.
