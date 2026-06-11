"""Classificação geográfica de alertas — Camada 4 Parte A.1.3.

Determina o escopo (BRASIL, PROXIMO, INTERNACIONAL, INDETERMINADO) de um alerta
a partir das suas coordenadas. Usa bbox + buffer configurável em vez de polígono
real (shapely) — quatro comparações numéricas, sem dependência nova, imprecisão
documentada e substituível.

A faixa BRASIL é fixa (território + pequena margem para alertas costeiros e
fronteiriços). A faixa PROXIMO recebe um buffer configurável via env var
`ALERTAVIDA_BUFFER_PROXIMO_GRAUS` (default 5° ≈ 500 km).

Mudanças no buffer só afetam alertas NOVOS. Re-classificação de alertas
existentes é responsabilidade de `scripts/reclassificar_escopos.py`
(implementado em A.1.4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import EscopoGeografico

BUFFER_PROXIMO_DEFAULT_GRAUS: float = 5.0
ENV_BUFFER_PROXIMO: str = "ALERTAVIDA_BUFFER_PROXIMO_GRAUS"


@dataclass(frozen=True)
class FaixaGeografica:
    """Bounding box geográfico em graus decimais (WGS84).

    Convenção: latitudes negativas no Sul, longitudes negativas no Oeste.
    Brasil: aproximadamente lat [-34, +5], lon [-74, -34].
    """

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def contem(self, coord: Coordenadas) -> bool:
        return (
            self.lat_min <= coord.latitude <= self.lat_max
            and self.lon_min <= coord.longitude <= self.lon_max
        )


# Bbox BRASIL inclui pequena margem para zonas marítimas costeiras e
# áreas fronteiriças (Pantanal, Amazônia ocidental). Valores fixos por
# decisão arquitetural — alterá-los é mudança de contrato, não config.
FAIXA_BRASIL: FaixaGeografica = FaixaGeografica(
    lat_min=-34.0,
    lat_max=6.0,
    lon_min=-74.0,
    lon_max=-34.0,
)


def _ler_buffer_proximo() -> float:
    """Lê o buffer PROXIMO da env var, com fallback para o default.

    Buffer inválido (não-numérico, negativo ou zero) cai para o default,
    sem levantar erro — operações de classificação não devem falhar por
    config malformada.
    """
    valor_raw = os.getenv(ENV_BUFFER_PROXIMO)
    if valor_raw is None or not valor_raw.strip():
        return BUFFER_PROXIMO_DEFAULT_GRAUS
    try:
        valor = float(valor_raw)
    except ValueError:
        return BUFFER_PROXIMO_DEFAULT_GRAUS
    if valor <= 0:
        return BUFFER_PROXIMO_DEFAULT_GRAUS
    return valor


def _faixa_proximo() -> FaixaGeografica:
    """Faixa PROXIMO = bbox BRASIL expandido em todas as direções pelo buffer."""
    buffer = _ler_buffer_proximo()
    return FaixaGeografica(
        lat_min=FAIXA_BRASIL.lat_min - buffer,
        lat_max=FAIXA_BRASIL.lat_max + buffer,
        lon_min=FAIXA_BRASIL.lon_min - buffer,
        lon_max=FAIXA_BRASIL.lon_max + buffer,
    )


def classificar_escopo(coordenadas: Coordenadas | None) -> EscopoGeografico:
    """Classifica o escopo geográfico de um alerta.

    - Sem coordenadas → INDETERMINADO (default seguro, não chuta).
    - Dentro do bbox BRASIL → BRASIL.
    - Fora do BRASIL mas dentro do bbox PROXIMO (BRASIL + buffer) → PROXIMO.
    - Fora do bbox PROXIMO → INTERNACIONAL.

    Buffer da faixa PROXIMO é lido a cada chamada — env vars podem mudar em
    runtime (testes, hot-reload). Custo é desprezível (uma leitura de env).
    """
    if coordenadas is None:
        return EscopoGeografico.INDETERMINADO
    if FAIXA_BRASIL.contem(coordenadas):
        return EscopoGeografico.BRASIL
    if _faixa_proximo().contem(coordenadas):
        return EscopoGeografico.PROXIMO
    return EscopoGeografico.INTERNACIONAL
