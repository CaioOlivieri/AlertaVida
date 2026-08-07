status: in-progress
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-08-07

# Layer 5: Event Correlation (in progress)

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

**OPEN — blocking verification** *(→ answered in Round 2; no longer blocking)*:
what a CEMADEN `latitude`/`longitude` actually denotes (municipality centroid vs.
precise risk point) is **not established**. The test fixtures carry values
consistent with municipal centroids, but those are hand-written test data, not
real samples — per `_schema.md` rule 1 this cannot be asserted by inference.
Verify against real payload data before choosing between options 1–3; Brazilian
municipalities span ~4 orders of magnitude in area, so the answer changes the
design.

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

#### OPEN — the maintainer's call *(→ answered in Round 2)*

**Which error is worse: a false merge or a false split?** Everything above
assumes a bias toward **splitting** (under-merging): duplicate incidents are
cheap redundancy — the user sees two similar alerts — whereas a wrong merge can
make a severe event inherit a mild one's context and lose attention. For a
life-safety system, redundancy is cheap and omission is not. If the priority is
instead to avoid bothering users with duplicates, the thresholds change (not the
architecture). **This answer must be recorded before scoring thresholds are
set.**

---

### Round 2 — 2026-08-06

Closes the two items Round 1 left OPEN. **Planning is now unblocked.**

#### Q2 follow-up — what a CEMADEN coordinate denotes

Settled by **measurement, not opinion**. A live fetch of the CEMADEN endpoint
returned a single active alert nationwide:

```
codibge 4322400 · URUGUAIANA/RS
latitude        -29.840579610029
longitude       -56.72993457504
ult_atualizacao 2026-08-01 13:10:58.615
```

Uruguaiana's municipal seat is at 29°45'17"S / 57°05'18"W (≈ `-29.7547`,
`-57.0883`) and the municipality covers 5,702 km². The alert point sits **~36 km
from the seat** (≈ 9.6 km south, ≈ 34.6 km east).

**Established:** the coordinate is **not** the municipal seat or urban centre.
The 12 decimal places also indicate a computed value rather than a hand-tabled
one.

This **refutes the inference recorded in Round 1**, which read the fixtures
(Rio at `-22.91`, roughly the city centre) as evidence of centroid semantics.
Real payloads do not behave that way — precisely the failure mode `_schema.md`
rule 1 exists to prevent.

**Still not separable:** polygon centroid vs. actual risk point. Uruguaiana's
seat sits on the western border and the municipality extends east, so *both*
candidates land tens of km east of the seat; one sample cannot discriminate.

**Method to finish it** (tracked, not blocking): the discriminator is several
alerts **within the same municipality** — identical coordinates ⇒ centroid,
varying coordinates ⇒ risk point. Not runnable at time of writing (one alert in
the whole country). Re-run during an alert surge in the rainy season.

**Why it no longer blocks planning:** either answer reinforces the Round 1
decision. A single point standing for 5,702 km² carries tens of km of positional
ambiguity whichever it is, so the preference for the `codigo_ibge`
administrative key and point-in-polygon over any radius holds — more strongly,
not less.

#### Maintainer's call — false merge vs. false split

**Decided: bias toward splitting (under-merging).**

Concretely: at 2 a.m. in Recife, the worst a duplicate does is show the user two
similar alerts and annoy them. The worst a wrong merge does is let a severe
landslide inherit the label of a moderate rainfall incident, so the user swipes
past it believing it was already read. Redundancy is cheap; omission is not. The
project's own stated mission — "code that can save lives must not fail silently"
([[_index]]) — makes the asymmetry unambiguous.

**This is a starting posture, not a final threshold.** The three-outcome design
adopted in the Round 1 framing defers the fine calibration by construction: the
trade-off only bites inside the ambiguous band, and there the system decides
*neither* way — it flags for review. The thresholds are then calibrated from the
accumulated flagged cases, the same evidence-first discipline as the Q1 time
window. Cost of revising it later is low: it moves thresholds, not architecture.

#### Planning status

| Item | State |
|---|---|
| Framing, Q3, Q4, Q5, Q6 | Decided (Round 1) |
| Q2 spatial predicate | Decided (Round 1); semantics measured (Round 2) |
| Merge-vs-split posture | Decided (Round 2) |
| Q1 per-type window values | **Calibration-time**, not planning-time — requires a maintainer-confirmed pair set that cannot exist before the layer runs |
| CEMADEN centroid vs. risk point | **Tracked**, not blocking — re-run the discriminator in the rainy season |

Nothing on this page blocks technical planning of Camada 5 any longer.

---

## Technical plan

*(Written 2026-08-07, issue #56. Derived from the clarification rounds above —
which are the product spec — and from the code as it stands at `main` 96b54c8
(311 tests, ruff 0.16, mypy with `disallow_untyped_defs`). This section is
written to be executable without any chat history: every choice below either
cites the round that decided it or is flagged as a v1 planning decision made
here. Where it is silent, the rounds above govern.)*

### Design shape in one paragraph

Correlation is a record-linkage pipeline — **blocking → scoring → three-outcome
decision** (Round 1 framing) — bolted onto the existing ingestion round, not a
new service. The decision logic is a **pure core** in `domain/`, with zero I/O,
exactly as `ChangeDetector` was built pure before being integrated
([[components/domain-detector]]); candidate generation and durable state live in
`database.py`; the wiring point is `ingestion/orquestrador.py`, immediately after
`aplicar_resultado_deteccao()`. Nothing re-reads history: correlation only ever
looks at **open** incidents (Round 1, Q6), so cost is O(open incidents).

### Module layout

| Module | Status | Responsibility | Issue |
|---|---|---|---|
| `domain/incidente.py` | new | `Incidente` entity (frozen pydantic, like `Alerta`), members by `(fonte, cod_alerta)`, status `ATIVO`/`RESOLVIDO`, severity aggregation = **max** over members with a known level, `INDETERMINADO` members excluded but counted | #58 |
| `domain/correlacao.py` | new | Pure decision core: identity-compatibility table keyed on `cobrade_codigo`, weighted evidence, three-outcome decision, haversine helper. All weights/thresholds are module-level constants | #58 |
| `database.py` | extend | `incidentes`, `incidente_membros` (#59), `correlacao_observacoes` + candidate query (#60); state-change functions writing their outbox event in the **same transaction** (invariant 4) | #59, #60 |
| `ingestion/orquestrador.py` | extend | Integration point: after persistence, correlate `CRIADO` and `REATIVADO` alerts; incident counters on `RelatorioFonte`/`RelatorioIngestao` | #61 |
| `sources/nasa_eonet.py` | fix | EONET `data_criacao` = **earliest** geometry (onset), position/`ult_atualizacao` stay the latest fix | #57 |
| `reporting.py` | extend | `formatar_relatorio()` renders the new counters | #61 |
| `scripts/` + spatial predicate | later | IBGE *malha municipal* acquisition + point-in-polygon | #62 |

**Why a pure core, restated for whoever executes #58:** the decision function is
precisely what dormant issue #63 will calibrate. Keeping it pure and
constant-driven means calibration edits a table of constants, never control
flow — and its tests need no database, so the suite stays under a second
([[patterns/test-conventions]]).

**Evidence available to scoring at v1**, all already persisted per alert:
`codibge`, `latitude`/`longitude`, `data_criacao` (= onset once #57 lands),
`cobrade_codigo`, `tipo_evento`, `fonte`. **`nivel_risco` is deliberately not an
input** (Round 1, Q3 — correlation establishes identity, not agreement).

### Schema sketch

Illustrative, not final DDL — #59 owns the exact statements and #60 adds the
third table. Every table is **new**, so `_migrar_banco()` stays additive-only and
`_verificar_compatibilidade_schema()` needs no new rejection branch. FK style
follows the #22 precedent ([[decisions/foreign-key-eventos-agregado-id]]):
declared in `CREATE TABLE`, child-key index on every FK, `ON DELETE NO ACTION`,
enforcement per connection via `conectar()`'s `PRAGMA foreign_keys=ON`.

```sql
CREATE TABLE IF NOT EXISTS incidentes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    status        TEXT    NOT NULL DEFAULT 'ATIVO',  -- mirrors alertas.status_interno
    criado_em     TEXT    NOT NULL,
    atualizado_em TEXT    NOT NULL,
    resolvido_em  TEXT    NULL,
    fundido_em    INTEGER NULL,                      -- append-only merge redirect
    FOREIGN KEY (fundido_em) REFERENCES incidentes(id)
);

CREATE TABLE IF NOT EXISTS incidente_membros (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incidente_id INTEGER NOT NULL,
    alerta_id    INTEGER NOT NULL,
    score        REAL    NOT NULL,   -- provenance: how strong the evidence was
    motivo       TEXT    NOT NULL,   -- provenance: which evidence fired
    criado_em    TEXT    NOT NULL,   -- provenance: when it joined
    UNIQUE (alerta_id),
    FOREIGN KEY (incidente_id) REFERENCES incidentes(id),
    FOREIGN KEY (alerta_id)    REFERENCES alertas(id)
);

-- #60, append-only instrumentation; the dataset #63 calibrates from
CREATE TABLE IF NOT EXISTS correlacao_observacoes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id        INTEGER NOT NULL,
    incidente_id     INTEGER NULL,      -- NULL = no candidate at all
    delta_t_segundos REAL    NOT NULL,  -- signed, against estimated onset
    distancia_km     REAL    NULL,
    mesmo_codibge    INTEGER NOT NULL,  -- 0/1
    score            REAL    NOT NULL,
    decisao          TEXT    NOT NULL,  -- VINCULA | NAO_VINCULA | REVISAO
    motivo           TEXT    NOT NULL,
    criado_em        TEXT    NOT NULL,
    FOREIGN KEY (alerta_id)    REFERENCES alertas(id),
    FOREIGN KEY (incidente_id) REFERENCES incidentes(id)
);
```

Plus child-key indexes on `incidentes(fundido_em)`,
`incidente_membros(incidente_id)`, `incidente_membros(alerta_id)`,
`correlacao_observacoes(alerta_id)`, `correlacao_observacoes(incidente_id)`, and
a candidate-lookup index on `incidentes(status, fundido_em)`.

Three properties are load-bearing and must survive implementation:

- **`fundido_em` is a redirect, never a delete** (Round 1, Q6). A merged incident
  keeps its row and its members; the column points at the survivor, so both ids
  stay resolvable forever — the property Camada 8 depends on.
- **`UNIQUE (alerta_id)`** — an alert belongs to at most one incident. Merges are
  expressed at the incident level (`fundido_em`), never by rewriting membership
  rows, which is what keeps the history append-only.
- **Statuses mirror the alert lifecycle** (`ATIVO`/`RESOLVIDO`, resolution only
  when *all* members resolve, reactivation supported —
  [[decisions/alert-reactivation-instead-of-crash]]). Internal consistency beats
  novelty (Round 1, Q5).

**Open implementation question, owned by #59 — do not pre-empt it here.**
`eventos.agregado_id` carries a FK to `alertas(id)` since #22, so incident
lifecycle events cannot reuse that column to reference `incidentes`. The
candidates are: (a) incident id in the JSON `payload`, `agregado_id` pointing at
the triggering alert; (b) a nullable `agregado_incidente_id` column with its own
FK; (c) something else. #59 must put the trade-offs to the maintainer before
writing code, and the #22 FK must not be weakened or dropped either way. The
outcome gets a page in `decisions/`.

### Execution plan

```
#56 kickoff (docs)
      │
      ├──► #57 EONET onset ──────────────┐
      │                                  │  (must merge before #61:
      └──► #58 domain core ──► #59 ──► #60 ──► #61   without it the
                            persist  blocking  wiring   window measures
                                                 │       the wrong timestamp)
                                                 ├──► #62 PIP/IBGE (enhancement)
                                                 └──► #63 calibration (dormant)
```

| Issue | Scope | `Depends on:` | `Parallel-safe:` | Files it touches |
|---|---|---|---|---|
| #57 | EONET onset = earliest geometry | #56 | **yes**, with #58 (disjoint files) | `sources/nasa_eonet.py` + its tests/fixtures |
| #58 | `Incidente` + pure correlation core | #56 | **yes**, with #57 | `domain/incidente.py`, `domain/correlacao.py` (both new) + tests |
| #59 | Tables, provenance, merge redirect, outbox events | #58 | **no** — touches `database.py` | `database.py` + tests |
| #60 | Blocking: spatial index, open-incident windows, instrumentation | #59 | **no** — touches `database.py` | `database.py` + tests |
| #61 | Correlate during ingestion, forward-only lifecycle | #60 | **no** — touches the pipeline | `ingestion/orquestrador.py`, `reporting.py` + tests |
| #62 | Point-in-polygon against the IBGE mesh | #61 | **yes** (enhancement, off the v1 path) | `scripts/`, spatial predicate + tests |
| #63 | Calibrate windows and thresholds | #61 **deployed** through an alert surge | n/a — **dormant, no action now** | constants only |

Notes on the ordering:

- **#57 and #58 are the only pair that can run simultaneously.** They share no
  file. Start both; whichever finishes first does not block the other.
- **#57 has no code dependency on the rest, but a hard semantic one:** #60/#61
  measure Δt against onset, and until #57 lands the EONET `data_criacao` is the
  *latest* observation. Merging #57 before #61 is mandatory.
- **#59 and #60 both edit `database.py` and are serial by construction.** Do not
  attempt to parallelize them — the merge conflict is guaranteed and the second
  one needs the first one's tables.
- **#63 stays open and dormant on purpose**, the same pattern as #24 before
  Camada 8: the calibration debt has to stay visible. Its hard precondition is
  real rows in `correlacao_observacoes` plus several same-municipality CEMADEN
  alerts. Without both, proven by real query output, the correct action is none.
- Per-issue gates, every commit: `uv run pytest` · `uv run ruff check .` ·
  `uv run mypy src/`. Chained-commit style per [[patterns/git-workflow]] — CI
  green between links, never big-bang.
- The layer moves to `status: done` only after #61 passes a
  [[patterns/layer-convergence]] declared-vs-real audit. #62 and #63 are
  explicitly *not* v1-blocking.

### v1 scope decisions

Recorded here because they close gaps the clarification rounds deliberately left
to planning. They are planning decisions, not new product decisions — each one
follows from a round above.

1. **Spatial predicate v1 = `codigo_ibge` equality first, geodesic (haversine)
   distance as fallback.** Point-in-polygon against the IBGE municipal mesh is
   the *recorded preference* (Round 1, Q2) and it stays the preference — it
   simply is not in v1. It ships as upgrade issue #62, because acquiring and
   simplifying the mesh is an independent chunk of work with its own data-source
   and dependency questions, and shipping it inside the v1 path would hold the
   whole layer hostage to it. Round 2 makes this safe: a CEMADEN point can stand
   for a 5,702 km² municipality, so the administrative key is the *stronger*
   evidence anyway, and distance is only ever the fallback. Decision-path
   comparisons in raw degrees remain forbidden (degree distortion with latitude);
   bbox in degrees is allowed **only** in the blocking stage, which never decides.

2. **Every scoring constant is provisional and conservative, and says so in
   code.** Calibration is owned by dormant #63 — #58 and #60 must not tune. Two
   consequences the executor needs:
   - The starting numbers (window width, distance band, the two decision
     thresholds) are **placeholders, not derived values.** The ±6h / 50 km that
     appear at the top of this page are illustrations inherited from the
     pre-clarification spec; if v1 starts from them, they must be labelled as
     placeholders in the constant's own comment. Asserting them as evidence would
     violate `_schema.md` rule 1 and the discipline `domain/cobrade.py` imposes.
   - Ties break toward **splitting** (Round 2): in doubt, `REVISAO` or
     `NAO_VINCULA`, never `VINCULA`. Concretely, the link threshold starts high
     and the review band starts wide. Widening the band costs flagged rows —
     which is exactly the dataset #63 needs — while a loose link threshold costs
     a wrong merge, the error Round 2 ruled worse.
   - The per-type asymmetric window keeps its **structure** in v1 (per ordered
     source pair, measured against onset) even while every entry holds the same
     provisional value, so #63 edits a table and not the code shape.

3. **Branch naming for the whole batch: `camada5/<issue>-<slug>`** — e.g.
   `camada5/58-incidente-domain-core`. One branch per issue, one PR per issue,
   `Closes #<n>` on the last line of the body.

4. **Causal cascade is out of v1 entirely** — no table, no column, no code. Round
   1 Q4 split identity from cascade precisely so cascade could never act as a
   merge criterion; v1 implements identity only. #58 records the exclusion in a
   docstring pointing back at this page.

5. **The review band has no interface in v1.** `REVISAO` outcomes are written to
   `correlacao_observacoes` and nothing else — no auto-link, no notification. The
   observations table *is* the review queue until Camada 6/7 can render one. This
   is what makes the three-outcome design cheap enough to ship now.

6. **No new runtime dependency in v1.** Haversine is a dozen lines of `math`;
   blocking uses SQLite's own R-Tree if the CI matrix has it (#60 verifies
   empirically on ubuntu **and** windows before relying on it) and plain indexed
   bbox columns if it does not. Any dependency #62 might want needs its own
   `decisions/` page.
