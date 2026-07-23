status: integrated
sources: `src/alertavida/scheduler.py`
updated: 2026-07-22

# scheduler

Production service entrypoint (`python -m alertavida.scheduler`). Two APScheduler jobs:

- **ingestao** — every 5 min (immediate first run via `next_run_time=now`), `max_instances=1`, `coalesce=True`, `misfire_grace_time=60`. Calls `executar_ingestao([CemadenSource(), NasaEonetSource()])`.
- **dispatcher** — every 30s, `max_instances=1`, `coalesce=True`, `misfire_grace_time=60`, processes pending outbox events via `OutboxDispatcher`.

`agendar_ingestao()` calls `criar_banco()` once at startup (not per round). Uses `BlockingScheduler`: `start()` blocks the main thread and wakes only for jobs (no busy loop). A `try/except (KeyboardInterrupt, SystemExit)` around `start()` logs and calls `shutdown(wait=False)` for clean `Ctrl+C` shutdown. Listener `EVENT_JOB_ERROR` keeps service alive if one round fails. See [[decisions/scheduler-background-jobs]].
