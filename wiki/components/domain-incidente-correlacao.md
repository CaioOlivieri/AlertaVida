status: integrated
sources: `src/alertavida/domain/incidente.py`, `src/alertavida/domain/correlacao.py`
updated: 2026-08-11

# domain-incidente-correlacao

Pure domain core for Camada 5 correlation (issue #58) — zero I/O, no SQL, no
`database`/`sources` imports. Mirrors how `ChangeDetector`
([[components/domain-detector]]) was built pure before integration.
Implements the record-linkage decision from [[projects/layer-5-correlation]]
(Round 1 framing): blocking (spatial index, time window) lives elsewhere
(#60); this is scoring → three-outcome decision.

## `incidente.py` — the aggregate

- `Incidente` — frozen pydantic entity, like `Alerta`. `membros: tuple[MembroIncidente, ...]` (min 1), `status: StatusIncidente` (`ATIVO`/`RESOLVIDO`, mirrors `alertas.status_interno`), `criado_em`/`atualizado_em`/`resolvido_em`. Atomic invariant `resolvido_em is not None ⇔ status == RESOLVIDO`, same style as `Alerta`'s `cobrade_codigo ⇔ fonte_classificacao` pair. Rejects duplicate members (same `fonte` + `cod_alerta`).
- `MembroIncidente` — frozen pydantic value object: `fonte`, `cod_alerta` (the `UNIQUE (fonte, cod_alerta)` natural key from [[components/domain-models]]), `nivel_risco` (needed for severity aggregation; not looked up — this module does no I/O, so whoever builds the `Incidente` supplies it).
- `Incidente.severidade` (property) — MAX over members with a known `nivel_risco`; `None` if every member is `INDETERMINADO`. Never the mean (Round 1, Q3 — an `INDETERMINADO` member must never dilute a `MUITO_ALTO`).
- `Incidente.membros_sem_severidade` (property) — count of `INDETERMINADO` members: excluded from `severidade`, but recorded, never treated as "low severity".
- Lifecycle transitions (when to resolve, merge redirects) are **not** modeled here — they need persisted state (real member status, incident ids) and belong to #59/#61. This module only models the aggregate's shape.

## `correlacao.py` — the decision core

- `CandidatoCorrelacao` (frozen dataclass) — reduced view of an `Alerta` carrying only what scoring needs: `fonte`, `cod_alerta`, `tipo_evento`, `cobrade_codigo`, `codigo_ibge`, `latitude`/`longitude`, `momento_onset`. Deliberately excludes `nivel_risco` (Round 1, Q3 — correlation establishes identity, not agreement on severity).
- `compatibilidade_tipo(cobrade_a, tipo_a, cobrade_b, tipo_b)` — identity compatibility at the most specific level both sides have. Both with `cobrade_codigo` → prefix comparison (same subgroup = `FORTE`, same group/different subgroup = `FRACA`, different group = `INCOMPATIVEL`). One or both missing → `TipoEvento` fallback (`INDETERMINADO` on either side → `INDETERMINADA`, even when *both* sides are `INDETERMINADO`; equal → `FORTE`; different → `INCOMPATIVEL`). Diagonal-only by construction: no cross-group pair is approved without documented empirical evidence, same discipline as `EVENTO_CEMADEN_PARA_COBRADE` in [[components/domain-cobrade]].
- `distancia_haversine_km(lat1, lon1, lat2, lon2)` — pure geodesic distance, `math` stdlib only, no new dependency. Decision path never compares raw degrees (Round 1, Q2 — the distortion already documented in `domain/geographic.py`'s buffer).
- `decidir_correlacao(a, b)` — weighted score over available evidence (administrative key `codigo_ibge`, `distancia_haversine_km`, time proximity to `momento_onset`, `compatibilidade_tipo`); a missing component (e.g. `codigo_ibge` on most CEMADEN↔EONET pairs) redistributes its weight instead of scoring zero. Two structural gates sit ahead of the score thresholds and survive any future recalibration: `INCOMPATIVEL` always → `NAO_VINCULA`; `INDETERMINADA` never → `VINCULA` (at most `REVISAO`). Returns `DecisaoCorrelacao` (frozen dataclass: `resultado`, `score`, `motivo`, `distancia_km`, signed `delta_t_segundos`) — enough for #59/#60 to write a `correlacao_observacoes` row without recomputing.
- `ResultadoDecisao` (`StrEnum`) — `VINCULA` / `NAO_VINCULA` / `REVISAO`, the three-outcome decision (Round 1 framing; the review band is deliberate, not a hedge).
- All weights (`PESO_CODIGO_IBGE`, `PESO_DISTANCIA`, `PESO_TEMPO`, `PESO_TIPO`) and thresholds (`DISTANCIA_MAXIMA_KM`, `JANELA_TEMPO_SEGUNDOS`, `LIMIAR_VINCULA`, `LIMIAR_REVISAO`) are module-level constants, explicitly documented as provisional placeholders inherited from the pre-clarification spec (±6h / 50 km). Calibration is dormant issue #63 — not touched here. `LIMIAR_VINCULA` starts high and `LIMIAR_REVISAO` starts low (wide review band), the Round 2 bias toward splitting: in doubt, `REVISAO` or `NAO_VINCULA`, never `VINCULA`.
- Causal cascade is explicitly out of scope for v1 (module docstring note only, no code, no table) — Round 1, Q4 splits it from identity.

27 pure unit tests (`tests/domain/test_incidente.py`, `tests/domain/test_correlacao.py`), no DB, run in the main suite (< 1s, [[patterns/test-conventions]]).
