status: integrated
sources: `src/alertavida/sources/_http.py`
updated: 2026-06-14

# sources-http

Shared HTTP transport for all `DataSource` implementations. Extracted (Fase 2 of
the maintainability review) because [[components/sources-cemaden]] and
[[components/sources-nasa-eonet]] duplicated ~50 lines each of identical
retry/backoff and JSON parsing.

## Exports

- `fetch_com_retry(url, *, fonte, opener, user_agent, timeout_segundos=…, max_tentativas=…, backoff_inicial=…) -> bytes`
  — GET with exponential backoff. Encapsulates the resilience policy
  (invariants 3, 19, 20): retry only on 5xx / 408 / 429 / `URLError` /
  `socket.timeout`; 4xx (except 408/429) fails immediately. **Raises
  `FalhaDeColeta(fonte=…)` directly** (with the original exception chained) — no
  raw network exception leaks to the orchestrator, so each source's `coletar()`
  no longer needs a transport `try/except`.
- `parse_json(raw, *, fonte) -> object` — UTF-8 decode + `json.loads`, raising
  `FalhaDeColeta` on `UnicodeDecodeError` / `JSONDecodeError`.
- `RespostaHTTP` Protocol (PEP 544, `read() -> bytes`) and `Opener` type —
  strict-by-contract typing of the HTTP response, faked in tests via `read()`.

## Testing

`tests/sources/test_http.py` exercises the retry/backoff matrix and `parse_json`
once (previously a `TestFetchComRetry` class was copied into each source's test
file). `time.sleep` is patched at `alertavida.sources._http.time.sleep`.
