status: integrated
sources: [[decisions/sdd-practices-from-spec-kit]], issues #30/#10
updated: 2026-07-02

# Spec Checklist ("unit tests for English")

Quality gate run **against the specification itself**, before any implementation.
Adapted from spec-kit's `/speckit.checklist` concept ([[decisions/sdd-practices-from-spec-kit]]).
Every question below exists because skipping it already cost this project real damage.

## When it is mandatory

- Before closing the spec of any layer (Camadas 5–8) — i.e., before `/plan`-level
  technical decisions start.
- Before implementing any feature that touches an **external data source**
  (new source, new field, new endpoint, schema change).

## The checklist

1. **Empirical claims verified?** Every statement about an external API's behavior
   (field names, value formats, lifecycle semantics) is backed by **captured real
   samples** — not by documentation, memory, or a previous wiki page.
   *Origin: issue #30 — the spec claimed a `tipoevento` field; the real payload
   never had it. Every CEMADEN alert was misclassified for ~2 months with green CI.*
2. **Fixtures match reality?** Test fixtures use the **real payload shape**
   (verbatim sample items where possible), not an idealized shape.
   *Origin: issue #30 — fixtures used `tipoevento`/`codigoalerta` with bare
   category values, a shape the API never sent, which is exactly why the suite
   stayed green while production misclassified everything.*
3. **Tests assert the property, not a proxy?** Each acceptance test verifies the
   property that matters, not a stand-in for it.
   *Origin: the daily CEMADEN contract test measured acceptance rate (items become
   `Alerta`) while the property that mattered was classification rate — a
   misclassified alert still counted as accepted.*
4. **Measurable acceptance criteria?** Every requirement has a criterion that a
   test (or a human with a checklist) can evaluate as pass/fail.
5. **No ambiguous terms?** No term that two readers would resolve differently
   ("recent", "nearby", "relevant") survives without a number or a definition.
6. **Non-goals declared?** What the spec deliberately does NOT cover is written
   down — absence of a statement is not a decision.
7. **Invariants cross-checked?** The spec does not contradict
   [[patterns/resilience-invariants]] or the atomicity/honesty rules in
   [[patterns/code-conventions]].

## Explicit-skip rule

Skipping this checklist (or any single item) is allowed — for spikes, throwaway
prototypes, exploratory work — but the skip MUST be declared in writing where the
spec lives (e.g., "spike: checklist skipped on purpose, items 1–2 still apply").
An undeclared skip is an omission; a declared skip is an auditable decision.
