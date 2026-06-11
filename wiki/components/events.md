status: integrated
sources: `src/alertavida/events.py`
updated: 2026-06-11

# events

In-memory EventBus (~50 lines) with subscribe/publish/handler_count. `OutboxDispatcher` processes pending events from `eventos` table (batch_size=100). Log handler registered for `AlertaCriado`, `AlertaAtualizado`, `AlertaResolvido`.

Design decision: EventBus operates on raw `dict` payloads — no domain dependency. `events.py` does NOT import `TipoEventoDetectado` from domain (preserves Dependency Inversion). Strings cross the outbox boundary as canonical representation.
