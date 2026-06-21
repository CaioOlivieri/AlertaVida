import pytest
from pydantic import ValidationError

from alertavida.domain.municipio import Municipio


def test_criacao_valida_nome_uf() -> None:
    m = Municipio(nome="Recife", uf="PE")
    assert m.nome == "Recife"
    assert m.uf == "PE"


def test_uf_normalizado_uppercase() -> None:
    m = Municipio(nome="Recife", uf="pe")
    assert m.uf == "PE"


def test_uf_com_whitespace_normaliza() -> None:
    m = Municipio(nome="Recife", uf=" pe ")
    assert m.uf == "PE"


def test_nome_vazio_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="", uf="PE")


def test_nome_apenas_whitespace_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="   ", uf="PE")


def test_uf_tamanho_errado_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="Recife", uf="PEX")


def test_codigo_ibge_opcional_none_por_padrao() -> None:
    m = Municipio(nome="Recife", uf="PE")
    assert m.codigo_ibge is None


def test_codigo_ibge_aceita_inteiro() -> None:
    m = Municipio(nome="Recife", uf="PE", codigo_ibge=2611606)
    assert m.codigo_ibge == 2611606


def test_immutabilidade() -> None:
    m = Municipio(nome="Recife", uf="PE")
    with pytest.raises(ValidationError):
        m.nome = "Outro"


def test_uf_none_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome="Recife", uf=None)  # type: ignore[arg-type]


def test_nome_nao_string_lanca() -> None:
    with pytest.raises(ValidationError):
        Municipio(nome=123, uf="PE")  # type: ignore[arg-type]
