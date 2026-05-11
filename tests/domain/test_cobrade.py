from alertavida.domain.cobrade import mapear_cemaden, validar_formato


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
