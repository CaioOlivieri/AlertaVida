status: integrated
sources: [[raw/context-md-2026-06-11.pt.md]]
updated: 2026-06-11

# Git Workflow

- **Commit convention:** `tipo(escopo): descrição` in Portuguese.
- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Scope: layer name when applicable (`camada-1`, `camada-2`, etc.). Example: `feat(camada-1): integra monitor com database, dedup e testes unitários`.
- Keep commits small and independently revertible.
- Remote: `origin` points to GitHub private repo (`CaioOlivieri/AlertaVida`). Push via `git push origin main`.

## Chained-commit style (encadeado)

Introduced in Camada 4: each sub-part is its own prompt → commit → CI run → recap before the next. Never skip CI green between chained commits. Big-bang is rejected in favor of localized review and independent reversibility.
