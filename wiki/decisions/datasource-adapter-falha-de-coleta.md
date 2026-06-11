status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# DataSource Adapter + FalhaDeColeta

Camada 4 uses Adapter pattern. `DataSource` ABC with `ResultadoColeta` (frozen: `alertas`, `descartados`, `coletado_em`) carries explicit accounting — orchestrator needs `descartados` per source for the sanity assertion.

`FalhaDeColeta` is a typed exception (`fonte`, `causa`, `original`) raised with `from exc`. Distinguishes source round-level failure from individual alert errors (counted as `descartados`). `FakeDataSource` instead of `unittest.mock.Mock` — faithful double reveals signature changes immediately.
