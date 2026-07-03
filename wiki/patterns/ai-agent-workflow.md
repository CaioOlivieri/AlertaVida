status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]] (§9)
updated: 2026-07-02

# AI Agent Workflow

## Role division

- **Claude (chat web)** — architect. Design decisions, critical review, prompt formulation. Does not touch project files.
- **Claude Code (terminal)** — executor. Reads codebase via AGENT.md, edits files, runs tests, provides recap.
- **Cursor (IDE)** — editor + visual review. Diff, navigation, commits.

## Standard flow

1. Architectural discussion in chat → prompt formulated
2. Prompt pasted in Claude Code → execution with recap
3. Recap brought back to chat → validation against deviations
4. Commit in Cursor after approval

## Anti-patterns learned

- **Loose literal strings in prompts** — agent "beautifies" (`"Chuva"` became `"Chuva intensa"` on 2026-04-30, see issue #1). Always mark with "use these strings exactly".
- **Implicit scope** — agent touches files not requested. Always list `DO NOT modify:` in the prompt.
- **Missing recap** — deviations pass silently. Always request `git diff --stat` at the end.

## Recommended prompt structure

1. **Context:** "Read AGENT.md before anything else."
2. **Objective:** what to achieve (not how)
3. **Functional requirements:** expected behavior, edge cases
4. **Non-functional requirements:** robustness, tests, conventions
5. **Success criteria:** how to know it's done
6. **No-modify scope:** explicit list of untouchable files

## Issue batches: dependency and parallelism markers

When a review or a layer plan generates a batch of issues (e.g., the 2026-07-02
maintainability review, #17–#24), each issue body declares:

- `Depends on: #N, #M` — issues that must merge first (omit if none).
- `Parallel-safe: yes|no` — whether it can be worked simultaneously with its
  siblings without merge conflicts or semantic coupling.

Adapted from spec-kit's `[P]` task markers ([[decisions/sdd-practices-from-spec-kit]]).
Purpose: make parallelizable work visible so it can be split between agents
(Claude Code, opencode) and the maintainer instead of defaulting to a serial
queue.
