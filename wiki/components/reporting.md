status: integrated
sources: `src/alertavida/reporting.py`
updated: 2026-08-13

# reporting

Shared report formatter for ingestion run output. Exposes a single public
function:

- `formatar_relatorio(relatorio: RelatorioIngestao) -> str` — formats a
  `RelatorioIngestao` into a human-readable terminal string with counters
  per source (novos, atualizados, reativados, inalterados, descartados),
  the four Camada 5 incident counters (criados, juntados, fundidos, revisão
  — issue #61, see [[components/ingestion-orquestrador]]) and total.

Used by both `monitor.py` (one-shot CLI) and `scheduler.py` (continuous
service logging). The formatter was extracted from `monitor._formatar_relatorio`
to avoid duplication when the scheduler started logging per-run details.
