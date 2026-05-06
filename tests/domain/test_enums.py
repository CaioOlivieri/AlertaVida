import pytest

from alertavida.domain.enums import NivelRisco, TipoEvento


def test_nivel_risco_moderado_uppercase() -> None:
    assert NivelRisco.from_string("MODERADO") == NivelRisco.MODERADO


def test_nivel_risco_moderado_whitespace_case() -> None:
    assert NivelRisco.from_string(" moderado ") == NivelRisco.MODERADO


def test_nivel_risco_desconhecido() -> None:
    with pytest.raises(ValueError, match="Nível de risco desconhecido: XYZ"):
        NivelRisco.from_string("XYZ")


def test_nivel_risco_none_invalido() -> None:
    with pytest.raises(ValueError, match="Nível de risco ausente ou inválido"):
        NivelRisco.from_string(None)


def test_nivel_risco_vazio_invalido() -> None:
    with pytest.raises(ValueError, match="Nível de risco ausente ou inválido"):
        NivelRisco.from_string("")


def test_tipo_evento_hidrologico_com_acento() -> None:
    assert TipoEvento.from_string("Risco Hidrológico") == TipoEvento.HIDROLOGICO


def test_tipo_evento_geologico_movimentos_massa() -> None:
    assert TipoEvento.from_string("Movimentos de Massa") == TipoEvento.GEOLOGICO


def test_tipo_evento_climatologico_queimada() -> None:
    assert TipoEvento.from_string("Queimada") == TipoEvento.CLIMATOLOGICO


def test_tipo_evento_meteorologico_chuva() -> None:
    assert TipoEvento.from_string("Chuva") == TipoEvento.METEOROLOGICO


def test_tipo_evento_meteorologico_vento_forte() -> None:
    assert TipoEvento.from_string("Vento Forte") == TipoEvento.METEOROLOGICO


def test_tipo_evento_desconhecido_vira_indeterminado() -> None:
    assert TipoEvento.from_string("XYZ desconhecido") == TipoEvento.INDETERMINADO


def test_tipo_evento_none_vira_indeterminado() -> None:
    assert TipoEvento.from_string(None) == TipoEvento.INDETERMINADO


def test_nivel_risco_muito_alto_com_underscore() -> None:
    assert NivelRisco.from_string("MUITO_ALTO") == NivelRisco.MUITO_ALTO


def test_nivel_risco_muito_alto_sem_underscore() -> None:
    assert NivelRisco.from_string("muitoalto") == NivelRisco.MUITO_ALTO


def test_enum_str_mixin_serialize_value() -> None:
    assert NivelRisco.MODERADO.value == "MODERADO"


def test_tipo_evento_climatologico_incendio() -> None:
    assert TipoEvento.from_string("incendio") == TipoEvento.CLIMATOLOGICO


def test_tipo_evento_climatologico_fogo() -> None:
    assert TipoEvento.from_string("fogo") == TipoEvento.CLIMATOLOGICO


def test_nivel_risco_indeterminado() -> None:
    assert NivelRisco.from_string("INDETERMINADO") == NivelRisco.INDETERMINADO
