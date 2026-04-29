# AlertaVida

Sistema de monitoramento e ingestao de alertas de desastres em tempo real.

## Como rodar

```bash
pip install -e ".[dev]"
python -m alertavida.monitor
python -m alertavida.scheduler
```

## Testes

```bash
python -m pytest
```

Detalhes de arquitetura e contexto: [CONTEXT.md](./CONTEXT.md).
