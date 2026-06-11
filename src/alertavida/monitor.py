"""Entrypoint manual para uma rodada única de ingestão CEMADEN.

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
from alertavida.ingestion.orquestrador import RelatorioIngestao, executar_ingestao
from alertavida.sources.cemaden import CemadenSource


def _formatar_relatorio(relatorio: RelatorioIngestao) -> str:
    """Formata RelatorioIngestao para saída em terminal."""
    linhas = [f"{relatorio.agora.isoformat()}: rodada concluída"]
    for rf in relatorio.por_fonte:
        if rf.falha_coleta:
            linhas.append(
                f"  {rf.fonte.value}: FALHA de coleta "
                f"({rf.duracao_segundos:.2f}s)"
            )
        else:
            linhas.append(
                f"  {rf.fonte.value}: {rf.coletados} coletados "
                f"({rf.novos} novos, {rf.atualizados} atualizados, "
                f"{rf.reativados} reativados, {rf.inalterados} inalterados, "
                f"{rf.descartados} descartados) "
                f"em {rf.duracao_segundos:.2f}s"
            )
    linhas.append(f"Total: {relatorio.total} alertas")
    return "\n".join(linhas)


def main() -> int:
    """Executa uma rodada de ingestão e imprime o relatório."""
    criar_banco()
    sources = [CemadenSource()]
    relatorio = executar_ingestao(sources)
    print(_formatar_relatorio(relatorio))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
