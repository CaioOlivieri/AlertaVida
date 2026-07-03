status: integrated
sources: [[decisions/sdd-practices-from-spec-kit]], issues #10/#30
updated: 2026-07-02

# Layer Convergence Ritual

End-of-layer audit that reconciles **declared state** (issues, wiki claims,
roadmap) with **actual state** (code, tests, real execution). Adapted from
spec-kit's `/speckit.converge` concept ([[decisions/sdd-practices-from-spec-kit]]).
The [[patterns/spec-checklist]] is the entry gate of a layer; this is the exit gate.

## Why it exists

Both drift directions have already happened in this repo:

- **Issue→code drift:** issue #10 (Camada 4 C.3) sat open for weeks with the work
  100% complete — nobody reconciled the tracker against reality after the commits
  landed.
- **Doc→reality drift:** issue #30 — the wiki asserted payload behavior
  (`tipoevento` field) that the real API never had; the claim survived because
  nothing ever re-checked it against execution.

`_integration-state.md` covers *wiring* drift, but nothing covered *claims* and
*tracker* drift until this ritual.

## The ritual — run before declaring "Camada N complete"

1. **Tracker vs code:** every open issue tagged to the layer — is it still real
   work, already done (close it, like #10), or obsolete (close with rationale)?
2. **Claims vs execution:** every empirical claim the layer's wiki pages make
   about external systems — re-verify against fresh real samples or live
   execution (`uv run pytest -m integration`, inspector output in `wiki/raw/`).
   Never re-assert by inference (discipline rule in [[_schema]]).
3. **Wiring vs table:** `_integration-state.md` module table matches the actual
   imports/flow (spot-check the layer's new modules).
4. **Changelog + decision record:** every decision made during the layer has its
   line in [[decisions/decision-record]] and [[changelog]]; anything decided only
   in chat/PR threads gets written down now or is lost.
5. **Declare residue explicitly:** anything found but deliberately not fixed
   becomes an issue or a written note — same explicit-skip principle as
   [[patterns/spec-checklist]].

Output: a short entry in [[changelog]] ("Camada N convergence: ...") listing what
was reconciled. If nothing drifted, say so — a clean audit is information too.
