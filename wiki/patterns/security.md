status: integrated
sources: [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-06-11

# Security

- Credentials go in `.env` (gitignored). Never hardcode keys, tokens, or passwords in code.
- `.env.example` documents required variables without real values — this one is committed.
- `data/alertavida.db` is gitignored — never commit real data.
- When adding a new data source (INMET, NASA EONET, Cell Broadcast), the key goes into `.env` first, then referenced via `os.getenv()` in code.
- Never expose precise coordinates of critical infrastructure (CEMADEN stations, communication towers) in public logs or API responses without obfuscation.
