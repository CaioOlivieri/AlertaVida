status: implemented
sources: `src/alertavida/domain/detector.py`, `src/alertavida/database.py`, `src/alertavida/ingestion/orquestrador.py`
updated: 2026-06-11

# Alert Reactivation Instead of Crash

A resolved alert reappearing in the feed emits `AlertaReativado` (status back to ATIVO, `rodadas_ausente` reset, outbox event in the same transaction).

Previously `buscar_snapshots_ativos` only returned ATIVO snapshots, making the detector's RESOLVIDO branch dead code — a reappearing alert was classified as CRIADO and crashed the whole round with `IntegrityError: UNIQUE constraint failed: alertas.fonte, alertas.cod_alerta`, in a crash-loop every 5 minutes.
