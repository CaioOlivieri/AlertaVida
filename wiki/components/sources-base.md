status: integrated
sources: `src/alertavida/sources/base.py`, `src/alertavida/sources/__init__.py`
updated: 2026-06-11

# sources-base

Adapter abstraction for multi-source ingestion (Camada 4):

- `DataSource(ABC)` — abstract `fonte: FonteDado` property + `coletar() -> ResultadoColeta` method.
- `ResultadoColeta` — frozen dataclass: `alertas: list[Alerta]`, `descartados: int`, `coletado_em: datetime` (tz-aware).
- `FalhaDeColeta(Exception)` — typed with `fonte`, `causa`, `original`. Raised with `from exc` to preserve chain.

Contract test infrastructure in `tests/sources/contrato.py`: `verificar_contrato_data_source(source_factory)` parametrizes 7 invariants across all `DataSource` implementations.
