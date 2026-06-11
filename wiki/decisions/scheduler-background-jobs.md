status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# BackgroundScheduler + Job Configuration

`BackgroundScheduler` instead of `BlockingScheduler` — enables clean `Ctrl+C` shutdown on Windows and prepares for FastAPI integration in Camada 5. `time.sleep(1)` loop on main thread works on any OS.

Job config: `max_instances=1`, `coalesce=True`, `misfire_grace_time=60` prevents pile-up. `EVENT_JOB_ERROR` listener keeps service alive if a round fails.

`criar_banco()` called once at scheduler startup (not every round) — schema setup belongs to bootstrap.
