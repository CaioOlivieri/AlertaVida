status: integrated
sources: `src/alertavida/reporting.py`
updated: 2026-06-11

# reporting

Shared report formatter for ingestion run output. Exposes a single public
function:

- `formatar_relatorio(relatorio: RelatorioIngestao) -> str` — formats a
  `RelatorioIngestao` into a human-readable terminal string with counters
  per source (novos, atualizados, reativados, inalterados, descartados) and
  total.

Used by both `monitor.py` (one-shot CLI) and `scheduler.py` (continuous
service logging). The formatter was extracted from `monitor._formatar_relatorio`
to avoid duplication when the scheduler started logging per-run details.
