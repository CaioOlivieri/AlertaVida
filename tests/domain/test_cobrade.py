from alertavida.domain.cobrade import (
    EVENTO_CEMADEN_PARA_COBRADE,
    EVENTO_EONET_PARA_COBRADE,
    fonte_classificacao_do_mapeamento,
    mapear_cemaden,
    mapear_eonet,
    validar_formato,
)
from alertavida.domain.enums import FonteClassificacao

# ============================================================
# mapear_cemaden
# ============================================================


def test_mapear_cemaden_risco_hidrologico() -> None:
    assert mapear_cemaden("Risco Hidrológico") == "1.2.0.0.0"


def test_mapear_cemaden_movimentos_de_massa() -> None:
    assert mapear_cemaden("Movimentos de Massa") == "1.1.3.0.0"


def test_mapear_cemaden_desconhecido_retorna_none() -> None:
    assert mapear_cemaden("Qualquer Outra Coisa") is None


def test_mapear_cemaden_string_vazia_retorna_none() -> None:
    assert mapear_cemaden("") is None


# ============================================================
# mapear_eonet
# ============================================================


def test_mapear_eonet_wildfires() -> None:
    assert mapear_eonet("wildfires") == "1.4.1.0.0"


def test_mapear_eonet_floods() -> None:
    assert mapear_eonet("floods") == "1.2.0.0.0"


def test_mapear_eonet_severe_storms() -> None:
    assert mapear_eonet("severeStorms") == "1.3.0.0.0"


def test_mapear_eonet_volcanoes() -> None:
    assert mapear_eonet("volcanoes") == "1.1.2.0.0"


def test_mapear_eonet_landslides() -> None:
    assert mapear_eonet("landslides") == "1.1.3.0.0"


def test_mapear_eonet_desconhecido_retorna_none() -> None:
    assert mapear_eonet("waterColor") is None


def test_mapear_eonet_string_vazia_retorna_none() -> None:
    assert mapear_eonet("") is None


def test_mapear_eonet_todos_valores_validos() -> None:
    for codigo in EVENTO_EONET_PARA_COBRADE.values():
        assert validar_formato(codigo), f"{codigo} não é um código COBRADE válido"


# ============================================================
# validar_formato
# ============================================================


def test_validar_formato_cinco_niveis_valido() -> None:
    assert validar_formato("1.2.0.0.0") is True


def test_validar_formato_cinco_niveis_subgrupo_geologico() -> None:
    assert validar_formato("1.1.3.0.0") is True


def test_validar_formato_quatro_niveis_invalido() -> None:
    assert validar_formato("1.2.0.0") is False


def test_validar_formato_seis_niveis_invalido() -> None:
    assert validar_formato("1.2.0.0.0.0") is False


def test_validar_formato_nao_numerico_invalido() -> None:
    assert validar_formato("1.a.0.0.0") is False


def test_validar_formato_string_vazia_invalido() -> None:
    assert validar_formato("") is False


# ============================================================
# fonte_classificacao_do_mapeamento (#91)
# ============================================================


def test_fonte_classificacao_sem_codigo_e_indeterminada() -> None:
    assert fonte_classificacao_do_mapeamento(None) is FonteClassificacao.INDETERMINADA


def test_fonte_classificacao_de_todo_codigo_mapeado_e_por_nome() -> None:
    codigos = {*EVENTO_CEMADEN_PARA_COBRADE.values(), *EVENTO_EONET_PARA_COBRADE.values()}
    for codigo in codigos:
        assert fonte_classificacao_do_mapeamento(codigo) is FonteClassificacao.MAPEADA_POR_NOME


def test_fonte_classificacao_de_categoria_desconhecida_e_indeterminada() -> None:
    assert (
        fonte_classificacao_do_mapeamento(mapear_cemaden("Categoria Nova"))
        is FonteClassificacao.INDETERMINADA
    )
    assert (
        fonte_classificacao_do_mapeamento(mapear_eonet("dustHaze"))
        is FonteClassificacao.INDETERMINADA
    )
