"""Formatação de relatórios de ingestão para saída em terminal.

Compartilhado entre monitor.py (one-shot) e scheduler.py (serviço contínuo).
"""

from __future__ import annotations

from alertavida.ingestion.orquestrador import RelatorioIngestao


def formatar_relatorio(relatorio: RelatorioIngestao) -> str:
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
