status: integrated
sources: https://github.com/CaioOlivieri/QAbot (AGENT.md + wiki/ format)
updated: 2026-06-11

## LLM-Wiki Schema for AlertaVida

### Layers

- **raw/** — immutable copies of original documents. Never edited, never translated.
- **00_inbox/** — draft notes before they find their permanent page.
- **curated/** (future) — pages that passed review, separated from drafts.

### Page format

Every page has a header:

```
status: <one of: integrated | orphan-in-practice | orphan-total | proposal | open | draft | verified | implemented | done | in-progress | blocked>
sources: [[raw/...]] or real file paths
updated: 2026-06-11
```

Internal links use the [[wikilink]] convention.

### Operations

- **ingest** — learn something durable: update the page, then update `_index.md` and `_integration-state.md` if wiring changed.
- **query** — read `_integration-state.md` before architecture changes.
- **lint** — check that page count in `_index.md` matches filesystem; check raw/ immutability.

### Discipline rules

1. Only assert test/pipeline behavior based on real execution output (`uv run pytest`, logs in raw/) — never by inference.
2. Every new architectural decision requires a page in `decisions/` + a line in `_index.md` + updating `_integration-state.md` when wiring changes.
3. `raw/` is immutable and never translated. All curated content is in English.
