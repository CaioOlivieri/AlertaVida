status: implemented
sources: https://github.com/github/spec-kit (evaluated 2026-07-02), issues #30/#10/#33
updated: 2026-07-02

# SDD Practices Adopted from spec-kit (and What Was Rejected)

On 2026-07-02, [github/spec-kit](https://github.com/github/spec-kit) (GitHub's
Spec-Driven Development toolkit, MIT, ~117k stars) was evaluated for adoption.
**Full adoption was rejected; five of its practices were adopted as wiki
conventions with zero tooling.** This page records both sides so the question
"should we use spec-kit?" has a written answer the next time it comes up.

## Why full adoption was rejected

AlertaVida already practices SDD through the LLM-Wiki — the mapping is direct:

| spec-kit concept | AlertaVida equivalent |
|---|---|
| `constitution.md` | `AGENT.md` + `wiki/patterns/` (data honesty, 23 invariants, conventions) |
| `spec.md` per feature | `wiki/projects/layer-N-*.md` |
| `plan.md` + tech decisions | `wiki/decisions/` (ADRs with rationale) |
| `tasks.md` → issues | Issue batches (e.g., maintainability review #17–#24) |
| `/speckit.implement` | Chained-commit style ([[patterns/git-workflow]]) |

Installing it would create **dual sources of truth** (`wiki/` vs
`.specify/`+`specs/`), migration cost with no team to amortize it (solo dev +
AI agents; spec-kit's bundles are role-based for teams), and concrete convention
conflicts (spec-kit writes agent commands to `.claude/commands/`, which this
repo's `.gitignore` excludes entirely). The wiki also captures something
spec-kit's per-feature artifacts don't: durable cross-feature knowledge
(invariants, integration state, decision history).

**Reconsider if:** (1) the team grows beyond solo+agents, or (2) Camada 7's
frontend starts as a separate greenfield repo — greenfield is where spec-kit is
strongest and there would be no wiki conflict there.

## The five adopted practices

1. **Spec checklist** ([[patterns/spec-checklist]]) — quality gate against the
   spec itself, from `/speckit.checklist`. Evidence of the gap: issue #30.
2. **Layer convergence ritual** ([[patterns/layer-convergence]]) — declared state
   vs reality audit at layer end, from `/speckit.converge`. Evidence: issues #10
   and #30 (both drift directions happened).
3. **`## Clarifications` section in layer pages** — structured questioning before
   technical planning, answers recorded in the layer page rather than lost in
   chat, from `/speckit.clarify`. First application: `projects/layer-5-correlation`.
4. **Dependency/parallel markers on issue batches** — `Depends on:` /
   `Parallel-safe:` lines, from spec-kit's `[P]` task markers. Convention recorded
   in [[patterns/ai-agent-workflow]].
5. **Explicit-skip rule** — skipping a gate is allowed but must be declared in
   writing (embedded in [[patterns/spec-checklist]]). Turns omission into an
   auditable decision.

## Rejected pieces, individually

- **`constitution.md`** — redundant with `AGENT.md` + patterns pages.
- **`specs/NNN-feature/` directory structure** — would compete with
  `wiki/projects/`; two places for the same information.
- **Bundles/presets/extensions machinery** — presupposes multiple personas and
  template distribution; no consumer here.
- **Branch-per-feature automation** — the issue→`<type>/N-slug`→PR flow
  established 2026-07-02 already covers it with less machinery.
