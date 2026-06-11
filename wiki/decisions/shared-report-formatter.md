status: implemented
updated: 2026-06-11

# Shared Report Formatter

The ingestion report formatter lived as a private function in `monitor.py`.
When scheduler observability was added, the same formatting was needed for
the scheduler's per-run logging.

Extracted into `reporting.py` as `formatar_relatorio()` — a shared public
function used by both `monitor.py` (CLI print) and `scheduler.py` (logger
info). The orchestrator itself remains silent per [[decisions/orchestrator-silent-reports]].
