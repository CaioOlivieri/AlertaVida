status: integrated
sources: `src/alertavida/events.py`
updated: 2026-07-02

# events

In-memory EventBus (~50 lines) with subscribe/publish/handler_count. `OutboxDispatcher` processes pending events from `eventos` table (batch_size=100). Log handler registered for `AlertaCriado`, `AlertaAtualizado`, `AlertaResolvido`.

Design decision: EventBus operates on raw `dict` payloads — no domain dependency. `events.py` does NOT import `TipoEventoDetectado` from domain (preserves Dependency Inversion). Strings cross the outbox boundary as canonical representation.

## `eventos.tentativas` is not a real retry counter (yet)

`processar_pendentes` sets `processado_em` and increments `tentativas` in the **same** statement, even when a handler raises (documented no-redelivery policy — a failing handler logs the error but the event is never reprocessed). In practice the column can only ever hold `0` or `1`; it does not track actual retry attempts.

This is intentional for now, not a bug: redelivery isn't implemented. The column only becomes meaningful if/when a future layer (likely Camada 8, notification) introduces real retry + dead-letter semantics — at that point `tentativas` would increment across multiple genuine attempts before giving up. Until then, treat it as equivalent to `processado_em IS NOT NULL` (maintainability review #18 B).
