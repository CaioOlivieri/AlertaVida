status: integrated
sources: `src/alertavida/scheduler.py`
updated: 2026-06-11

# scheduler

Production service entrypoint (`python -m alertavida.scheduler`). Two APScheduler jobs:

- **ingestao** — every 5 min, `max_instances=1`, `coalesce=True`, `misfire_grace_time=60`. Calls `executar_ingestao([CemadenSource()])`.
- **dispatcher** — every 30s, processes pending outbox events via `OutboxDispatcher`.

`agendar_ingestao()` calls `criar_banco()` once at startup (not per round). Uses `BackgroundScheduler` + `time.sleep(1)` for clean `Ctrl+C` shutdown. Listener `EVENT_JOB_ERROR` keeps service alive if one round fails.
