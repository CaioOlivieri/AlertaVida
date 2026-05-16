"""Pacote de fontes de dados (DataSources) — Camada 4 Parte B.

Cada DataSource encapsula a coleta de alertas de uma origem específica
(CEMADEN, EONET, INMET, INPE) e produz objetos Alerta de domínio
validados. O orquestrador (ingestao/orquestrador.py, Parte B.2) consome
DataSources sem conhecer suas particularidades — padrão Adapter.

Exports públicos:
    DataSource         — interface ABC (sources/base.py)
    ResultadoColeta    — dataclass frozen de retorno de coletar() (sources/base.py)
    FalhaDeColeta      — exceção tipada para falhas irrecuperáveis (sources/base.py)

Implementações concretas (B.1.b em diante):
    CemadenSource      — sources/cemaden.py (B.1.b)
    NasaEonetSource    — sources/nasa_eonet.py (Parte C)
"""

from alertavida.sources.base import DataSource, FalhaDeColeta, ResultadoColeta
from alertavida.sources.cemaden import CemadenSource

__all__ = [
    "DataSource",
    "FalhaDeColeta",
    "ResultadoColeta",
    "CemadenSource",
]
