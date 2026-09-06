status: open
sources: https://developers.google.com/weathernext, https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_2_0_0, https://developers.google.com/weathernext/guides/bigquery, https://developers.google.com/weathernext/guides/dissemination, https://storage.googleapis.com/weathernext-public/terms-of-use.pdf (read in full, 2026-08-11), [[projects/layer-5-correlation]], [[raw/analise-weathernext-skill-2026-08-24]], [[decisions/weathernext-surge-watch-design]]
updated: 2026-09-05

# WeatherNext: Anticipation Track, Not a DataSource

On 2026-08-11 the maintainer evaluated integrating Google DeepMind's
**WeatherNext 2** into AlertaVida (issue #68). Decision, in one line: **rejected
as a Camada 4 `DataSource`, adopted as a phased internal anticipation track**
(#69–#72), with public display deferred behind a written legal path (#72).

## What it is (from the official docs, not summaries)

- Global ML weather forecast: **0.25° grid (~28 km)**, 100+ variables, 6-hour
  steps up to a **15-day horizon**, **64 ensemble members**.
- 4 runs/day (00/06/12/18 UTC), each released ~7h30 after init to BigQuery
  (`weathernext_2_0_0`, `weathernext_2_0_0_mean` — Analytics Hub subscription
  after a data-request form), Earth Engine, and GCS (Zarr).
- Output is a **gridded field** ("X mm of rain over cell Y at hour Z"), not
  discrete alerts. This single fact drives the whole decision.

## Why not a DataSource

- **No `cod_alerta`.** A grid has no stable event identity; any id we minted
  would churn through `ChangeDetector` on every 6-hour run, and resolution by
  inference would fire spurious `AlertaResolvido`/`AlertaReativado` cycles.
- **`nivel_risco` and COBRADE would be invented.** Deriving a risk level and a
  disaster classification from a precipitation threshold we chose is exactly
  the heuristic invention data honesty forbids — the same reason EONET ships
  `nivel_risco=INDETERMINADO` instead of a magnitude-derived level
  ([[decisions/decision-record]]).
- **Product shift.** Ingesting forecasts as alerts turns AlertaVida from an
  aggregator of official alerts into a producer of its own — a change of
  responsibility, not of source. The terms themselves state the data "in no way
  replaces official alerts, warnings or notices" published by government
  meteorological agencies. The meteorological-source gap is INMET's to fill
  (official, legally mandated, publishes actual alerts), not WeatherNext's.

## Licensing (read from the terms of use, version of 2025-11-12)

Two regimes, split at whether the data's valid time is more than 48 h in the
past:

- **Historic (> 48 h): CC BY 4.0.** Attribution only. Everything in #69 runs
  entirely in this regime.
- **Real-time (≤ 48 h): GDM Real-Time Weather Forecasting Experimental Data
  Terms of Use.** The clauses that shaped this decision:
  - **§2(a): "any internal purpose" is permitted without restriction.** The
    entire #70/#71 design lives inside this clause.
  - **§3: only a Non-Retrievable Value Added Service may be shared publicly.**
    Sub-setting of areas, selection of time-steps/parameters/runs, colouring
    and reformatting are explicitly *unmodified* data — so "the forecast for
    municipality X" can never be displayed publicly, no matter how it is
    dressed up.
  - **§4(b):** public findings must carry the citation "This data is intended
    for experimental modelling only and is not intended, validated, or
    approved for real world use" — in direct tension with a life-safety
    product, hence #72's written-legal-path precondition.
  - **§6:** as-is, "not intended for consumer use", does not replace official
    agency alerts; Google's aggregate liability capped at USD 500; access
    revocable, fees possible on one month's notice.
  - **§1:** Brazil is not in the restricted-country list.

### Commercial use is not prohibited — the constraint is the sharing *form*

Recorded 2026-08-12, after the question came up while filling the access
request form. Re-read of the terms establishes:

**There is no non-commercial clause.** The grant is "non-exclusive,
royalty-free, revocable, non-transferable and non-sublicensable" and says
nothing about money changing hands; CC BY 4.0 (historic data) permits
commercial use explicitly. What §3 restricts is the *shape* of what leaves the
building:

| What is shared | Permitted audience | Paid? |
|---|---|---|
| Non-Retrievable VAS (grid not recoverable) | anyone, including by publication | not restricted |
| Retrievable VAS (grid recoverable) | clearly identified, known third parties, for their own internal use, no onward sharing | not restricted |
| Unmodified data (incl. sub-set areas, selected time-steps/runs) | controlled distribution only — never public | n/a |

**B2G fits these terms better than a public consumer app.** Selling to a
municipal Defesa Civil is precisely §3's "clearly identified and known third
party, using it for their own internal purposes" — the case the terms *do*
allow for Retrievable VAS. A product open to the general public is the more
restricted scenario, not the less.

**The real obstacle is §6, not the licence.** Data is as-is, "not intended for
consumer use", does not replace official agency alerts, Google's aggregate
liability is capped at **USD 500**, and the customer indemnifies Google. Under
a paid contract with a civil-protection body, that means carrying contractual
responsibility for a life-safety service built on data whose provider disclaims
fitness and caps exposure at five hundred dollars. That is a commercial
problem, not a legal-permission one, and it points at the same two exits
already recorded as #72's precondition: written permission from
weathernext@google.com, or the Google Maps Platform Weather API, whose
production terms carry no such posture.

**Consequence for the current plan: none.** #69 and #70 are internal and touch
none of this. It only means that if a B2G route becomes real, the *data
channel* likely changes before the product ships — which is why #72 is gated on
the legal path rather than on engineering.

## The phased plan

| Phase | Issue | What | When |
|---|---|---|---|
| Kickoff | #68 | this page | done |
| A | #69 | data access + offline skill validation over known Brazilian events (CC BY historic; **STOP gate for the whole track**) | **done, 2026-08-24 — qualified PASS, see below** |
| B | #70 | surge watch: daily forecast artifact (`scripts/`, outside the runtime) + high-frequency CEMADEN capture for the Round 2 discriminator | **done, 2026-09-05 — see [[decisions/weathernext-surge-watch-design]]** |
| C | #71 | physical-plausibility annotation on `REVISAO` rows, input to #63 labelling | after #61 + #70 |
| D | #72 | public worsening-trend indicator on `Incidente` (Non-Retrievable VAS or Maps Platform Weather API) | dormant — after Camada 7 + written legal path |

## Timing against the Camada 5 batch

Nothing here touches the v1 critical path (#59 → #60 → #61, serial on
`database.py` and the pipeline). #69 is offline analysis; #70 touches
`scripts/` only and introduces **no runtime dependency** — the daily job
materializes a small local artifact and the runtime, when it ever reads it,
reads a local file (same posture as v1 scope decision #6 on the layer page).

The one real deadline is seasonal: **#70 must be watching before the Oct–Mar
rainy season**, because that surge is simultaneously (a) the only data source
for the Round 2 centroid-vs-risk-point discriminator, which is otherwise
waiting on luck, and (b) when `correlacao_observacoes` fills with the candidate
pairs dormant #63 needs. Missing the season costs a year of field data.

## The honest caveat #69 exists to measure

0.25° ≈ 28 km. Brazilian flash floods and landslides are subgrid phenomena; at
best the ensemble sees the precipitation that triggers them, never the event
itself. Whether that signal arrives with useful lead time at municipal scale is
**unknown until measured** — the same `_schema.md` rule 1 discipline that
forced the Round 2 live fetch instead of trusting fixtures. If #69's answer is
no, the correct outcome is to close #70–#72 as not planned and keep only this
page as the written answer for the next time the question comes up (the
[[decisions/sdd-practices-from-spec-kit]] precedent).

## #69 verdict, 2026-08-24: qualified PASS — proceed to #70

Measured against 9 real Brazilian flood events (NASA EONET/GDACS, since
WeatherNext's 2025-10-03 coverage start; below the 10–20 target — see
[[raw/analise-weathernext-skill-2026-08-24]] for why), using only the
WeatherNext 2 **mean** field (cost rule; ensemble excluded) and ERA5 as
ground truth (Open-Meteo Archive API, pipeline independently validated
against the documented Zona da Mata Mineira / Juiz de Fora disaster):

- **6 of 9 events** show a precipitation signal ≥50% of the ERA5-observed
  magnitude at the correct 0.25° grid cell, even at 1-day lead.
- **5 of 9** keep that signal useful out to 7-day lead.
- **2 of 9** (EONET_16409, EONET_20298) show no useful signal at *any*
  tested lead (1–11 days) — reported without cherry-picking, same as the
  6 hits.
- Signal degrades to weak/miss for all 9 by 7–11 days, matching known NWP
  predictability limits.

**Statistical caveat — read the percentages as qualitative, not precise.**
N=9. The ≥50% HIT threshold is a cutoff chosen for this analysis, not a
property of the problem; with N=9, one event moving category shifts any
percentage by ~11 points ("67% at 1d" and "56% at 7d" differ by exactly one
event, EONET_18043's intermittent HIT). Do not cite these numbers later as
a precise skill rate.

**The 22% miss rate does not disqualify #70.** #70 is an *internal capture
trigger* (surge-watch → higher-frequency CEMADEN capture), not a
user-facing alert. Against that use, a ~78% hit rate means catching roughly
4 surge events out of 5, against catching **zero** today. Read the miss
rate as the size of the gap #70 leaves, not as evidence the track should
stop.

**Open, unresolved question: mean vs. ensemble.** This analysis cannot tell
"the model didn't see the event" apart from "the mean smoothed out a signal
present in part of the 64-member ensemble" — the mean is a deterministic
average, and the two events that missed could plausibly be
ensemble-visible. Left open deliberately: testing it would cost ~189 GB per
event at 1-day lead alone (≈37% of the 1 TiB free tier for both), and
would not change this verdict either way — #70 proceeds regardless, carrying
this caveat. Revisit only if #70's real-world false-negative rate makes it
worth spending that budget.

**Gate outcome: not "close #70–#72."** Skill was demonstrated for a
majority of real events with real lead time — not the zero-signal outcome
that would have triggered the not-planned close. #70 proceeds, scoped with
the miss rate and the mean/ensemble open question above in mind.
