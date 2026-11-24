"""Coleta de avisos meteorológicos — fora do pipeline de alertas (issue #153).

Separada de `executar_ingestao` de propósito: avisos não passam pelo
`ChangeDetector` (o ciclo de vida deles é a janela de validade, não a
ausência entre rodadas — a regra de ausência foi o que quebrou o EONET na
#124) nem pela correlação. Falha de coleta é registrada e não derruba nada.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from alertavida.database import registrar_avisos, registrar_rodada
from alertavida.domain.enums import FonteDado
from alertavida.sources.base import FalhaDeColeta
from alertavida.sources.inmet import InmetSource

logger = logging.getLogger(__name__)

_FONTE = FonteDado.INMET.value


@dataclass(frozen=True)
class RelatorioAvisos:
    coletados: int
    descartados: int
    novos: int
    falha_coleta: bool
    duracao_segundos: float


def executar_coleta_avisos(source: InmetSource) -> RelatorioAvisos:
    """Coleta e grava os avisos; registra a rodada (#158) com ou sem falha."""
    iniciada_em = datetime.now(UTC).isoformat()
    inicio = time.monotonic()
    try:
        avisos, descartados = source.coletar()
    except FalhaDeColeta as exc:
        logger.error("Falha ao coletar avisos INMET: %s", exc.causa)
        registrar_rodada(iniciada_em, datetime.now(UTC).isoformat(), [(_FONTE, None)])
        return RelatorioAvisos(0, 0, 0, True, time.monotonic() - inicio)
    resultado = registrar_avisos(avisos, datetime.now(UTC).isoformat())
    registrar_rodada(iniciada_em, datetime.now(UTC).isoformat(), [(_FONTE, len(avisos))])
    return RelatorioAvisos(
        coletados=len(avisos),
        descartados=descartados,
        novos=resultado.novos,
        falha_coleta=False,
        duracao_segundos=time.monotonic() - inicio,
    )


def formatar_relatorio_avisos(relatorio: RelatorioAvisos) -> str:
    if relatorio.falha_coleta:
        return f"  INMET (avisos): FALHA de coleta ({relatorio.duracao_segundos:.2f}s)"
    return (
        f"  INMET (avisos): {relatorio.coletados} vigentes ou futuros "
        f"({relatorio.novos} novos, {relatorio.descartados} descartados) "
        f"em {relatorio.duracao_segundos:.2f}s"
    )
