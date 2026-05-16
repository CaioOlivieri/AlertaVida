"""Orquestração de ingestão multi-fonte (Camada 4, Parte B)."""

from alertavida.ingestion.orquestrador import (
    RelatorioFonte,
    RelatorioIngestao,
    executar_ingestao,
)

__all__ = ["RelatorioFonte", "RelatorioIngestao", "executar_ingestao"]
