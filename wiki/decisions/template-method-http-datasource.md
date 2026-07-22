status: implemented
sources: `src/alertavida/sources/_http.py`, `src/alertavida/sources/base.py`
updated: 2026-07-22

# Template Method: HttpDataSource

`CemadenSource` and `NasaEonetSource` duplicated their `__init__`
(url/opener/timeout_segundos, keyword-only) and `coletar()`
(`fetch_com_retry` → `parse_json` → `_normalize_payload` → per-item
`try/except ValueError` counting `descartados` → `ResultadoColeta`) line by
line. The invariant "only `ValueError` counts as a discard; anything else is
a bug and propagates" (resilience-invariants.md #19) lived only as a comment
repeated in both files — a third source (INMET/INPE) would depend on
copy-paste discipline to keep it.

## Decision

New `HttpDataSource(DataSource)` in `sources/_http.py` owns the shared
`__init__` and concrete `coletar()`. Subclasses implement only two abstract
methods — `_normalize_payload()` and `_montar_alerta()` — and declare
`URL`/`USER_AGENT` as class-level constants. `CemadenSource` and
`NasaEonetSource` now extend `HttpDataSource` instead of `DataSource`
directly.

## Why `HttpDataSource`, not the `DataSource` ABC

`DataSource` (`sources/base.py`) explicitly promises not to expose
transport — that's what lets tests substitute a `FakeDataSource` without
mocking network libraries. Folding a concrete HTTP-fetch-and-retry
`coletar()` into the ABC would break that promise for every future
subclass, including non-HTTP sources.

## Why it lives in `_http.py`, not `base.py`

`_http.py` already imports `FalhaDeColeta`/`DataSource` from `base.py`
(transport depends on the interface). Putting `HttpDataSource` in
`base.py` would need `fetch_com_retry`/`parse_json`/`opener_padrao` from
`_http.py`, creating an import cycle. `HttpDataSource` is the concrete
extension point for the transport it composes, so it belongs in the
transport module; `base.py`'s docstring now points to it.

## Construction

`url` defaults to `None` in `HttpDataSource.__init__` and falls back to
`self.URL` — a plain default value (`url: str = URL_CEMADEN`, the previous
per-subclass pattern) can't work once `__init__` is shared, because
default parameter values are bound once at function-definition time, not
per-subclass.

## Result

`CemadenSource`/`NasaEonetSource` each lost their `__init__` and
`coletar()`; only `_normalize_payload`/`_montar_alerta` (and helpers
specific to each payload shape) remain. Exported as `HttpDataSource` from
`sources/__init__.py` — the extension point for INMET/INPE.
