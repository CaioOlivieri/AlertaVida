"""Entrypoint manual para uma rodada única de ingestão multi-fonte.

Em produção, o scheduler (`agendar_ingestao` em
`alertavida.scheduler`) orquestra rodadas periódicas. Este módulo
serve para debug/desenvolvimento manual: `python -m alertavida.monitor`
executa UMA rodada e imprime o relatório no terminal.
"""

from __future__ import annotations

import sys

from alertavida.bootstrap import configurar_logging, fonte_avisos, fontes_producao
from alertavida.database import criar_banco
from alertavida.ingestion.avisos import executar_coleta_avisos, formatar_relatorio_avisos
from alertavida.ingestion.orquestrador import executar_ingestao
from alertavida.reporting import formatar_relatorio


def main() -> int:
    """Executa uma rodada de ingestão e imprime o relatório."""
    criar_banco()
    relatorio = executar_ingestao(fontes_producao())
    print(formatar_relatorio(relatorio))
    print(formatar_relatorio_avisos(executar_coleta_avisos(fonte_avisos())))
    return 0


if __name__ == "__main__":
    configurar_logging()
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
