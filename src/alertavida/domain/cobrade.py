"""
Mapeamento de eventos de fontes externas para códigos COBRADE.

COBRADE = Classificação e Codificação Brasileira de Desastres, codificação
oficial da Defesa Civil brasileira (IN nº 01/2012 do Ministério da
Integração Nacional, com procedimentos atualizados pela IN nº 02/2016).
Hierárquica em 5 níveis: Categoria.Grupo.Subgrupo.Tipo.Subtipo.

Na Camada 4 do AlertaVida, classificamos APENAS até subgrupo (Tipo=0,
Subtipo=0). Distinção entre subtipos exige cruzamento com topografia, série
temporal de chuva e densidade urbana — escopo da Camada 5. Ver
wiki/decisions/tipoevento-cobrade-classification.md.
"""

import re
from typing import Final

# Mapeamento de tipoevento bruto do CEMADEN para código COBRADE de subgrupo.
# Inspeção empírica de 240 alertas em 4 amostras de 01-02/05/2026 revelou
# apenas 2 tipos físicos entregues pela API:
#   - "Risco Hidrológico"    → Hidrológico (subgrupo 1.2)
#   - "Movimentos de Massa"  → Geológico / Movimento de massa (subgrupo 1.1.3)
# Adicionar entradas aqui SOMENTE quando novas amostras empíricas revelarem
# outros tipos. Não inventar mapeamentos baseado em suposição.
EVENTO_CEMADEN_PARA_COBRADE: Final[dict[str, str]] = {
    "Risco Hidrológico": "1.2.0.0.0",
    "Movimentos de Massa": "1.1.3.0.0",
}

# Mapeamento de categorias EONET v3 (id em inglês) para código COBRADE.
# Cada categoria é mapeada ao nível mais específico que a terminologia
# EONET determina SEM inferência. Quando a categoria não distingue entre
# subgrupos, paramos no grupo (Tipo=Subtipo=0):
#   - floods → grupo Hidrológico (1.2.0.0.0): categoria não distingue entre
#     inundação gradual, enxurrada, alagamento etc.
#   - severeStorms → grupo Meteorológico (1.3.0.0.0): categoria não distingue
#     entre ciclone, tornado, tempestade etc.
#   - wildfires → subgrupo Seca (1.4.1.0.0): incêndio florestal é tipo dentro
#     do subgrupo Seca (1.4.1.3), paramos no subgrupo (Tipo=Subtipo=0).
#   - volcanoes → subgrupo Emanação Vulcânica (1.1.2.0.0).
#   - landslides → subgrupo Movimento de Massa (1.1.3.0.0).
EVENTO_EONET_PARA_COBRADE: Final[dict[str, str]] = {
    "wildfires": "1.4.1.0.0",
    "floods": "1.2.0.0.0",
    "severeStorms": "1.3.0.0.0",
    "volcanoes": "1.1.2.0.0",
    "landslides": "1.1.3.0.0",
}

# Formato COBRADE: 5 níveis numéricos separados por ponto.
_FORMATO_COBRADE: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+\.\d+\.\d+$")


def validar_formato(codigo: str) -> bool:
    """Retorna True se a string segue o formato N.N.N.N.N (5 níveis numéricos)."""
    return bool(_FORMATO_COBRADE.match(codigo))


def mapear_cemaden(tipo_evento: str) -> str | None:
    """
    Mapeia um tipoevento bruto do CEMADEN para código COBRADE de subgrupo.
    Retorna None se o tipo não está no mapeamento conhecido.
    """
    return EVENTO_CEMADEN_PARA_COBRADE.get(tipo_evento)


def mapear_eonet(categoria: str) -> str | None:
    """Mapeia uma categoria EONET v3 (id em inglês) para código COBRADE.
    Retorna None se a categoria não está no mapeamento conhecido."""
    return EVENTO_EONET_PARA_COBRADE.get(categoria)
