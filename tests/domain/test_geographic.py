"""Testes do módulo geographic — classificação de escopo geográfico."""

import pytest

from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import EscopoGeografico
from alertavida.domain.geographic import (
    BUFFER_PROXIMO_DEFAULT_GRAUS,
    ENV_BUFFER_PROXIMO,
    FAIXA_BRASIL,
    FaixaGeografica,
    _faixa_proximo,
    _ler_buffer_proximo,
    classificar_escopo,
)

# ============================================================
# Casos do BRASIL — coordenadas dentro do território
# ============================================================


def test_classificar_escopo_recife_brasil() -> None:
    coord = Coordenadas(latitude=-8.05, longitude=-34.88)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


def test_classificar_escopo_sao_paulo_brasil() -> None:
    coord = Coordenadas(latitude=-23.55, longitude=-46.63)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


def test_classificar_escopo_manaus_brasil() -> None:
    coord = Coordenadas(latitude=-3.10, longitude=-60.02)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


def test_classificar_escopo_brasilia_brasil() -> None:
    coord = Coordenadas(latitude=-15.78, longitude=-47.93)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


# ============================================================
# Casos PROXIMO — fora do Brasil mas dentro do buffer default (5°)
# ============================================================


def test_classificar_escopo_buenos_aires_proximo() -> None:
    coord = Coordenadas(latitude=-34.61, longitude=-58.37)
    assert classificar_escopo(coord) == EscopoGeografico.PROXIMO


def test_classificar_escopo_montevideu_proximo() -> None:
    coord = Coordenadas(latitude=-34.90, longitude=-56.16)
    assert classificar_escopo(coord) == EscopoGeografico.PROXIMO


# ============================================================
# Casos INTERNACIONAL — fora do buffer default
# ============================================================


def test_classificar_escopo_lisboa_internacional() -> None:
    coord = Coordenadas(latitude=38.72, longitude=-9.14)
    assert classificar_escopo(coord) == EscopoGeografico.INTERNACIONAL


def test_classificar_escopo_toquio_internacional() -> None:
    coord = Coordenadas(latitude=35.68, longitude=139.69)
    assert classificar_escopo(coord) == EscopoGeografico.INTERNACIONAL


def test_classificar_escopo_los_angeles_internacional() -> None:
    coord = Coordenadas(latitude=34.05, longitude=-118.24)
    assert classificar_escopo(coord) == EscopoGeografico.INTERNACIONAL


# ============================================================
# Caso INDETERMINADO — sem coordenadas
# ============================================================


def test_classificar_escopo_sem_coordenadas_indeterminado() -> None:
    assert classificar_escopo(None) == EscopoGeografico.INDETERMINADO


# ============================================================
# Bordas do bbox BRASIL — testes de inclusividade
# ============================================================


def test_classificar_escopo_borda_norte_brasil() -> None:
    coord = Coordenadas(latitude=FAIXA_BRASIL.lat_max, longitude=-50.0)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


def test_classificar_escopo_borda_sul_brasil() -> None:
    coord = Coordenadas(latitude=FAIXA_BRASIL.lat_min, longitude=-50.0)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


def test_classificar_escopo_borda_leste_brasil() -> None:
    coord = Coordenadas(latitude=-15.0, longitude=FAIXA_BRASIL.lon_max)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


def test_classificar_escopo_borda_oeste_brasil() -> None:
    coord = Coordenadas(latitude=-15.0, longitude=FAIXA_BRASIL.lon_min)
    assert classificar_escopo(coord) == EscopoGeografico.BRASIL


# ============================================================
# Configuração via env var — buffer PROXIMO override
# ============================================================


def test_buffer_proximo_default_quando_env_ausente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_BUFFER_PROXIMO, raising=False)
    assert _ler_buffer_proximo() == BUFFER_PROXIMO_DEFAULT_GRAUS


def test_buffer_proximo_default_quando_env_vazio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "")
    assert _ler_buffer_proximo() == BUFFER_PROXIMO_DEFAULT_GRAUS


def test_buffer_proximo_override_valor_valido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "10.0")
    assert _ler_buffer_proximo() == 10.0


def test_buffer_proximo_default_quando_env_nao_numerico(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "abc")
    assert _ler_buffer_proximo() == BUFFER_PROXIMO_DEFAULT_GRAUS


def test_buffer_proximo_default_quando_env_negativo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "-3")
    assert _ler_buffer_proximo() == BUFFER_PROXIMO_DEFAULT_GRAUS


def test_buffer_proximo_default_quando_env_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "0")
    assert _ler_buffer_proximo() == BUFFER_PROXIMO_DEFAULT_GRAUS


# ============================================================
# Reflexo do override no comportamento de classificar_escopo
# ============================================================


def test_classificar_escopo_buffer_pequeno_torna_internacional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Com buffer reduzido, ponto antes PROXIMO vira INTERNACIONAL."""
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "0.5")
    coord = Coordenadas(latitude=-34.61, longitude=-58.37)
    assert classificar_escopo(coord) == EscopoGeografico.INTERNACIONAL


def test_classificar_escopo_buffer_grande_inclui_mais_em_proximo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Com buffer expandido, ponto antes INTERNACIONAL vira PROXIMO."""
    monkeypatch.setenv(ENV_BUFFER_PROXIMO, "30.0")
    coord = Coordenadas(latitude=-15.0, longitude=-5.0)
    assert classificar_escopo(coord) == EscopoGeografico.PROXIMO


# ============================================================
# Estrutura interna — _faixa_proximo refletir o buffer corrente
# ============================================================


def test_faixa_proximo_default_estende_brasil_em_5_graus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_BUFFER_PROXIMO, raising=False)
    faixa = _faixa_proximo()
    assert faixa.lat_min == FAIXA_BRASIL.lat_min - 5.0
    assert faixa.lat_max == FAIXA_BRASIL.lat_max + 5.0
    assert faixa.lon_min == FAIXA_BRASIL.lon_min - 5.0
    assert faixa.lon_max == FAIXA_BRASIL.lon_max + 5.0


def test_faixa_geografica_contem_inclusivo() -> None:
    faixa = FaixaGeografica(lat_min=-10.0, lat_max=10.0, lon_min=-20.0, lon_max=20.0)
    assert faixa.contem(Coordenadas(latitude=-10.0, longitude=-20.0))
    assert faixa.contem(Coordenadas(latitude=10.0, longitude=20.0))
    assert faixa.contem(Coordenadas(latitude=0.0, longitude=0.0))


def test_faixa_geografica_nao_contem_fora() -> None:
    faixa = FaixaGeografica(lat_min=-10.0, lat_max=10.0, lon_min=-20.0, lon_max=20.0)
    assert not faixa.contem(Coordenadas(latitude=-11.0, longitude=0.0))
    assert not faixa.contem(Coordenadas(latitude=11.0, longitude=0.0))
    assert not faixa.contem(Coordenadas(latitude=0.0, longitude=-21.0))
    assert not faixa.contem(Coordenadas(latitude=0.0, longitude=21.0))
