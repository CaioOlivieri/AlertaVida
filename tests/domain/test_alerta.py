from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import EscopoGeografico, FonteClassificacao, NivelRisco, TipoEvento
from alertavida.domain.municipio import Municipio


# ============================================================
# Criação direta — invariantes do construtor
# ============================================================


def test_criacao_direta_valida_todos_campos() -> None:
    alerta = Alerta(
        cod_alerta="123",
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-22.90, longitude=-47.06),
        municipio=Municipio(nome="Campinas", uf="SP"),
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
        descricao="Alerta de teste",
    )
    assert alerta.cod_alerta == "123"
    assert alerta.coordenadas.latitude == -22.90
    assert alerta.escopo_geografico == EscopoGeografico.INDETERMINADO


def test_criacao_direta_sem_municipio_aceita() -> None:
    alerta = Alerta(
        cod_alerta="EONET_42",
        tipo_evento=TipoEvento.METEOROLOGICO,
        nivel_risco=NivelRisco.INDETERMINADO,
        coordenadas=Coordenadas(latitude=-15.78, longitude=-47.93),
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
    )
    assert alerta.municipio is None


def test_criacao_direta_sem_coordenadas_lanca() -> None:
    with pytest.raises(ValidationError):
        Alerta(
            cod_alerta="123",
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            municipio=Municipio(nome="Campinas", uf="SP"),
            data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
        )


def test_criacao_direta_com_escopo_explicito() -> None:
    alerta = Alerta(
        cod_alerta="EONET_99",
        tipo_evento=TipoEvento.CLIMATOLOGICO,
        nivel_risco=NivelRisco.INDETERMINADO,
        coordenadas=Coordenadas(latitude=35.68, longitude=139.69),
        escopo_geografico=EscopoGeografico.INTERNACIONAL,
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
    )
    assert alerta.escopo_geografico == EscopoGeografico.INTERNACIONAL


# ============================================================
# from_dict — payload realista CEMADEN (com coordenadas + município)
# ============================================================


def test_from_dict_payload_realista_cemaden() -> None:
    payload = {
        "codigoalerta": "1001",
        "tipoevento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "estado": "sp",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "ult_atualizacao": "2026-04-29T12:00:00",
        "latitude": "-23.55",
        "longitude": "-46.63",
        "descricao": "Teste",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == "1001"
    assert alerta.municipio is not None
    assert alerta.municipio.uf == "SP"
    assert alerta.tipo_evento == TipoEvento.HIDROLOGICO
    assert alerta.coordenadas.latitude == -23.55
    assert alerta.data_criacao.tzinfo is not None
    assert alerta.ult_atualizacao == datetime.fromisoformat(
        "2026-04-29T12:00:00"
    ).replace(tzinfo=timezone.utc)


def test_from_dict_com_codibge_popula_codigo_ibge() -> None:
    payload = {
        "codigoalerta": "1001",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "codibge": 3550308,
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.municipio is not None
    assert alerta.municipio.codigo_ibge == 3550308


def test_from_dict_com_chaves_alternativas() -> None:
    payload = {
        "id": "EONET_42",
        "evento": "Queimada",
        "nivel_alerta": "ALTO",
        "state": "mg",
        "cidade": "Belo Horizonte",
        "lat": -19.92,
        "lng": -43.94,
        "dataCriacao": "2026-04-29T10:00:00",
        "ultima_atualizacao": "2026-04-29T14:30:00+00:00",
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == "EONET_42"
    assert alerta.municipio is not None
    assert alerta.municipio.nome == "Belo Horizonte"
    assert alerta.tipo_evento == TipoEvento.CLIMATOLOGICO
    assert alerta.ult_atualizacao == datetime.fromisoformat(
        "2026-04-29T14:30:00+00:00"
    )


# ============================================================
# from_dict — Município opcional (fonte não fornece)
# ============================================================


def test_from_dict_sem_municipio_apenas_coordenadas() -> None:
    payload = {
        "codigoalerta": "EONET_5421",
        "tipoevento": "Wildfires",
        "nivel": "INDETERMINADO",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -10.5,
        "longitude": -52.3,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == "EONET_5421"
    assert alerta.municipio is None
    assert alerta.coordenadas.latitude == -10.5


def test_from_dict_sem_uf_municipio_fica_none() -> None:
    payload = {
        "codigoalerta": "999",
        "tipoevento": "Risco Hidrológico",
        "nivel": "ALTO",
        "municipio": "Recife",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.municipio is None


def test_from_dict_sem_nome_municipio_fica_none() -> None:
    payload = {
        "codigoalerta": "999",
        "tipoevento": "Risco Hidrológico",
        "nivel": "ALTO",
        "estado": "PE",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.municipio is None


# ============================================================
# from_dict — Coordenadas obrigatórias
# ============================================================


def test_from_dict_sem_coordenadas_lanca() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload)


def test_from_dict_sem_latitude_lanca() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload)


def test_from_dict_latitude_invalida_lanca() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": 999,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload)


def test_from_dict_coordenadas_nao_numericas_lanca() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": "não é número",
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload)


# ============================================================
# from_dict — cod_alerta como string
# ============================================================


def test_from_dict_cod_alerta_alfanumerico_aceita() -> None:
    payload = {
        "codigoalerta": "EONET_5421",
        "tipoevento": "Wildfires",
        "nivel": "INDETERMINADO",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -10.5,
        "longitude": -52.3,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == "EONET_5421"


def test_from_dict_cod_alerta_numerico_aceita_como_string() -> None:
    payload = {
        "codigoalerta": 1854,
        "tipoevento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "estado": "PE",
        "municipio": "Recife",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == "1854"


def test_from_dict_sem_cod_alerta_lanca() -> None:
    payload = {
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload)


def test_from_dict_cod_alerta_string_vazia_lanca() -> None:
    payload = {
        "codigoalerta": "",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload)


def test_from_dict_fallback_quando_chave_principal_vazia() -> None:
    payload = {
        "codigoalerta": "",
        "id": "42",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.cod_alerta == "42"


# ============================================================
# from_dict — Outros campos (tipo_evento, nivel, datas, ult_atualizacao)
# ============================================================


def test_from_dict_tipo_evento_vazio_lanca() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem tipo_evento"):
        Alerta.from_dict(payload)


def test_from_dict_tipo_evento_desconhecido_vira_indeterminado() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Qualquer coisa",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.tipo_evento == TipoEvento.INDETERMINADO


def test_from_dict_sem_nivel_lanca() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem nivel_risco"):
        Alerta.from_dict(payload)


def test_from_dict_com_ult_atualizacao_popula() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "dataAtualizacao": "2026-05-01T08:30:00-03:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.ult_atualizacao is not None
    assert alerta.ult_atualizacao.utcoffset() == timedelta(hours=-3)


def test_from_dict_sem_ult_atualizacao_none() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.ult_atualizacao is None


def test_from_dict_data_criacao_naive_assume_utc() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.data_criacao.tzinfo is not None
    assert alerta.data_criacao.utcoffset() == timedelta(0)


def test_from_dict_data_criacao_com_timezone_preserva() -> None:
    payload = {
        "codigoalerta": "10",
        "tipoevento": "Queimada",
        "nivel": "ALTO",
        "estado": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00-03:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload)
    assert alerta.data_criacao.utcoffset() == timedelta(hours=-3)


# ============================================================
# Imutabilidade e serialização
# ============================================================


def test_immutabilidade_alerta() -> None:
    alerta = Alerta(
        cod_alerta="123",
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-22.90, longitude=-47.06),
        municipio=Municipio(nome="Campinas", uf="SP"),
        data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
    )
    with pytest.raises(ValidationError):
        alerta.cod_alerta = "999"


def test_alerta_serializa_e_desserializa_json_sem_perder_dados() -> None:
    original = Alerta(
        cod_alerta="42",
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
        municipio=Municipio(nome="Recife", uf="PE"),
        data_criacao=datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc),
        descricao="Enchente forte",
    )
    json_str = original.model_dump_json()
    reconstruido = Alerta.model_validate_json(json_str)
    assert reconstruido == original


def test_alerta_sem_municipio_serializa_e_desserializa_json() -> None:
    original = Alerta(
        cod_alerta="EONET_99",
        tipo_evento=TipoEvento.INDETERMINADO,
        nivel_risco=NivelRisco.INDETERMINADO,
        coordenadas=Coordenadas(latitude=35.68, longitude=139.69),
        data_criacao=datetime(2026, 4, 29, 10, 0, 0, tzinfo=timezone.utc),
    )
    json_str = original.model_dump_json()
    reconstruido = Alerta.model_validate_json(json_str)
    assert reconstruido == original
    assert reconstruido.municipio is None


# ============================================================
# Camada 4 A.2 — cobrade_codigo + fonte_classificacao
# ============================================================


def test_cobrade_codigo_e_fonte_mapeada_aceita() -> None:
    alerta = Alerta(
        cod_alerta="1001",
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.MODERADO,
        coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
        data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
        cobrade_codigo="1.2.0.0.0",
        fonte_classificacao=FonteClassificacao.MAPEADA_POR_NOME,
    )
    assert alerta.cobrade_codigo == "1.2.0.0.0"
    assert alerta.fonte_classificacao == FonteClassificacao.MAPEADA_POR_NOME


def test_cobrade_defaults_none_e_indeterminada() -> None:
    alerta = Alerta(
        cod_alerta="EONET_42",
        tipo_evento=TipoEvento.INDETERMINADO,
        nivel_risco=NivelRisco.INDETERMINADO,
        coordenadas=Coordenadas(latitude=35.68, longitude=139.69),
        data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert alerta.cobrade_codigo is None
    assert alerta.fonte_classificacao == FonteClassificacao.INDETERMINADA


def test_cobrade_formato_invalido_lanca() -> None:
    with pytest.raises(ValidationError):
        Alerta(
            cod_alerta="1001",
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
            data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
            cobrade_codigo="formato_errado",
            fonte_classificacao=FonteClassificacao.MAPEADA_POR_NOME,
        )


def test_cobrade_invariante_codigo_com_fonte_indeterminada_lanca() -> None:
    with pytest.raises(ValidationError):
        Alerta(
            cod_alerta="1001",
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
            data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
            cobrade_codigo="1.2.0.0.0",
            fonte_classificacao=FonteClassificacao.INDETERMINADA,
        )


def test_cobrade_invariante_fonte_sem_codigo_lanca() -> None:
    with pytest.raises(ValidationError):
        Alerta(
            cod_alerta="1001",
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
            data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
            cobrade_codigo=None,
            fonte_classificacao=FonteClassificacao.MAPEADA_POR_NOME,
        )


def test_cobrade_none_com_fonte_indeterminada_aceita() -> None:
    alerta = Alerta(
        cod_alerta="pre_a2",
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
        data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
        cobrade_codigo=None,
        fonte_classificacao=FonteClassificacao.INDETERMINADA,
    )
    assert alerta.cobrade_codigo is None
    assert alerta.fonte_classificacao == FonteClassificacao.INDETERMINADA
