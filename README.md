# AlertaVida

[![tests](https://github.com/CaioOlivieri/AlertaVida/actions/workflows/test.yml/badge.svg)](https://github.com/CaioOlivieri/AlertaVida/actions/workflows/test.yml)

🇧🇷 **[Leia em português](#português)**

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

---

## Português

Ingestão em tempo real de alertas de desastres naturais para o público brasileiro. Coleta dados do **CEMADEN** (operacional), com **NASA EONET**, **INMET** e **INPE** planejados.

**Arquitetura** — pipeline modular: adaptadores de fonte → detecção de mudanças → outbox transacional. Cada fonte roda em uma transação independente; a falha de uma não bloqueia as outras. Veja [wiki/_index.md](wiki/_index.md) para a arquitetura completa e o roadmap de 8 camadas.

**Como rodar e testar** — os comandos são os mesmos das seções [Running](#running) e [Tests](#tests) acima.

**Fontes de dados** — CEMADEN (dados públicos do governo federal brasileiro — Centro Nacional de Monitoramento e Alertas de Desastres Naturais); NASA EONET, INMET e INPE planejados.

**Licença** — Apache 2.0. Copyright 2026 Caio Olivieri. Veja [LICENSE](LICENSE).

**Status** — Em desenvolvimento ativo — Camada 4 do roadmap de 8 camadas (veja a [wiki](wiki/_index.md)).
