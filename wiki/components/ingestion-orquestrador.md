status: integrated
sources: `src/alertavida/ingestion/orquestrador.py`
updated: 2026-06-11

# ingestion-orquestrador

Ingestion orchestrator (B.2). Pure orchestration — no entrypoint responsibility:

- `executar_ingestao(sources, *, agora=None)` — for each `DataSource`: calls `coletar()`, isolates `FalhaDeColeta`, runs `detectar_mudancas` + `aplicar_resultado_deteccao`. Returns `RelatorioIngestao`.
- `RelatorioFonte` — frozen dataclass with `__post_init__` invariants (counters balance when no failure; zero + `coletado_em=None` on failure).
- `RelatorioIngestao` — frozen aggregate with `@property total`.

Orchestrator is silent (zero print/logging). Presentation is caller's responsibility. `agora` generated once and propagated for all sources.
