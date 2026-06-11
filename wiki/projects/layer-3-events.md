status: done
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-06-11

# Layer 3: Change Detection and Events

Pure `ChangeDetector`, transactional Outbox Pattern, in-memory EventBus, scheduled `OutboxDispatcher` every 30 seconds.

**Delivered:**
- Empirical inspection of wsAlertas2 contract (`scripts/inspect_cemaden_payload.py`)
- Database migration: lifecycle columns + `eventos` outbox table
- `ChangeDetector` (pure): `AlertaSnapshot`, `EventoDetectado`, `ResultadoDeteccao`, `detectar_mudancas()`
- 3-phase integration in `executar_ingestao()`: parse → detection → transactional persistence
- EventBus (subscribe/publish) + `OutboxDispatcher` (batch_size=100)
- `AlertaResolvido` by inference (3 consecutive absent rounds, configurable)
- Events: `AlertaCriado`, `AlertaAtualizado`, `AlertaResolvido`
