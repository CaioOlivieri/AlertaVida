status: integrated
sources: `src/alertavida/domain/detector.py`
updated: 2026-06-11

# domain-detector

Change detection engine (Camada 3). Pure — no I/O, no database, no network:

- `AlertaSnapshot` — frozen snapshot of an alert's last known state.
- `EventoDetectado` — typed event (AlertaCriado, AlertaAtualizado, AlertaResolvido) with payload.
- `ResultadoDeteccao` — frozen output containing events, `codigos_vistos`, `codigos_ausentes`, and `fonte_por_codigo` (populated for EVERY code in the union).
- `detectar_mudancas(alertas, snapshots)` — compares current alerts against previous snapshots. Returns `ResultadoDeteccao`.
- `TipoEventoDetectado(StrEnum)` — CRIADO, ATUALIZADO, RESOLVIDO.

`fonte_por_codigo` follows Tell, Don't Ask: the detector tells infra everything needed for persistence.
