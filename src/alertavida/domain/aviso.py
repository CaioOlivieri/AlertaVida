"""Aviso meteorológico — contexto de incidentes, nunca alerta (issue #153).

Um aviso do INMET é uma previsão REGIONAL de condições: medido em
2026-11-23, um único aviso de Tempestade cobria 3.059 municípios em 19
estados por um dia inteiro. Isso não cabe na identidade da Camada 5 — um
Incidente nunca atravessa dois municípios (#129). Decisão do mantenedor
(opção A, 2026-11-23): o aviso é armazenado à parte, com os códigos IBGE
que cobre e a janela de validade, e um alerta é ANOTADO com os avisos
vigentes no seu município no seu onset. Nenhum Alerta ou Incidente nasce de
um aviso. Ver wiki/decisions/inmet-warnings-as-context.md.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SeveridadeAviso(StrEnum):
    """Escala do INMET, com o nível CAP 1.2 equivalente no comentário.

    A correspondência Perigo Potencial = `Moderate` foi lida num CAP real
    (aviso 28747, 2026-11-23); as outras duas seguem a mesma escala de três
    níveis do INMET.
    """

    PERIGO_POTENCIAL = "PERIGO_POTENCIAL"  # CAP Moderate
    PERIGO = "PERIGO"  # CAP Severe
    GRANDE_PERIGO = "GRANDE_PERIGO"  # CAP Extreme

    @classmethod
    def from_inmet(cls, valor: str) -> SeveridadeAviso:
        mapa = {
            "perigo potencial": cls.PERIGO_POTENCIAL,
            "perigo": cls.PERIGO,
            "grande perigo": cls.GRANDE_PERIGO,
        }
        chave = valor.strip().lower() if isinstance(valor, str) else ""
        if chave not in mapa:
            raise ValueError(f"Severidade INMET desconhecida: {valor!r}")
        return mapa[chave]


class AvisoMeteorologico(BaseModel):
    """Uma mensagem de aviso do INMET (um `id_sequencia` de um `id_aviso`).

    `codigo_cap` é o identificador CAP (`urn:oid:2.49.0.0.76.0.<ano>.<id_aviso>.<seq>`)
    — único por mensagem; uma nova sequência do mesmo aviso é uma nova mensagem
    que substitui a anterior.
    """

    codigo_cap: str = Field(min_length=1)
    id_aviso: int
    id_sequencia: int = Field(ge=1)
    evento: str = Field(min_length=1)
    severidade: SeveridadeAviso
    inicio: datetime
    fim: datetime
    codigos_ibge: frozenset[int] = Field(min_length=1)
    encerrado: bool = False

    model_config = ConfigDict(frozen=True)

    @field_validator("inicio", "fim")
    @classmethod
    def _exigir_fuso(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None:
            raise ValueError("instante de aviso precisa de fuso (aware)")
        return valor

    @field_validator("codigos_ibge")
    @classmethod
    def _validar_codigos(cls, codigos: frozenset[int]) -> frozenset[int]:
        invalidos = sorted(c for c in codigos if not 1_000_000 <= c <= 9_999_999)
        if invalidos:
            raise ValueError(f"código IBGE fora do formato de 7 dígitos: {invalidos[:5]}")
        return codigos

    @model_validator(mode="after")
    def _validar_janela(self) -> AvisoMeteorologico:
        if self.fim < self.inicio:
            raise ValueError(f"aviso {self.codigo_cap} termina antes de começar")
        return self
