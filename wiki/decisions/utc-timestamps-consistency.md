status: implemented
updated: 2026-06-11

# UTC Timestamps Consistency

All timestamp writes in the system use `datetime.now(UTC)` aware datetime —
`criado_em` in the outbox already was UTC-aware ISO, but `processado_em` in
the `OutboxDispatcher` used `datetime.now()` naive local time, creating
inconsistent timezones in the same table.

Fixed: `processado_em` now uses `datetime.now(UTC)`. No functional change
for scheduling — the dispatcher only checks `IS NULL` to find pending events.
