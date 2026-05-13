import pytest

from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento


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


# ============================================================
# Camada 4 B.0.a — FonteDado
# ============================================================


class TestFonteDadoValores:
    """Conjunto fechado de valores válidos."""

    def test_valores_esperados(self):
        valores = {f.value for f in FonteDado}
        assert valores == {"CEMADEN", "EONET", "INMET", "INPE"}

    def test_cardinalidade(self):
        assert len(list(FonteDado)) == 4


class TestFonteDadoFromString:
    """Construção a partir de string com normalização."""

    @pytest.mark.parametrize("valor,esperado", [
        ("CEMADEN", FonteDado.CEMADEN),
        ("cemaden", FonteDado.CEMADEN),
        ("Cemaden", FonteDado.CEMADEN),
        ("  CEMADEN  ", FonteDado.CEMADEN),
        ("EONET", FonteDado.EONET),
        ("eonet", FonteDado.EONET),
        ("INMET", FonteDado.INMET),
        ("INPE", FonteDado.INPE),
    ])
    def test_normaliza_case_e_whitespace(self, valor, esperado):
        assert FonteDado.from_string(valor) == esperado

    @pytest.mark.parametrize("valor", [
        "CEMADAN",
        "NASA",
        "NOAA",
        "xyz",
    ])
    def test_levanta_em_valor_desconhecido(self, valor):
        with pytest.raises(ValueError, match="Fonte desconhecida"):
            FonteDado.from_string(valor)

    @pytest.mark.parametrize("valor", [None, "", "  ", "\n", "\t"])
    def test_levanta_em_valor_vazio(self, valor):
        with pytest.raises(ValueError, match="ausente ou vazia"):
            FonteDado.from_string(valor)

    def test_mensagem_lista_validas(self):
        """Erro deve listar as fontes válidas para diagnóstico."""
        with pytest.raises(ValueError) as exc_info:
            FonteDado.from_string("INVALIDA")
        msg = str(exc_info.value)
        assert "CEMADEN" in msg
        assert "EONET" in msg
        assert "INMET" in msg
        assert "INPE" in msg


class TestFonteDadoStrEnum:
    """Comportamento de StrEnum — serialização transparente."""

    def test_value_e_string(self):
        assert FonteDado.CEMADEN.value == "CEMADEN"
        assert isinstance(FonteDado.CEMADEN.value, str)

    def test_membro_e_string(self):
        """StrEnum: instância do enum é também instância de str."""
        assert isinstance(FonteDado.CEMADEN, str)

    def test_comparacao_com_string(self):
        """StrEnum permite comparação direta com string."""
        assert FonteDado.CEMADEN == "CEMADEN"
