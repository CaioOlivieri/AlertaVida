status: implemented
sources: `src/alertavida/scheduler.py`, [[decisions/decision-record]]
updated: 2026-07-22

# Scheduler engine + Job Configuration

`BlockingScheduler` — the scheduler process has no other work on its main thread, so it blocks on `start()` and wakes only to run jobs. This replaced the earlier `BackgroundScheduler` + `while True: time.sleep(1)` keep-alive loop (issue #21): identical clean `Ctrl+C` shutdown, minus the once-per-second busy wakeup and the hand-rolled loop. `start()` blocks; a `try/except (KeyboardInterrupt, SystemExit)` around it logs the shutdown and calls `scheduler.shutdown(wait=False)` for graceful teardown.

The original "background" label was about running the scheduler as a long-lived service, not about the keep-alive mechanism. `BackgroundScheduler` only becomes the right tool again if the main thread gains other work (e.g. a FastAPI app in Camada 5) — at that point this reverts, but until then `BlockingScheduler` is the idiomatic fit.

Job config: `max_instances=1`, `coalesce=True`, `misfire_grace_time=60` prevents pile-up. `EVENT_JOB_ERROR` listener keeps service alive if a round fails.

`criar_banco()` called once at scheduler startup (not every round) — schema setup belongs to bootstrap.
