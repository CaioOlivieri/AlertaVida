"""Núcleo puro de decisão de correlação — Camada 5 (issue #58).

Decide se dois candidatos (tipicamente dois `Alerta`s, ou um `Alerta` e um
`Incidente` já aberto — quem chama decide o que cada lado de
`CandidatoCorrelacao` representa) descrevem o MESMO evento físico. Segue a
arquitetura de record linkage (Fellegi & Sunter) adotada pela camada:
blocking → scoring → decisão de três saídas. Este módulo é só o
"scoring → decisão"; blocking (índice espacial, janela de tempo) fica em
#60. Ver wiki/projects/layer-5-correlation.md — as duas rodadas de
clarificação são a spec.

Núcleo 100% puro: nenhum I/O, nenhum SQL, nenhum import de `database`/
`sources`. Todos os pesos e limiares abaixo são constantes de módulo,
PROVISÓRIAS e conservadoras (viés para separar — Round 2, "false merge vs.
false split"). Calibração é escopo da issue #63 (dormente); não ajustar
aqui.

Cascata causal (ex.: tempestade → enchente → deslizamento) é uma relação
DISTINTA de identidade e está fora do escopo deste módulo e da v1 inteira
(Round 1, Q4; "v1 scope decisions" #4 na página do projeto). Este módulo só
responde "é o mesmo evento?", nunca "um evento desencadeou o outro?".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from alertavida.domain.enums import FonteDado, TipoEvento

# ---------------------------------------------------------------------------
# Pesos e limiares — TODOS provisórios e conservadores. Placeholders herdados
# do spec pré-clarificação (±6h / 50 km na página do projeto), rotulados como
# tal por disciplina de wiki/_schema.md regra 1 (não afirmar como valor
# derivado). Ver wiki/projects/layer-5-correlation.md, "v1 scope decisions"
# #2. Calibração é escopo da issue #63 — NÃO ajustar estas constantes aqui.
# ---------------------------------------------------------------------------

PESO_CODIGO_IBGE: Final[float] = 0.35
PESO_DISTANCIA: Final[float] = 0.25
PESO_TEMPO: Final[float] = 0.20
PESO_TIPO: Final[float] = 0.20

# Banda de distância (km) — fallback quando codigo_ibge está ausente ou não
# bate (preferência: chave administrativa antes de geometria, Round 1 Q2).
DISTANCIA_MAXIMA_KM: Final[float] = 50.0

# Janela de tempo (segundos), simétrica por enquanto — o formato final é
# assimétrico por par de fontes e medido contra o onset estimado (Round 1,
# Q1), mas os valores por tipo só existem depois que #63 calibrar contra
# pares confirmados reais.
JANELA_TEMPO_SEGUNDOS: Final[float] = 6 * 3600.0

# Limiar de VINCULA começa ALTO e o de REVISAO começa BAIXO (banda de revisão
# larga) de propósito — viés para separar (Round 2, decisão do mantenedor).
# Em dúvida: REVISAO ou NAO_VINCULA, nunca VINCULA.
LIMIAR_VINCULA: Final[float] = 0.85
LIMIAR_REVISAO: Final[float] = 0.45

_RAIO_TERRA_KM: Final[float] = 6371.0088  # raio médio da Terra (IUGG)


class ResultadoCompatibilidadeTipo(StrEnum):
    """Nível de compatibilidade de identidade entre dois tipos de evento."""

    FORTE = "FORTE"
    FRACA = "FRACA"
    INDETERMINADA = "INDETERMINADA"
    INCOMPATIVEL = "INCOMPATIVEL"


class ResultadoDecisao(StrEnum):
    """As três saídas da decisão de correlação (Round 1, framing geral)."""

    VINCULA = "VINCULA"
    NAO_VINCULA = "NAO_VINCULA"
    REVISAO = "REVISAO"


@dataclass(frozen=True)
class CandidatoCorrelacao:
    """View reduzida de um `Alerta` com só os campos que a decisão pura usa.

    `nivel_risco` deliberadamente NÃO está aqui (Round 1, Q3): correlação
    estabelece identidade, não concordância de severidade. Quem monta este
    objeto (infra, #59/#61) decide de que fonte de dados cada lado vem.
    """

    fonte: FonteDado
    cod_alerta: str
    tipo_evento: TipoEvento
    cobrade_codigo: str | None
    codigo_ibge: int | None
    latitude: float
    longitude: float
    momento_onset: datetime


@dataclass(frozen=True)
class DecisaoCorrelacao:
    """Resultado de `decidir_correlacao` — o suficiente para #59/#60
    registrarem uma linha de `correlacao_observacoes` sem recalcular nada.
    """

    resultado: ResultadoDecisao
    score: float
    motivo: str
    distancia_km: float
    delta_t_segundos: float


def distancia_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância geodésica (grande círculo) entre dois pontos, em km.

    Comparações na trilha de decisão NUNCA usam graus decimais puros (Round
    1, Q2 — 1° de longitude difere de 1° de latitude em km nas latitudes
    brasileiras, a mesma distorção documentada no buffer de
    `domain/geographic.py`). Bbox em graus é aceitável só no estágio de
    blocking (#60), que nunca decide sozinho.
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    return 2 * _RAIO_TERRA_KM * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Tabela de compatibilidade de identidade — DIAGONAL-ONLY por construção.
# `compatibilidade_tipo` só retorna FORTE/FRACA quando os dois lados caem no
# MESMO grupo COBRADE (prefixo) ou no mesmo TipoEvento; nunca entre grupos
# diferentes. Um par fora da diagonal (ex.: HIDROLOGICO correlacionando com
# METEOROLOGICO — "tempestade causa enchente") é CASCATA CAUSAL, não
# identidade (Round 1, Q4), e está fora de escopo. Adicionar uma exceção fora
# da diagonal exige evidência empírica documentada — mesma disciplina de
# `EVENTO_CEMADEN_PARA_COBRADE` em `domain/cobrade.py`. Não inventar por
# suposição.
# ---------------------------------------------------------------------------


def _mesmo_subgrupo_cobrade(a: str, b: str) -> bool:
    return a.split(".")[:3] == b.split(".")[:3]


def _mesmo_grupo_cobrade(a: str, b: str) -> bool:
    return a.split(".")[:2] == b.split(".")[:2]


def compatibilidade_tipo(
    cobrade_a: str | None,
    tipo_a: TipoEvento,
    cobrade_b: str | None,
    tipo_b: TipoEvento,
) -> ResultadoCompatibilidadeTipo:
    """Compara identidade no nível mais específico disponível dos dois lados.

    - Ambos com `cobrade_codigo`: compara por prefixo — mesmo subgrupo
      (5 níveis, 3 primeiros iguais) = FORTE; mesmo grupo mas subgrupo
      diferente (2 primeiros iguais) = FRACA; grupos diferentes =
      INCOMPATIVEL.
    - Um ou ambos sem `cobrade_codigo`: cai para `TipoEvento` (fallback).
      `TipoEvento.INDETERMINADO` em qualquer lado → INDETERMINADA (nunca
      vincula sozinho — no máximo REVISAO, decidido em `decidir_correlacao`).
      Mesmo `TipoEvento` (nenhum INDETERMINADO) → FORTE. Tipos diferentes →
      INCOMPATIVEL.
    """
    if cobrade_a is not None and cobrade_b is not None:
        if _mesmo_subgrupo_cobrade(cobrade_a, cobrade_b):
            return ResultadoCompatibilidadeTipo.FORTE
        if _mesmo_grupo_cobrade(cobrade_a, cobrade_b):
            return ResultadoCompatibilidadeTipo.FRACA
        return ResultadoCompatibilidadeTipo.INCOMPATIVEL

    if tipo_a is TipoEvento.INDETERMINADO or tipo_b is TipoEvento.INDETERMINADO:
        return ResultadoCompatibilidadeTipo.INDETERMINADA

    if tipo_a is tipo_b:
        return ResultadoCompatibilidadeTipo.FORTE

    return ResultadoCompatibilidadeTipo.INCOMPATIVEL


_PONTUACAO_POR_COMPATIBILIDADE: Final[dict[ResultadoCompatibilidadeTipo, float]] = {
    ResultadoCompatibilidadeTipo.FORTE: 1.0,
    ResultadoCompatibilidadeTipo.FRACA: 0.5,
    ResultadoCompatibilidadeTipo.INDETERMINADA: 0.0,
    ResultadoCompatibilidadeTipo.INCOMPATIVEL: 0.0,
}


def _pontuacao_codigo_ibge(a: int | None, b: int | None) -> float | None:
    """`None` = sem evidência (ao menos um lado sem código); não entra no peso."""
    if a is None or b is None:
        return None
    return 1.0 if a == b else 0.0


def _pontuar(
    a: CandidatoCorrelacao, b: CandidatoCorrelacao
) -> tuple[float, ResultadoCompatibilidadeTipo, float, float]:
    """Média ponderada sobre a evidência DISPONÍVEL — pesos de evidência
    ausente (tipicamente `codigo_ibge` em pares CEMADEN×EONET) são
    redistribuídos entre o resto, nunca tratados como pontuação zero.
    """
    componentes: list[tuple[float, float]] = []

    pontuacao_ibge = _pontuacao_codigo_ibge(a.codigo_ibge, b.codigo_ibge)
    if pontuacao_ibge is not None:
        componentes.append((PESO_CODIGO_IBGE, pontuacao_ibge))

    distancia_km = distancia_haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
    pontuacao_distancia = max(0.0, 1.0 - distancia_km / DISTANCIA_MAXIMA_KM)
    componentes.append((PESO_DISTANCIA, pontuacao_distancia))

    delta_t_segundos = (b.momento_onset - a.momento_onset).total_seconds()
    pontuacao_tempo = max(0.0, 1.0 - abs(delta_t_segundos) / JANELA_TEMPO_SEGUNDOS)
    componentes.append((PESO_TEMPO, pontuacao_tempo))

    compatibilidade = compatibilidade_tipo(
        a.cobrade_codigo, a.tipo_evento, b.cobrade_codigo, b.tipo_evento
    )
    componentes.append((PESO_TIPO, _PONTUACAO_POR_COMPATIBILIDADE[compatibilidade]))

    peso_total = sum(peso for peso, _ in componentes)
    score = sum(peso * pontuacao for peso, pontuacao in componentes) / peso_total
    return score, compatibilidade, distancia_km, delta_t_segundos


def decidir_correlacao(a: CandidatoCorrelacao, b: CandidatoCorrelacao) -> DecisaoCorrelacao:
    """Decide VINCULA / NAO_VINCULA / REVISAO para um par de candidatos.

    Dois portões estruturais valem ANTES de qualquer limiar de score — não
    dependem de calibração e não podem ser contornados por reajuste de pesos
    (#63): tipos INCOMPATIVEL nunca vinculam, e `TipoEvento.INDETERMINADO`
    nunca vincula sozinho (no máximo REVISAO, quando o resto da evidência é
    forte).
    """
    score, compatibilidade, distancia_km, delta_t_segundos = _pontuar(a, b)

    if compatibilidade is ResultadoCompatibilidadeTipo.INCOMPATIVEL:
        return DecisaoCorrelacao(
            resultado=ResultadoDecisao.NAO_VINCULA,
            score=score,
            motivo="tipos_incompativeis",
            distancia_km=distancia_km,
            delta_t_segundos=delta_t_segundos,
        )

    if compatibilidade is ResultadoCompatibilidadeTipo.INDETERMINADA:
        if score >= LIMIAR_REVISAO:
            resultado = ResultadoDecisao.REVISAO
            motivo = "tipo_indeterminado_evidencia_forte"
        else:
            resultado = ResultadoDecisao.NAO_VINCULA
            motivo = "tipo_indeterminado_evidencia_fraca"
        return DecisaoCorrelacao(
            resultado=resultado,
            score=score,
            motivo=motivo,
            distancia_km=distancia_km,
            delta_t_segundos=delta_t_segundos,
        )

    if score >= LIMIAR_VINCULA:
        resultado = ResultadoDecisao.VINCULA
        motivo = "evidencia_forte"
    elif score >= LIMIAR_REVISAO:
        resultado = ResultadoDecisao.REVISAO
        motivo = "evidencia_ambigua"
    else:
        resultado = ResultadoDecisao.NAO_VINCULA
        motivo = "evidencia_fraca"

    return DecisaoCorrelacao(
        resultado=resultado,
        score=score,
        motivo=motivo,
        distancia_km=distancia_km,
        delta_t_segundos=delta_t_segundos,
    )
