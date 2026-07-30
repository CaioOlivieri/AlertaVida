status: blocked
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-07-30

# Layer 5: Event Correlation (blocked)

**Concept:** `Incidente` = aggregate of N `Alerta`s referring to the same physical event observed by different sources.

Example: a flood in Recife may produce CEMADEN (level ALTO), NASA EONET (severeStorms), and INMET (accumulated rainfall) alerts — all describing the same event.

**Algorithm (initial):**
- Same time window (e.g., ±6h)
- Geographic distance below threshold (e.g., 50 km)
- Compatible event types (explicit per-pair rule)

**Prerequisite:** spatial indexing. SQLite R-Tree in current phase; PostGIS when migrating to Postgres in Camada 6.

## Clarifications

*(Per [[decisions/sdd-practices-from-spec-kit]]: before technical planning of
this layer starts, run a structured clarification round with the maintainer and
record every question + answer here — not in chat history. The spec above has
placeholder numbers (±6h, 50 km) that are illustrations, not decisions.)*

### Round 1 — 2026-07-30

Held after the 2026-07-13 maintainability backlog closed (#37–#41, #20–#24).
Answers below were researched against CAP 1.2 (OASIS), the NASA EONET v3 data
model, published GDACS practice and the UNDRR/ISC Hazard Information Profiles.
Items marked **OPEN** are *not* decided and still block planning.

#### Framing adopted for the whole layer

Correlation is a **record-linkage / entity-resolution** problem (Fellegi &
Sunter, *A Theory for Record Linkage*, JASA 1969), and the layer adopts its
three-stage architecture:

1. **Blocking** — cheap candidate generation (spatial index + time window).
2. **Scoring** — weighted evidence, not a chain of `if`s.
3. **Decision with three outcomes** — link, no-link, and a **review band**.

The review band is deliberate, not a hedge. GDACS — the UN/EU multi-hazard
system — generates candidate events algorithmically per hazard and keeps expert
supervision over merges *and splits* at every update. Fully automatic,
fully confident cross-source merging is not the state of the art.

#### Q1 — Time window: value, symmetry, per-type?

**Decided:** the window is **not symmetric**, and it is **not taken from
literature** — it is derived from this project's own data.

Detection latency differs by source (satellite revisit + processing vs. ground
nowcast), so the physical event starts before either source observes it. The
window must therefore be expressed against an **estimated event onset**, not
alert-to-alert.

Method adopted: **instrument before calibrating.** Record the Δt of every
candidate pair even when it does not correlate; once a maintainer-confirmed set
of same-event pairs exists, set the window per type at a high percentile (P95)
of the empirical Δt distribution. This is the discipline `domain/cobrade.py`
already imposes on the mapping tables ("não inventar mapeamentos baseado em
suposição").

**Code consequence (must fix before scoring is written):** `NasaEonetSource`
uses `_fix_mais_recente`, collapsing the EONET geometry series to the **most
recent** observation. EONET geometries are "the pairing of a specific date/time
with a location", i.e. a time series for an already-aggregated event, so that
timestamp is the *latest* observation, not the onset. Correlation must use the
**earliest** geometry as EONET onset.

**OPEN:** the provisional per-type values, pending the first confirmed pair set.

#### Q2 — Distance: single radius or per-type? point-to-point or bbox?

**Decided (reframed):** the comparison is not point-to-point but between **two
location estimates with different positional uncertainty**, so a single global
radius is rejected.

Preference order for the spatial predicate:

1. **Administrative key before geometry** — `codigo_ibge` is already persisted;
   for CEMADEN↔CEMADEN, same municipality is stronger and cheaper evidence than
   any distance.
2. **Point-in-polygon across sources** — for CEMADEN↔EONET, test the EONET point
   against the municipality polygon (IBGE *malha municipal*, public data).
3. **Distance only as a fallback**, and then per type.

**Bbox and exact distance both, in different roles** — the classic
filter-and-refine paradigm: the R-Tree bbox is the *blocking* stage (cheap,
approximate); the decision uses exact geodesic distance over the candidates.
A bbox must never decide on its own: it over-selects at the corners and, in
degrees, distorts with latitude (1° of longitude ≠ 1° of latitude in km at
Brazilian latitudes — a trap already live in the `escopo_geografico` buffer,
which is configured in degrees).

**OPEN — blocking verification:** what a CEMADEN `latitude`/`longitude` actually
denotes (municipality centroid vs. precise risk point) is **not established**.
The test fixtures carry values consistent with municipal centroids, but those
are hand-written test data, not real samples — per `_schema.md` rule 1 this
cannot be asserted by inference. Verify against the real 475-item sample set
before choosing between options 1–3; Brazilian municipalities span ~4 orders of
magnitude in area, so the answer changes the design.

#### Q3 — Does `nivel_risco=INDETERMINADO` (EONET) correlate on equal footing?

**Decided:** yes — because **severity is removed from the matching criteria
entirely**.

Correlation establishes **identity** (same physical event), not **agreement**
(sources concur on gravity). Two sources disagreeing on severity is expected and
is precisely the information an `Incidente` exists to preserve; matching on
severity would discard the most valuable case (one source reporting a level
materially worse than another).

`INDETERMINADO` means "the source publishes no severity", not "low severity" —
treating absence of information as information would bias the result.

Severity's role is in the **aggregate**, where:

- `Incidente` severity = **maximum** over members with a known level, never the
  mean. For a life-safety system the precautionary reading holds: an incident is
  as severe as its most severe credible member. Averaging would let an
  `INDETERMINADO` dilute a `MUITO_ALTO` — an unacceptable failure mode.
- `INDETERMINADO` members are **excluded from the aggregation but recorded**
  ("N sources published no severity").
- Source reliability, if modelled, enters as an **explicit per-source weight** in
  the score — never disguised as severity.

#### Q4 — Which (TipoEvento × TipoEvento) pairs correlate?

**Decided:** re-key the table, and split one relation into two.

**Re-key to `cobrade_codigo`, not `TipoEvento`.** `TipoEvento` carries only the
5 COBRADE groups, so a 5×5 table is too coarse to be useful. `cobrade_codigo` is
already persisted and distinguishes what the groups cannot (e.g. `1.4.1.0.0`
wildfires vs. `1.2.0.0.0` floods), is the official Defesa Civil standard, and
scales when INMET/INPE bring finer codes.

**Two distinct relations, never merged into one table:**

- **Same event** (identity) — e.g. one storm seen by CEMADEN and by EONET.
  This is what forms an `Incidente`.
- **Causal cascade** (triggering) — storm → flash flood → landslide. The 2025
  UNDRR/ISC HIPs edition explicitly moves toward a multi-hazard reading in which
  hazards interact and cascade.

Collapsing the two makes incidents grow without bound: in a rainy region
everything eventually merges and the `Incidente` loses operational meaning.
Cascade becomes a separate relation (`desencadeou` / `desencadeado_por`) —
valuable to display, unusable as a merge criterion.

The identity table starts **diagonal only** (same group with same group); every
off-diagonal pair requires documented empirical evidence, same discipline as
`domain/cobrade.py`.

#### Q5 — `Incidente` lifecycle: resolve when all members resolve? reactivate?

**Decided**, anchored on CAP 1.2, which separates two mechanisms:

- `<references>` — the temporal chain (`Update`/`Cancel` supersede earlier
  messages);
- `<incidents>` — "the group listing naming the referent incident(s)", which
  collates distinct messages addressing different facets of one incident.

`Incidente` **is** the CAP `incidents` concept, with one critical difference:
in CAP the *sender* knows the incident identifier, whereas here it is
**inferred**. Every membership therefore needs provenance (which alert joined,
with what score, when) and must remain revisable.

Rules adopted:

- Mirror the alert lifecycle already in place (`status_interno`,
  `rodadas_ausente`, reactivation — see
  [[decisions/alert-reactivation-instead-of-crash]]). Internal consistency beats
  novelty.
- An `Incidente` resolves when **all** members are resolved, never when any one
  resolves (precautionary).
- It **must** be able to reactivate, because alerts already do: a resolved alert
  that reappears emits `AlertaReativado`, and an incident unable to follow would
  leave the two tables inconsistent.
- **EONET `closed` is not authoritative** for resolution — NASA states the value
  "may or may not accurately represent the absolute ending of the event".
- Lifecycle events (`IncidenteCriado`/`Atualizado`/`Resolvido`) go through the
  existing outbox — the reason issue #24 built the bus via
  `criar_bus_producao()` ahead of Camada 8.

#### Q6 — Retroactive or forward-only correlation?

**Decided: forward-only, with bounded append-only revision.**

Full retroactive re-clustering makes the incident set a function of the entire
history, so incident identifiers can change meaning as history grows. That is
disqualifying once Camada 8 exists: a user notified about a given incident must
never find it gone or redefined.

Three permitted operations, in order:

1. A new alert **joins** a compatible open incident;
2. or **opens** a new one;
3. or triggers a **merge of two open incidents** — recorded as an event, both
   identifiers remaining resolvable (the older redirects to the survivor), never
   silently deleted.

**Closed incidents are never re-evaluated**, and only incidents whose time window
is still open are merge candidates. This keeps cost at O(open incidents) rather
than O(history) — the scalability property of the design. It also mirrors GDACS,
where merging is assessed at each update rather than by reprocessing the past.

#### OPEN — the maintainer's call, still unanswered

**Which error is worse: a false merge or a false split?** Everything above
assumes a bias toward **splitting** (under-merging): duplicate incidents are
cheap redundancy — the user sees two similar alerts — whereas a wrong merge can
make a severe event inherit a mild one's context and lose attention. For a
life-safety system, redundancy is cheap and omission is not. If the priority is
instead to avoid bothering users with duplicates, the thresholds change (not the
architecture). **This answer must be recorded before scoring thresholds are
set.**
