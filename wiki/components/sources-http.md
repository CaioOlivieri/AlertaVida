status: integrated
sources: `src/alertavida/sources/_http.py`
updated: 2026-07-17

# sources-http

Shared HTTP transport for all `DataSource` implementations. Extracted (Fase 2 of
the maintainability review) because [[components/sources-cemaden]] and
[[components/sources-nasa-eonet]] duplicated ~50 lines each of identical
retry/backoff and JSON parsing. Hardened (#39, 2026-07-13 maintainability audit)
against two availability/integrity gaps: unbounded response bodies and
cross-scheme (https→http) redirects — see [[patterns/resilience-invariants]]
24/25.

## Exports

- `fetch_com_retry(url, *, fonte, opener, user_agent, timeout_segundos=…, max_tentativas=…, backoff_inicial=…, max_resposta_bytes=MAX_RESPOSTA_BYTES) -> bytes`
  — GET with exponential backoff. Encapsulates the resilience policy
  (invariants 3, 19, 20, 24): retry **only** on 5xx / 408 / 429 / `URLError` /
  `socket.timeout`; any other `HTTPError` (4xx except 408/429, and — since #39
  — a redirect refused by `opener_padrao`, which surfaces as a non-5xx
  `HTTPError`) fails immediately. Reads at most `max_resposta_bytes + 1` bytes
  via `response.read(n)`; if the body exceeds `max_resposta_bytes` it fails
  immediately too (no retry — an oversized body is not transient, same
  treatment as a 4xx). **Raises `FalhaDeColeta(fonte=…)` directly** (with the
  original exception chained where one exists) — no raw network exception
  leaks to the orchestrator, so each source's `coletar()` no longer needs a
  transport `try/except`.
- `MAX_RESPOSTA_BYTES: int = 20 * 1024 * 1024` (20 MB) — module default for
  `max_resposta_bytes`, sized for real feed volumes (CEMADEN: hundreds of KB;
  EONET with `limit=500`: a few MB) with headroom, not for worst-case DoS
  payloads.
- `opener_padrao: Opener` — module's default opener, built via
  `build_opener(_RedirectHTTPSObrigatorioHandler)`. `CemadenSource` and
  `NasaEonetSource` both default their `opener` constructor param to this
  (replacing the bare `urlopen` they used pre-#39) — the only change #39 made
  in those two files.
- `_RedirectHTTPSObrigatorioHandler` (private, `HTTPRedirectHandler` subclass)
  — overrides `redirect_request` to raise `HTTPError` when `newurl` doesn't
  start with `https://`, instead of following the redirect. Both production
  URLs are https today; a downgrade is never legitimate — it's either a
  misconfigured server or a network attacker forging the redirect to get a
  plaintext channel for injecting fake disaster alerts.
- `parse_json(raw, *, fonte) -> object` — UTF-8 decode + `json.loads`, raising
  `FalhaDeColeta` on `UnicodeDecodeError` / `JSONDecodeError`.
- `RespostaHTTP` Protocol (PEP 544, `read(n: int = -1) -> bytes`) and `Opener`
  type — strict-by-contract typing of the HTTP response, faked in tests via
  `read()`. Grew from `read() -> bytes` to `read(n=-1) -> bytes` for #39 — not
  a new contract, `http.client.HTTPResponse.read(amt)` already supports it;
  `fetch_com_retry` just started passing the cap through.

## Design note: 3xx tightened into the immediate-fail path (#39)

Before #39, the retry condition was `400 <= code < 500 and code not in (408,
429)` — anything **not** matching that (including a bare 3xx `HTTPError`) fell
through to the generic retry-and-exhaust path, contradicting invariant 3's own
text ("retry only on 5xx/408/429"). This was latent/unreachable before #39
because urllib followed redirects silently. Once
`_RedirectHTTPSObrigatorioHandler` started raising `HTTPError` with the
original 3xx code on a refused redirect, that path became reachable — and
retrying four times (with backoff) against a deterministic, non-transient
redirect refusal would burn ~14s per source per round for no benefit, which is
itself an availability concern for a public alert system. The condition was
inverted to an explicit retryable set (`500 <= code < 600 or code in (408,
429)`) so 3xx now fails immediately, same as 4xx. All pre-existing retry tests
(404, 429, 503) pass unchanged under the new condition — it's a strict
tightening, not a behavior change for the codes already covered.

## Testing

`tests/sources/test_http.py` exercises the retry/backoff matrix, the size cap,
the redirect handler, and `parse_json` (previously a `TestFetchComRetry` class
was copied into each source's test file). `time.sleep` is patched at
`alertavida.sources._http.time.sleep`. The size-cap test uses a fake opener
whose `read(n)` actually slices the payload (unlike the plain
`_opener_de_payload` fake used elsewhere, which ignores `n`) — needed to prove
`fetch_com_retry` passes the `limite + 1` cap through instead of buffering the
whole body. The redirect handler is tested directly (`redirect_request(...)`
raises/delegates) plus one `fetch_com_retry`-level test with a fake opener
raising a 302 `HTTPError`, standing in for what
`_RedirectHTTPSObrigatorioHandler` would raise for real — no real network or
redirect-following exercised.
