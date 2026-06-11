# AlertaVida

[![tests](https://github.com/CaioOlivieri/AlertaVida/actions/workflows/test.yml/badge.svg)](https://github.com/CaioOlivieri/AlertaVida/actions/workflows/test.yml)

Real-time multi-source ingestion of natural-disaster alerts for the Brazilian public. Ingests data from **CEMADEN** (operational), with **NASA EONET**, **INMET**, and **INPE** planned.

## Architecture

Modular pipeline: source adapters → change detection → transactional outbox. Each source runs in an independent transaction; failure of one does not block others. See [wiki/_index.md](wiki/_index.md) for the full architecture and the 8-layer roadmap.

## Running

```bash
uv sync              # install everything (dev included via dependency-groups PEP 735)
uv sync --frozen     # reproduce exact lock
python -m alertavida.monitor     # one-shot debug run
python -m alertavida.scheduler   # continuous service (Ctrl+C to stop)
```

## Tests

```bash
uv run pytest                # full suite (network and time.sleep are mocked)
uv run pytest -m integration  # CEMADEN contract test (hits real API)
```

## Data sources

- **CEMADEN** — public data from the Brazilian federal government (Centro Nacional de Monitoramento e Alertas de Desastres Naturais)
- **NASA EONET** — planned
- **INMET** — planned
- **INPE** — planned

## License

Apache 2.0. Copyright 2026 Caio Olivieri. See [LICENSE](LICENSE).

## Status

Active development — Layer 4 of the 8-layer roadmap (see [wiki](wiki/_index.md)).
