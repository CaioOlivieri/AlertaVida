"""Enums de domínio do AlertaVida.

A taxonomia de `TipoEvento` segue os 5 subgrupos da Classificação e Codificação
Brasileira de Desastres (COBRADE), padrão alinhado com EM-DAT/CRED. Cada
DataSource (Camada 4) implementa seu próprio mapeamento da terminologia da
fonte para esses valores neutros.
"""

from __future__ import annotations

import unicodedata
from enum import Enum


def _normalizar(s: str) -> str:
    normalized = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


class NivelRisco(str, Enum):
    BAIXO = "BAIXO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"
    MUITO_ALTO = "MUITO_ALTO"
    INDETERMINADO = "INDETERMINADO"

    @classmethod
    def from_string(cls, valor: str | None) -> "NivelRisco":
        if valor is None or not valor.strip():
            raise ValueError("Nível de risco ausente ou inválido")

        normalized = _normalizar(valor).replace(" ", "_")
        mapping = {
            "baixo": cls.BAIXO,
            "moderado": cls.MODERADO,
            "alto": cls.ALTO,
            "muito_alto": cls.MUITO_ALTO,
            "muitoalto": cls.MUITO_ALTO,
            "indeterminado": cls.INDETERMINADO,
        }
        if normalized in mapping:
            return mapping[normalized]

        raise ValueError(f"Nível de risco desconhecido: {valor}")


class TipoEvento(str, Enum):
    """Subgrupos COBRADE de desastres naturais (Grupo 1).

    - HIDROLOGICO    (1.2.x): inundação, enxurrada, alagamento.
    - GEOLOGICO      (1.1.x): terremoto, vulcanismo, movimento de massa, erosão.
    - METEOROLOGICO  (1.3.x): ciclones, tempestades, tornados, granizo, vendaval.
    - CLIMATOLOGICO  (1.4.x): seca, estiagem, incêndio florestal, baixa umidade.
    - BIOLOGICO      (1.5.x): epidemias, infestações, pragas.
    - INDETERMINADO         : fonte não classifica ou string desconhecida.
    """

    HIDROLOGICO = "HIDROLOGICO"
    GEOLOGICO = "GEOLOGICO"
    METEOROLOGICO = "METEOROLOGICO"
    CLIMATOLOGICO = "CLIMATOLOGICO"
    BIOLOGICO = "BIOLOGICO"
    INDETERMINADO = "INDETERMINADO"

    @classmethod
    def from_string(cls, valor: str | None) -> "TipoEvento":
        if valor is None or not valor.strip():
            return cls.INDETERMINADO

        normalized = _normalizar(valor)

        hidrologico = {
            "risco hidrologico",
            "hidrologico",
            "hidrologia",
            "enchente",
            "inundacao",
            "alagamento",
        }
        geologico = {
            "movimentos de massa",
            "movimento de massa",
            "deslizamento",
            "geologico",
        }
        meteorologico = {
            "tempestade",
            "chuva",
            "meteorologico",
            "vento forte",
        }
        climatologico = {
            "queimada",
            "incendio",
            "fogo",
        }
        biologico: set[str] = set()

        if normalized in hidrologico:
            return cls.HIDROLOGICO
        if normalized in geologico:
            return cls.GEOLOGICO
        if normalized in meteorologico:
            return cls.METEOROLOGICO
        if normalized in climatologico:
            return cls.CLIMATOLOGICO
        if normalized in biologico:
            return cls.BIOLOGICO
        return cls.INDETERMINADO


class EscopoGeografico(str, Enum):
    """Relevância geográfica de um alerta para o usuário brasileiro.

    Calculado em `domain/geographic.py` (Camada 4 Parte A.1.3) a partir das
    coordenadas do alerta e de buffers configuráveis via env var.

    - BRASIL          : dentro do bbox do território brasileiro.
    - PROXIMO         : fora do Brasil mas dentro do buffer configurado.
    - INTERNACIONAL   : fora do buffer.
    - INDETERMINADO   : alerta sem coordenadas válidas (default seguro).
    """

    BRASIL = "BRASIL"
    PROXIMO = "PROXIMO"
    INTERNACIONAL = "INTERNACIONAL"
    INDETERMINADO = "INDETERMINADO"
