status: implemented
sources: [[decisions/decision-record]]
updated: 2026-07-30

# Outbox Pattern + In-Memory EventBus

Transactional outbox: INSERT into `alertas` and `eventos` in the same SQLite transaction — eliminates dual-write. Natural path to Postgres LISTEN/NOTIFY and later message broker.

In-memory EventBus (~50 lines, no library) with subscribe/publish/handler_count. Replaceable by broker when needed. `OutboxDispatcher` processes pending events every 30s.

`events.py` keeps raw strings (no domain dependency) — messages cross process boundary via outbox SQL where strings are canonical representation.

## The bus is built by a factory, not exported as a singleton (issue #24, 2026-07-30)

Camada 3 shipped `events.py` ending in a module-level `bus = EventBus()` plus four import-time `subscribe()` calls; `scheduler.py` imported that object. Harmless while every handler only logs — a liability the day a handler has a real side effect (push, SMS, e-mail): import order would start deciding what is registered, tests touching the bus would leak state across the suite, and there would be no seam to wire different handler sets per environment.

Replaced by `criar_bus_producao() -> EventBus` (composition happens inside the factory) with `scheduler.py` calling it once and injecting the result into `OutboxDispatcher`. `events.py` now holds only `EventBus`, `OutboxDispatcher`, `log_handler` and the factory — no mutable module-level state.

**Done deliberately before Camada 8, which has not started** — [[projects/layer-8-notification]] remains `status: blocked` and this refactor does not unblock it. The issue itself proposed deferring until kickoff; the maintainer chose to bring it forward because the refactor is small and self-contained (`scheduler.py` was the singleton's only importer in the whole repo, and no test ever imported it), and because doing it while the bus is still "lukewarm" — log handlers only — is cheaper and safer than doing it mid-Camada-8 with real side-effecting handlers already in play. See [[components/events]].
