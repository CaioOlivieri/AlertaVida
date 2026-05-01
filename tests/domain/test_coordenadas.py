import pytest
from pydantic import ValidationError

from alertavida.domain.coordenadas import Coordenadas


def test_criacao_valida() -> None:
    c = Coordenadas(latitude=-23.55, longitude=-46.63)
    assert c.latitude == -23.55
    assert c.longitude == -46.63


def test_latitude_maior_que_90_invalida() -> None:
    with pytest.raises(ValidationError):
        Coordenadas(latitude=91.0, longitude=0.0)


def test_latitude_menor_que_menos_90_invalida() -> None:
    with pytest.raises(ValidationError):
        Coordenadas(latitude=-91.0, longitude=0.0)


def test_longitude_fora_do_intervalo_invalida() -> None:
    with pytest.raises(ValidationError):
        Coordenadas(latitude=0.0, longitude=181.0)


def test_polo_norte_valido() -> None:
    c = Coordenadas(latitude=90.0, longitude=0.0)
    assert c.latitude == 90.0
    assert c.longitude == 0.0


def test_polo_sul_valido() -> None:
    c = Coordenadas(latitude=-90.0, longitude=0.0)
    assert c.latitude == -90.0
    assert c.longitude == 0.0


def test_antimeridiano_valido() -> None:
    c = Coordenadas(latitude=0.0, longitude=180.0)
    assert c.latitude == 0.0
    assert c.longitude == 180.0


def test_immutabilidade() -> None:
    c = Coordenadas(latitude=0.0, longitude=0.0)
    with pytest.raises(ValidationError):
        c.latitude = 10.0
