"""Testes do núcleo puro de decisão de correlação (Camada 5, issue #58)."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from alertavida.domain.correlacao import (
    LIMIAR_REVISAO,
    LIMIAR_VINCULA,
    CandidatoCorrelacao,
    ResultadoCompatibilidadeTipo,
    ResultadoDecisao,
    compatibilidade_tipo,
    decidir_correlacao,
    distancia_haversine_km,
)
from alertavida.domain.enums import FonteDado, TipoEvento

_ONSET = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
_RECIFE = (-8.05, -34.88)


def _candidato(
    cod: str = "1",
    fonte: FonteDado = FonteDado.CEMADEN,
    tipo_evento: TipoEvento = TipoEvento.HIDROLOGICO,
    cobrade_codigo: str | None = None,
    codigo_ibge: int | None = None,
    latitude: float = _RECIFE[0],
    longitude: float = _RECIFE[1],
    momento_onset: datetime = _ONSET,
) -> CandidatoCorrelacao:
    return CandidatoCorrelacao(
        fonte=fonte,
        cod_alerta=cod,
        tipo_evento=tipo_evento,
        cobrade_codigo=cobrade_codigo,
        codigo_ibge=codigo_ibge,
        latitude=latitude,
        longitude=longitude,
        momento_onset=momento_onset,
    )


# ============================================================
# compatibilidade_tipo — tabela diagonal-only
# ============================================================


def test_mesmo_subgrupo_cobrade_e_forte() -> None:
    """1.1.2.0.0 e 1.1.2.0.0 (vulcanismo) — mesmo subgrupo."""
    assert (
        compatibilidade_tipo("1.1.2.0.0", TipoEvento.GEOLOGICO, "1.1.2.0.0", TipoEvento.GEOLOGICO)
        is ResultadoCompatibilidadeTipo.FORTE
    )


def test_mesmo_grupo_subgrupo_diferente_e_fraca() -> None:
    """1.1.2.0.0 (vulcanismo) e 1.1.3.0.0 (movimento de massa) — mesmo grupo
    geológico (1.1), subgrupo diferente. Códigos reais de
    EVENTO_EONET_PARA_COBRADE (domain/cobrade.py)."""
    assert (
        compatibilidade_tipo("1.1.2.0.0", TipoEvento.GEOLOGICO, "1.1.3.0.0", TipoEvento.GEOLOGICO)
        is ResultadoCompatibilidadeTipo.FRACA
    )


def test_grupos_diferentes_e_incompativel() -> None:
    """1.4.1.0.0 (climatológico/queimada) e 1.1.3.0.0 (geológico) — grupos
    diferentes, fora da diagonal. Códigos reais de
    EVENTO_EONET_PARA_COBRADE."""
    assert (
        compatibilidade_tipo(
            "1.4.1.0.0", TipoEvento.CLIMATOLOGICO, "1.1.3.0.0", TipoEvento.GEOLOGICO
        )
        is ResultadoCompatibilidadeTipo.INCOMPATIVEL
    )


def test_fallback_tipoevento_igual_e_forte_sem_cobrade() -> None:
    assert (
        compatibilidade_tipo(None, TipoEvento.HIDROLOGICO, None, TipoEvento.HIDROLOGICO)
        is ResultadoCompatibilidadeTipo.FORTE
    )


def test_fallback_tipoevento_diferente_e_incompativel() -> None:
    assert (
        compatibilidade_tipo(None, TipoEvento.HIDROLOGICO, None, TipoEvento.METEOROLOGICO)
        is ResultadoCompatibilidadeTipo.INCOMPATIVEL
    )


def test_cobrade_so_de_um_lado_cai_no_fallback_tipoevento() -> None:
    """Um só lado com cobrade_codigo não basta para comparar por prefixo —
    cai para TipoEvento (Round 1, Q4: 'um ou ambos ausentes')."""
    assert (
        compatibilidade_tipo("1.2.0.0.0", TipoEvento.HIDROLOGICO, None, TipoEvento.HIDROLOGICO)
        is ResultadoCompatibilidadeTipo.FORTE
    )


@pytest.mark.parametrize(
    ("tipo_a", "tipo_b"),
    [
        (TipoEvento.INDETERMINADO, TipoEvento.HIDROLOGICO),
        (TipoEvento.HIDROLOGICO, TipoEvento.INDETERMINADO),
        (TipoEvento.INDETERMINADO, TipoEvento.INDETERMINADO),
    ],
)
def test_indeterminado_em_qualquer_lado_nunca_e_forte(
    tipo_a: TipoEvento, tipo_b: TipoEvento
) -> None:
    """Mesmo quando os dois lados são INDETERMINADO ('iguais'), o resultado
    é INDETERMINADA, nunca FORTE — ausência de classificação nos dois lados
    não é evidência de identidade."""
    assert (
        compatibilidade_tipo(None, tipo_a, None, tipo_b)
        is ResultadoCompatibilidadeTipo.INDETERMINADA
    )


# ============================================================
# decidir_correlacao — portões estruturais (não dependem de calibração)
# ============================================================


def test_indeterminado_nunca_vincula_mesmo_com_evidencia_maxima() -> None:
    """TipoEvento.INDETERMINADO nunca vincula sozinho, mesmo com o resto da
    evidência maximizada (mesmo codigo_ibge, distância zero, tempo zero)."""
    a = _candidato(tipo_evento=TipoEvento.HIDROLOGICO, codigo_ibge=2611606)
    b = _candidato(
        cod="2",
        fonte=FonteDado.EONET,
        tipo_evento=TipoEvento.INDETERMINADO,
        codigo_ibge=2611606,
    )
    decisao = decidir_correlacao(a, b)
    assert decisao.resultado is not ResultadoDecisao.VINCULA
    assert decisao.resultado is ResultadoDecisao.REVISAO
    assert decisao.motivo == "tipo_indeterminado_evidencia_forte"


def test_indeterminado_com_evidencia_fraca_nao_vincula() -> None:
    a = _candidato(tipo_evento=TipoEvento.HIDROLOGICO, codigo_ibge=1)
    b = _candidato(
        cod="2",
        fonte=FonteDado.EONET,
        tipo_evento=TipoEvento.INDETERMINADO,
        codigo_ibge=2,
        latitude=35.68,
        longitude=139.69,
        momento_onset=_ONSET + timedelta(days=3),
    )
    decisao = decidir_correlacao(a, b)
    assert decisao.resultado is ResultadoDecisao.NAO_VINCULA
    assert decisao.motivo == "tipo_indeterminado_evidencia_fraca"


def test_par_fora_da_diagonal_nunca_vincula_mesmo_com_evidencia_maxima() -> None:
    """Grupos COBRADE diferentes (fora da diagonal) — NAO_VINCULA mesmo com
    o resto da evidência maximizada. Cascata causal não é identidade."""
    a = _candidato(tipo_evento=TipoEvento.HIDROLOGICO, cobrade_codigo="1.2.0.0.0", codigo_ibge=1)
    b = _candidato(
        cod="2",
        tipo_evento=TipoEvento.METEOROLOGICO,
        cobrade_codigo="1.3.0.0.0",
        codigo_ibge=1,
    )
    decisao = decidir_correlacao(a, b)
    assert decisao.resultado is ResultadoDecisao.NAO_VINCULA
    assert decisao.motivo == "tipos_incompativeis"


# ============================================================
# decidir_correlacao — as três saídas, todas alcançáveis
# ============================================================


def test_vincula_alcancavel_com_evidencia_forte_em_tudo() -> None:
    a = _candidato(tipo_evento=TipoEvento.HIDROLOGICO, cobrade_codigo="1.2.0.0.0", codigo_ibge=1)
    b = _candidato(
        cod="2",
        tipo_evento=TipoEvento.HIDROLOGICO,
        cobrade_codigo="1.2.0.0.0",
        codigo_ibge=1,
    )
    decisao = decidir_correlacao(a, b)
    assert decisao.resultado is ResultadoDecisao.VINCULA
    assert decisao.score >= LIMIAR_VINCULA


def test_nao_vincula_alcancavel_com_evidencia_fraca() -> None:
    a = _candidato(tipo_evento=TipoEvento.HIDROLOGICO, cobrade_codigo="1.2.0.0.0", codigo_ibge=1)
    b = _candidato(
        cod="2",
        tipo_evento=TipoEvento.HIDROLOGICO,
        cobrade_codigo="1.2.0.0.0",
        codigo_ibge=2,
        latitude=35.68,
        longitude=139.69,
        momento_onset=_ONSET + timedelta(days=3),
    )
    decisao = decidir_correlacao(a, b)
    assert decisao.resultado is ResultadoDecisao.NAO_VINCULA
    assert decisao.score < LIMIAR_REVISAO


def test_revisao_alcancavel_com_evidencia_ambigua() -> None:
    """codigo_ibge ausente dos dois lados (peso redistribuído), ~22 km de
    distância (banda 0-50km), 3h de defasagem (janela de 6h) — evidência
    real mas não conclusiva."""
    a = _candidato(tipo_evento=TipoEvento.HIDROLOGICO, latitude=-8.0, longitude=-34.88)
    b = _candidato(
        cod="2",
        tipo_evento=TipoEvento.HIDROLOGICO,
        latitude=-8.2,
        longitude=-34.88,
        momento_onset=_ONSET + timedelta(hours=3),
    )
    decisao = decidir_correlacao(a, b)
    assert decisao.resultado is ResultadoDecisao.REVISAO
    assert LIMIAR_REVISAO <= decisao.score < LIMIAR_VINCULA
    assert decisao.motivo == "evidencia_ambigua"


# ============================================================
# distancia_haversine_km — sanidade geométrica
# ============================================================


def test_distancia_entre_ponto_e_ele_mesmo_e_zero() -> None:
    assert distancia_haversine_km(*_RECIFE, *_RECIFE) == pytest.approx(0.0, abs=1e-9)


def test_distancia_quarto_de_meridiano_equador_ao_polo() -> None:
    """Do equador (0,0) ao polo norte (90,0): exatamente um quarto de
    grande círculo, (pi/2) * raio — par de coordenadas conhecido,
    verificável por geometria, não por referência externa."""
    raio_km = 6371.0088
    esperado = (math.pi / 2) * raio_km
    assert distancia_haversine_km(0.0, 0.0, 90.0, 0.0) == pytest.approx(esperado, rel=1e-9)


def test_distancia_e_simetrica() -> None:
    sp = (-23.5505, -46.6333)
    assert distancia_haversine_km(*_RECIFE, *sp) == pytest.approx(
        distancia_haversine_km(*sp, *_RECIFE), rel=1e-12
    )
