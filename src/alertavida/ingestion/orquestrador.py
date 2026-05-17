"""Orquestrador de ingestão multi-fonte — Camada 4 Parte B.2.

Coordena a pipeline completa por fonte: coleta → detecção de mudanças →
persistência. Cada fonte é tratada em transação independente; falha de
uma não aborta as demais. Apenas FalhaDeColeta é capturada — exceções
inesperadas propagam (bug deve quebrar ruidosamente).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from alertavida.database import aplicar_resultado_deteccao, buscar_snapshots_ativos
from alertavida.domain.detector import TipoEventoDetectado, detectar_mudancas
from alertavida.domain.enums import FonteDado
from alertavida.sources.base import DataSource, FalhaDeColeta


@dataclass(frozen=True, slots=True)
class RelatorioFonte:
    """Resultado da ingestão de uma única fonte numa rodada."""

    fonte: FonteDado
    coletados: int
    novos: int
    atualizados: int
    inalterados: int
    descartados: int
    falha_coleta: bool
    coletado_em: datetime | None
    duracao_segundos: float

    def __post_init__(self) -> None:
        if not self.falha_coleta:
            soma = self.novos + self.atualizados + self.inalterados + self.descartados
            if soma != self.coletados:
                raise ValueError(
                    f"Invariante violada para fonte {self.fonte.value}: "
                    f"coletados={self.coletados} mas "
                    f"novos+atualizados+inalterados+descartados={soma}"
                )
            if self.coletado_em is None:
                raise ValueError(
                    f"coletado_em obrigatório quando falha_coleta=False "
                    f"(fonte={self.fonte.value})"
                )
        else:
            zerados = (
                self.coletados,
                self.novos,
                self.atualizados,
                self.inalterados,
                self.descartados,
            )
            if any(z != 0 for z in zerados):
                raise ValueError(
                    f"falha_coleta=True exige todos os contadores zerados "
                    f"(fonte={self.fonte.value}); recebido {zerados}"
                )
            if self.coletado_em is not None:
                raise ValueError(
                    f"falha_coleta=True exige coletado_em=None "
                    f"(fonte={self.fonte.value})"
                )
        if self.duracao_segundos < 0:
            raise ValueError(
                f"duracao_segundos não pode ser negativa "
                f"(fonte={self.fonte.value}, recebido={self.duracao_segundos})"
            )


@dataclass(frozen=True, slots=True)
class RelatorioIngestao:
    """Resultado agregado de uma rodada de ingestão multi-fonte."""

    por_fonte: tuple[RelatorioFonte, ...]
    agora: datetime

    def __post_init__(self) -> None:
        if self.agora.tzinfo is None:
            raise ValueError("agora deve ser timezone-aware")

    @property
    def total(self) -> int:
        """Soma de alertas coletados em todas as fontes da rodada."""
        return sum(r.coletados for r in self.por_fonte)


def executar_ingestao(
    sources: Sequence[DataSource],
    *,
    agora: datetime | None = None,
) -> RelatorioIngestao:
    """Executa uma rodada de ingestão sobre as fontes dadas.

    Cada fonte é processada em transação independente: falha de uma não
    afeta as outras. Apenas FalhaDeColeta é capturada — qualquer outra
    exceção propaga (bug deve quebrar ruidosamente).

    O timestamp `agora` é gerado uma vez no início da rodada e propagado
    para todas as fontes, garantindo coerência temporal no campo
    `visto_ultima_vez` dos snapshots.
    """
    agora_da_rodada = agora if agora is not None else datetime.now(UTC)
    relatorios: list[RelatorioFonte] = []

    for source in sources:
        inicio = time.monotonic()
        fonte = source.fonte

        try:
            resultado_coleta = source.coletar()
        except FalhaDeColeta:
            relatorios.append(
                RelatorioFonte(
                    fonte=fonte,
                    coletados=0,
                    novos=0,
                    atualizados=0,
                    inalterados=0,
                    descartados=0,
                    falha_coleta=True,
                    coletado_em=None,
                    duracao_segundos=time.monotonic() - inicio,
                )
            )
            continue

        snapshots = buscar_snapshots_ativos(fonte)
        resultado_det = detectar_mudancas(resultado_coleta.alertas, snapshots)
        alertas_por_codigo = {a.cod_alerta: a for a in resultado_coleta.alertas}
        aplicar_resultado_deteccao(
            resultado_det,
            alertas_por_codigo,
            agora_da_rodada.isoformat(),
        )

        criados_count = sum(1 for e in resultado_det.eventos if e.tipo is TipoEventoDetectado.CRIADO)
        atualizados_count = sum(
            1 for e in resultado_det.eventos if e.tipo is TipoEventoDetectado.ATUALIZADO
        )
        inalterados_count = (
            len(resultado_det.codigos_vistos) - criados_count - atualizados_count
        )

        relatorios.append(
            RelatorioFonte(
                fonte=fonte,
                coletados=len(resultado_coleta.alertas) + resultado_coleta.descartados,
                novos=criados_count,
                atualizados=atualizados_count,
                inalterados=inalterados_count,
                descartados=resultado_coleta.descartados,
                falha_coleta=False,
                coletado_em=resultado_coleta.coletado_em,
                duracao_segundos=time.monotonic() - inicio,
            )
        )

    return RelatorioIngestao(
        por_fonte=tuple(relatorios),
        agora=agora_da_rodada,
    )
