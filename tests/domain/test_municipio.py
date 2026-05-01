import pytest
from pydantic import ValidationError

from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.municipio import Municipio


def test_criacao_valida_nome_uf() -> None:
    m = Municipio(nome="Sao Paulo", uf="SP")
    assert m.nome == "Sao Paulo"
    assert m.uf == "SP"


def test_uf_normalizado_uppercase() -> None:
    m = Municipio(nome="X", uf="sp")
    assert m.uf == "SP"


def test_uf_com_whitespace_normaliza() -> None:
    m = Municipio(nome="Sao Paulo", uf=" sp ")
    assert m.uf == "SP"


def test_uf_tamanho_errado_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="X", uf="S")


def test_nome_vazio_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="", uf="SP")


def test_nome_apenas_whitespace_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="   ", uf="SP")


def test_codigo_ibge_opcional_none_por_padrao() -> None:
    m = Municipio(nome="X", uf="SP")
    assert m.codigo_ibge is None


def test_coordenadas_opcional_none_por_padrao() -> None:
    m = Municipio(nome="X", uf="SP")
    assert m.coordenadas is None


def test_municipio_aceita_coordenadas_validas() -> None:
    coords = Coordenadas(latitude=-23.55, longitude=-46.63)
    m = Municipio(nome="São Paulo", uf="SP", coordenadas=coords)
    assert m.coordenadas is not None
    assert m.coordenadas.latitude == -23.55
    assert m.coordenadas.longitude == -46.63


def test_immutabilidade() -> None:
    m = Municipio(nome="X", uf="SP")
    with pytest.raises(ValidationError):
        m.uf = "RJ"
