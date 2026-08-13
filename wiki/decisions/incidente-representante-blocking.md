status: implemented
sources: `src/alertavida/database.py`, issue #60
updated: 2026-08-12

# Candidate Incident Representative: Most Recently Joined Member

`domain.correlacao.decidir_correlacao` (#58) compares exactly two points —
it has no notion of an `Incidente` with multiple members. But
`correlacao_observacoes` (#59's schema sketch) records one row per
`(alerta_id, incidente_id)` pair, not per `(alerta_id, member_alert_id)`
pair. Something has to pick a single point, type, and onset to stand in for
a candidate incident with N members before it can be handed to
`decidir_correlacao`.

**Decided: the member most recently added to the incident**
(`MAX(incidente_membros.criado_em)` among the members that fall inside the
blocking bbox). When the R-Tree query in `_buscar_incidentes_candidatos`
returns more than one matching member for the same incident, only that one
is built into a `CandidatoCorrelacao` and evaluated; the others are
discarded for that call.

## Why this, not a centroid or the founding member

- **No `incidentes`-level columns exist to average over.** [[decisions/rtree-spatial-index-blocking]]
  already established that #60 adds no new columns to `incidentes` — a
  centroid or cached bbox would require maintaining denormalized state on
  every `criar_incidente`/`adicionar_membro_incidente` call, which the
  kickoff technical plan did not scope into this issue.
- **A geometric centroid isn't a real observation.** Averaging coordinates
  from members of possibly-different compatible COBRADE subgroups
  (Round 1, Q4 allows FRACA matches) would produce a point, type, and onset
  that no source ever actually reported — worse grounds for `decidir_correlacao`
  than a real alert's data.
- **"Most recent" over "founding member"**: the most recently joined member
  is the freshest evidence of where/when the incident currently is, and its
  `criado_em` is already indexed (`idx_incidente_membros_incidente_id`) and
  cheap to compare with a plain Python `max()` over the (typically tiny)
  candidate set returned by the bbox filter — no extra query needed. The
  founding member (`criar_incidente`'s sole argument) would need explicit
  tracking (a `fundador` flag or `MIN(id)`) for no clear accuracy benefit.

## Known v1 limitation

Only one representative is evaluated per incident per call, even when
several members would individually match. A member outside the buffered
bbox but within `decidir_correlacao`'s effective range through some other
member is not considered — this is the same kind of blocking under-coverage
already flagged in [[decisions/rtree-spatial-index-blocking]] for `codigo_ibge`,
and is left to the same follow-up path (revisit against `#63`'s accumulated
`correlacao_observacoes` data if it proves to matter in practice).

### Temporal drift: the representative is picked *before* the window is applied

`_buscar_incidentes_candidatos` selects the most-recently-joined member
first (by bbox match), then checks *that member's* onset against the
window. It does not fall back to an older member if the newest one falls
outside the window — so an incident can be discarded **whole**, even though
one of its earlier members is well within range of the alert being
evaluated.

Concretely, with three members: `A` joins at `t=0`; `B` joins the same
incident at `t=6h` (still within whatever window applied at the time); `C`
joins at `t=12h`. An alert arriving at `t=1h` is compared only against `C`
(the current most-recent member, `t=12h` onset) — `delta_t = -11h`, almost
certainly outside any provisional window — and the incident is excluded as
a candidate, even though `A`'s onset (`t=0`) is only 1h away.

**This is accepted behavior, not a bug.** The incident's effective window
*slides* with its newest member by construction — the representative-choice
rule in this page is what causes it, and no fallback-to-older-member logic
is introduced to avoid it (that would reopen the "which member evaluates
which alert" question this whole page exists to close, for marginal gain).

**Consequence for #63 — sampling bias, not absence of correlation.** A
drifted incident produces **no row at all** in `correlacao_observacoes` for
alerts that are, in reality, close to its origin. Calibration reading this
dataset must not treat "no observation was written for this alert against
this incident" as evidence the two don't correlate — it may simply mean
blocking never considered the pair because the incident's representative
had already moved on. This should be called out explicitly wherever #63
documents its calibration methodology.
