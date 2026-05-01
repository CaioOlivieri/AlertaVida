from __future__ import annotations

from enum import Enum
import unicodedata


def _normalizar(s: str) -> str:
    normalized = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


class NivelRisco(str, Enum):
    BAIXO = "BAIXO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"
    MUITO_ALTO = "MUITO_ALTO"

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
        }
        if normalized in mapping:
            return mapping[normalized]

        raise ValueError(f"Nível de risco desconhecido: {valor}")


class TipoEvento(str, Enum):
    HIDROLOGICO = "HIDROLOGICO"
    GEOLOGICO = "GEOLOGICO"
    METEOROLOGICO = "METEOROLOGICO"
    INCENDIO = "INCENDIO"
    OUTROS = "OUTROS"

    @classmethod
    def from_string(cls, valor: str | None) -> "TipoEvento":
        if valor is None or not valor.strip():
            return cls.OUTROS

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
            "chuva intensa",
            "meteorologico",
            "vento forte",
        }
        incendio = {
            "queimada",
            "incendio",
            "fogo",
        }

        if normalized in hidrologico:
            return cls.HIDROLOGICO
        if normalized in geologico:
            return cls.GEOLOGICO
        if normalized in meteorologico:
            return cls.METEOROLOGICO
        if normalized in incendio:
            return cls.INCENDIO
        return cls.OUTROS
