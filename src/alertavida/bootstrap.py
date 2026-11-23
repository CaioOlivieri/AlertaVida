"""Composição compartilhada pelos dois entrypoints (issue #131).

`monitor.py` (rodada única) e `scheduler.py` (serviço contínuo) montavam a
lista de fontes e o logging cada um por conta própria — adicionar uma fonte
(INMET, INPE) exigia lembrar de editar os dois. Este módulo é o único lugar
onde a lista de fontes de produção e o formato de log existem.
"""

from __future__ import annotations

import logging
import os

from alertavida.sources.base import DataSource
from alertavida.sources.cemaden import CemadenSource
from alertavida.sources.nasa_eonet import NasaEonetSource

FORMATO_LOG = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def fontes_producao() -> list[DataSource]:
    """Instâncias novas das fontes de produção, na ordem de coleta.

    Nova fonte entra aqui — e só aqui.
    """
    return [CemadenSource(), NasaEonetSource()]


def configurar_logging() -> None:
    """Logging dos entrypoints: nível em `LOG_LEVEL` (default INFO)."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format=FORMATO_LOG)
