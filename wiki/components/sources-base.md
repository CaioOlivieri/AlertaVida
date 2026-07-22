status: integrated
sources: `src/alertavida/sources/base.py`, `src/alertavida/sources/_http.py`, `src/alertavida/sources/__init__.py`
updated: 2026-07-22

# sources-base

Adapter abstraction for multi-source ingestion (Camada 4):

- `DataSource(ABC)` — abstract `fonte: FonteDado` property + `coletar() -> ResultadoColeta` method. Transport-agnostic by design — does NOT expose HTTP, retry, or any I/O mechanism, so tests can substitute a `FakeDataSource` without mocking network libraries.
- `ResultadoColeta` — frozen dataclass: `alertas: list[Alerta]`, `descartados: int`, `coletado_em: datetime` (tz-aware).
- `FalhaDeColeta(Exception)` — typed with `fonte`, `causa`, `original`. Raised with `from exc` to preserve chain.

`HttpDataSource(DataSource)` (`sources/_http.py`, issue #20) — template-method base for JSON-over-HTTP sources. Lives in `_http.py`, not `base.py`, to avoid an import cycle (`_http.py` already depends on `base.py`); see [[decisions/template-method-http-datasource]]. Owns:

- Shared `__init__` (`url`/`opener`/`timeout_segundos`, keyword-only). `url` defaults to `None` and falls back to the subclass's `URL` class constant — a shared `__init__` can't use a per-subclass default parameter value.
- Concrete `coletar()`: `fetch_com_retry` → `parse_json` → `_normalize_payload` → per-item `try/except ValueError` (counted as `descartados`; any other exception propagates as a bug, resilience-invariants.md #19) → `ResultadoColeta`.

Subclasses (`CemadenSource`, `NasaEonetSource`) implement only `_normalize_payload()` + `_montar_alerta()` and declare `URL`/`USER_AGENT` as class-level constants. `HttpDataSource` is the extension point for INMET/INPE.

Contract test infrastructure in `tests/sources/contrato.py`: `verificar_contrato_data_source(source_factory)` parametrizes 7 invariants across all `DataSource` implementations.
