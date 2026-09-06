status: blocked
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-09-06 (issue #88)

# Layer 8: Notification Engine (blocked)

- **Short term:** Web Push (native PWA)
- **Medium term:** WhatsApp Business API, Email (SMTP), Telegram
- **Long term:** Cell Broadcast (via partnership with carriers/government)

## Warning for whoever writes the first real handler here (issue #88 finding)

`OutboxDispatcher.processar_pendentes` (see [[components/events]]) holds its write-lock transaction open across every `publish()` call in a batch, up to `batch_size=100`. That's invisible today because the only subscribed handler (`log_handler`) does no I/O. A network handler registered here will not have that luxury: a slow or blocked call anywhere in the batch holds the lock for every event after it, and a full 100-event batch of network calls is long enough to trip the ingestion job's own `busy_timeout=5000` on a concurrent connection.

This is not something to route around by writing straight to the DB from the handler thread — it's a signal to design this layer's dispatch (batching, async delivery, or backpressure) with that lock lifetime in mind before the first production notification ships, not after it causes the first ingestion stall.

`severidade` on `domain/incidente.py` (currently `orphan-in-practice` — see `wiki/_integration-state.md`) is also expected to feed this layer once wired.
