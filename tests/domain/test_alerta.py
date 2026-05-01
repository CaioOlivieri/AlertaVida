from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import NivelRisco, TipoEvento
from alertavida.domain.municipio import Municipio


def test_criacao_direta_valida_todos_campos() -> None:
    alerta = Alerta(
        cod_alerta=123,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        municipio=Municipio(nome="Campinas", uf="SP"),
        coordenadas=Coordenadas(latitude=-22.90, longitude=-47.06),
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
        descricao="Alerta de teste",
    )
    assert alerta.cod_alerta == 123


def test_criacao_sem_coordenadas_default_none() -> None:
    alerta = Alerta(
        cod_alerta=123,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        municipio=Municipio(nome="Campinas", uf="SP"),
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
    )
    assert alerta.coordenadas is None


def test_from_dict_payload_realista_cemaden() -> None:
    payload = {
        "codigoalerta": "1001",
        "tipoevento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "estado": "sp",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": "-23.55",
        "longitude": "-46.63",
        "descricao": "Teste",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == 1001
    assert alerta.municipio.uf == "SP"
    assert alerta.tipo_evento == TipoEvento.HIDROLOGICO
    assert alerta.data_criacao.tzinfo is not None


def test_from_dict_com_chaves_alternativas() -> None:
    payload = {
        "id": 42,
        "evento": "Queimada",
        "nivel_alerta": "ALTO",
        "state": "mg",
        "cidade": "Belo Horizonte",
        "dataCriacao": "2026-04-29T10:00:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == 42
    assert alerta.municipio.nome == "Belo Horizonte"
    assert alerta.tipo_evento == TipoEvento.INCENDIO


def test_from_dict_sem_cod_alerta_lanca() -> None:
    payload = {
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload)


def test_from_dict_cod_alerta_nao_numerico_lanca() -> None:
    payload = {
        "codigoalerta": "abc",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload)


def test_from_dict_cod_alerta_zero_lanca() -> None:
    payload = {
        "codigoalerta": 0,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload)


def test_from_dict_cod_alerta_negativo_lanca() -> None:
    payload = {
        "codigoalerta": -7,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload)


def test_from_dict_fallback_quando_chave_principal_vazia() -> None:
    payload = {
        "codigoalerta": "",
        "id": 42,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == 42


def test_from_dict_tipo_evento_vazio_lanca() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem tipo_evento"):
        Alerta.from_dict(payload)


def test_from_dict_tipo_evento_desconhecido_vira_outros() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Qualquer coisa",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.tipo_evento == TipoEvento.OUTROS


def test_from_dict_sem_nivel_lanca() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Queimada",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem nivel_risco"):
        Alerta.from_dict(payload)


def test_from_dict_sem_coordenadas_resulta_none() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.coordenadas is None


def test_from_dict_com_coordenadas_validas() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert isinstance(alerta.coordenadas, Coordenadas)


def test_from_dict_latitude_invalida_gera_none_em_coordenadas() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": 999,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.coordenadas is None


def test_immutabilidade_alerta() -> None:
    alerta = Alerta(
        cod_alerta=123,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        municipio=Municipio(nome="Campinas", uf="SP"),
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
    )
    with pytest.raises(ValidationError):
        alerta.cod_alerta = 999


def test_from_dict_data_criacao_naive_assume_utc() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.data_criacao.tzinfo is not None
    assert alerta.data_criacao.utcoffset() == timedelta(0)


def test_from_dict_data_criacao_com_timezone_preserva() -> None:
    payload = {
        "codigoalerta": 10,
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00-03:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.data_criacao.utcoffset() == timedelta(hours=-3)


def test_alerta_serializa_e_desserializa_json_sem_perder_dados() -> None:
    original = Alerta(
        cod_alerta=42,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        municipio=Municipio(nome="Recife", uf="PE"),
        coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
        data_criacao=datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc),
        descricao="Enchente forte",
    )
    json_str = original.model_dump_json()
    reconstruido = Alerta.model_validate_json(json_str)
    assert reconstruido == original


def test_alerta_sem_coordenadas_serializa_e_desserializa_json() -> None:
    original = Alerta(
        cod_alerta=99,
        tipo_evento=TipoEvento.OUTROS,
        nivel_risco=NivelRisco.BAIXO,
        municipio=Municipio(nome="Cuiabá", uf="MT"),
        data_criacao=datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc),
    )
    json_str = original.model_dump_json()
    reconstruido = Alerta.model_validate_json(json_str)
    assert reconstruido == original
    assert reconstruido.coordenadas is None
