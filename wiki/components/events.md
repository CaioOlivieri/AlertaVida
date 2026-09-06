status: integrated
sources: `src/alertavida/events.py`
updated: 2026-09-06 (issue #88)

# events

In-memory EventBus (~50 lines) with subscribe/publish/handler_count. `OutboxDispatcher` processes pending events from `eventos` table (batch_size=100).

Design decision: EventBus operates on raw `dict` payloads — no domain dependency. `events.py` does NOT import `TipoEventoDetectado` from domain (preserves Dependency Inversion). Strings cross the outbox boundary as canonical representation.

## Handler composition lives in a factory, not at import time (issue #24)

`criar_bus_producao() -> EventBus` returns a **fresh** bus with `log_handler` subscribed to the four event types (`AlertaCriado`, `AlertaAtualizado`, `AlertaResolvido`, `AlertaReativado`). The module has no mutable module-level state: importing `events` registers nothing, so import order carries no meaning and nothing leaks between callers.

`scheduler.py` is the only composition root — it calls the factory once in `agendar_ingestao()` and injects the bus into `OutboxDispatcher`. `monitor.py` (one-shot debug run) deliberately gets no dispatcher and no handlers; before #24 that was true only by accident of not importing `events`, now it is a consequence of the design. Tests build whatever bus they need (`EventBus()` directly, or the factory when asserting the production handler set).

Since issue #88, the same `log_handler` is also subscribed to all five `Incidente*` types, derived from `database._TIPOS_EVENTO_INCIDENTE` so a future sixth type can't silently diverge from what the outbox actually emits. Before #88 these events reached `OutboxDispatcher.publish` with no handler at all — `processar_pendentes` still marked them `processado_em` (no handler means nothing to fail), so Camada 5 ran with zero log trace of any Incidente lifecycle transition.

## The dispatcher holds its write lock across the whole batch (issue #88 finding, not fixed here)

`OutboxDispatcher.processar_pendentes` opens its transaction at the first `UPDATE ... SET processado_em` and keeps it open through every `publish()` call in the batch, committing only once at the end. Measured with a handler that writes via a second connection mid-batch: the first write succeeds, every subsequent one in the same batch fails with `database is locked`.

With `log_handler` this is immaterial — no I/O, microseconds per event. It becomes a real constraint the moment a handler does network I/O (see [[projects/layer-8-notification]]): a 100-event batch would hold the write lock for up to 100 sequential calls, and the ingestion job's own `busy_timeout=5000` would start tripping. **Not fixed here** — changing it changes delivery semantics: today a mid-batch crash rolls back and redelivers the whole batch (at-least-once *per batch*, not per event). Fixing it is its own issue.

## `eventos.tentativas` is not a real retry counter (yet)

`processar_pendentes` sets `processado_em` and increments `tentativas` in the **same** statement, even when a handler raises (documented no-redelivery policy — a failing handler logs the error but the event is never reprocessed). In practice the column can only ever hold `0` or `1`; it does not track actual retry attempts.

This is intentional for now, not a bug: redelivery isn't implemented. The column only becomes meaningful if/when a future layer (likely Camada 8, notification) introduces real retry + dead-letter semantics — at that point `tentativas` would increment across multiple genuine attempts before giving up. Until then, treat it as equivalent to `processado_em IS NOT NULL` (maintainability review #18 B).
