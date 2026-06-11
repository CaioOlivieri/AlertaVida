status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# Silent Orchestrator + Typed Reports

`executar_ingestao` returns `RelatorioIngestao` and stays silent (zero print/logging). Presentation is caller's responsibility.

`RelatorioFonte` (frozen dataclass with `__post_init__` invariants) per source + `RelatorioIngestao` (frozen aggregate with `@property total`) makes accounting immutable, typed, and consumable by logging, tests, and future `/health` endpoints. `agora` generated once and propagated to all sources for timestamp coherence.

Orchestrator placed in `ingestion/orquestrador.py` (SRP), `monitor.py` reduced to pure entrypoint.
