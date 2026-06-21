"""Entrypoint manual para uma rodada única de ingestão multi-fonte.

Em produção, o scheduler (`agendar_ingestao` em
`alertavida.scheduler`) orquestra rodadas periódicas. Este módulo
serve para debug/desenvolvimento manual: `python -m alertavida.monitor`
executa UMA rodada e imprime o relatório no terminal.
"""

from __future__ import annotations

import logging
import os
import sys

from alertavida.database import criar_banco
from alertavida.ingestion.orquestrador import executar_ingestao
from alertavida.reporting import formatar_relatorio
from alertavida.sources.cemaden import CemadenSource
from alertavida.sources.nasa_eonet import NasaEonetSource


def main() -> int:
    """Executa uma rodada de ingestão e imprime o relatório."""
    criar_banco()
    sources = [CemadenSource(), NasaEonetSource()]
    relatorio = executar_ingestao(sources)
    print(formatar_relatorio(relatorio))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
