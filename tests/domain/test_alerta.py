from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import (
    EscopoGeografico,
    FonteClassificacao,
    FonteDado,
    NivelRisco,
    TipoEvento,
)
from alertavida.domain.municipio import Municipio

_BASE_PAYLOAD = {
    "cod_alerta": "12345",
    "evento": "Risco Hidrológico",
    "nivel": "MODERADO",
    "uf": "PE",
    "municipio": "Recife",
    "codibge": 2611606,
    "datahoracriacao": "2026-04-29T10:00:00",
    "latitude": -8.05,
    "longitude": -34.88,
}

# ============================================================
# Criação direta — invariantes do construtor
# ============================================================


def test_criacao_direta_valida_todos_campos() -> None:
    alerta = Alerta(
        cod_alerta="123",
        fonte=FonteDado.CEMADEN,
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
        fonte=FonteDado.CEMADEN,
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
            fonte=FonteDado.CEMADEN,
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            municipio=Municipio(nome="Campinas", uf="SP"),
            data_criacao=datetime.fromisoformat("2026-04-29T10:00:00+00:00"),
        )


def test_criacao_direta_com_escopo_explicito() -> None:
    alerta = Alerta(
        cod_alerta="EONET_99",
        fonte=FonteDado.EONET,
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
        "cod_alerta": "1001",
        "evento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "uf": "sp",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "ult_atualizacao": "2026-04-29T12:00:00",
        "latitude": "-23.55",
        "longitude": "-46.63",
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
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
        "cod_alerta": "1001",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "codibge": 3550308,
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.municipio is not None
    assert alerta.municipio.codigo_ibge == 3550308


def test_from_dict_aliases_especulativos_nao_sao_reconhecidos() -> None:
    """Regressão (issue #19): from_dict só reconhece as chaves reais do
    CEMADEN, confirmadas empiricamente contra 475 itens reais (issue #30).

    Este payload usa exclusivamente aliases especulativos que o CEMADEN
    nunca emitiu em nenhuma amostra real (`id`, `nivel_alerta`, `state`,
    `cidade`, `lat`, `lng`, `dataCriacao`, `ultima_atualizacao`) — o
    fallback multi-alias que existia antes foi removido de propósito.
    """
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
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


# ============================================================
# from_dict — Município opcional (fonte não fornece)
# ============================================================


def test_from_dict_sem_municipio_apenas_coordenadas() -> None:
    payload = {
        "cod_alerta": "EONET_5421",
        "evento": "Wildfires",
        "nivel": "INDETERMINADO",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -10.5,
        "longitude": -52.3,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.cod_alerta == "EONET_5421"
    assert alerta.municipio is None
    assert alerta.coordenadas.latitude == -10.5


def test_from_dict_sem_uf_municipio_fica_none() -> None:
    payload = {
        "cod_alerta": "999",
        "evento": "Risco Hidrológico",
        "nivel": "ALTO",
        "municipio": "Recife",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.municipio is None


def test_from_dict_sem_nome_municipio_fica_none() -> None:
    payload = {
        "cod_alerta": "999",
        "evento": "Risco Hidrológico",
        "nivel": "ALTO",
        "uf": "PE",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.municipio is None


# ============================================================
# from_dict — Coordenadas obrigatórias
# ============================================================


def test_from_dict_sem_coordenadas_lanca() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_sem_latitude_lanca() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_latitude_invalida_lanca() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": 999,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_coordenadas_nao_numericas_lanca() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": "não é número",
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem coordenadas válidas"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


# ============================================================
# from_dict — cod_alerta como string
# ============================================================


def test_from_dict_cod_alerta_alfanumerico_aceita() -> None:
    payload = {
        "cod_alerta": "EONET_5421",
        "evento": "Wildfires",
        "nivel": "INDETERMINADO",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -10.5,
        "longitude": -52.3,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.cod_alerta == "EONET_5421"


def test_from_dict_cod_alerta_numerico_aceita_como_string() -> None:
    payload = {
        "cod_alerta": 1854,
        "evento": "Risco Hidrológico",
        "nivel": "MODERADO",
        "uf": "PE",
        "municipio": "Recife",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -8.05,
        "longitude": -34.88,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.cod_alerta == "1854"


def test_from_dict_sem_cod_alerta_lanca() -> None:
    payload = {
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_cod_alerta_string_vazia_lanca() -> None:
    payload = {
        "cod_alerta": "",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


# ============================================================
# from_dict — Outros campos (tipo_evento, nivel, datas, ult_atualizacao)
# ============================================================


def test_from_dict_tipo_evento_vazio_lanca() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem tipo_evento"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_tipo_evento_desconhecido_vira_indeterminado() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Qualquer coisa",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.tipo_evento == TipoEvento.INDETERMINADO


def test_from_dict_sem_nivel_lanca() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    with pytest.raises(ValueError, match="Alerta sem nivel_risco"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_com_ult_atualizacao_popula() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "ult_atualizacao": "2026-05-01T08:30:00-03:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.ult_atualizacao is not None
    assert alerta.ult_atualizacao.utcoffset() == timedelta(hours=-3)


def test_from_dict_sem_ult_atualizacao_none() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.ult_atualizacao is None


def test_from_dict_data_criacao_naive_assume_utc() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.data_criacao.tzinfo is not None
    assert alerta.data_criacao.utcoffset() == timedelta(0)


def test_from_dict_data_criacao_com_timezone_preserva() -> None:
    payload = {
        "cod_alerta": "10",
        "evento": "Queimada",
        "nivel": "ALTO",
        "uf": "SP",
        "municipio": "Sao Paulo",
        "datahoracriacao": "2026-04-29T10:00:00-03:00",
        "latitude": -23.55,
        "longitude": -46.63,
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.data_criacao.utcoffset() == timedelta(hours=-3)


# ============================================================
# from_dict — bordas: campos obrigatórios inválidos
# ============================================================


def test_from_dict_codigo_apenas_espacos() -> None:
    payload = {**_BASE_PAYLOAD, "cod_alerta": "   "}
    with pytest.raises(ValueError, match="Alerta sem cod_alerta válido"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_nivel_xpto_lanca() -> None:
    payload = {**_BASE_PAYLOAD, "nivel": "XPTO"}
    with pytest.raises(ValueError, match="XPTO"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_sem_data_criacao_lanca() -> None:
    payload = {k: v for k, v in _BASE_PAYLOAD.items() if k != "datahoracriacao"}
    with pytest.raises(ValueError, match="Alerta sem data_criacao"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_data_criacao_invalida_lanca() -> None:
    payload = {**_BASE_PAYLOAD, "datahoracriacao": "não-data"}
    with pytest.raises(ValueError, match="Alerta sem data_criacao"):
        Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)


def test_from_dict_ult_atualizacao_invalido_vira_none() -> None:
    payload = {**_BASE_PAYLOAD, "ult_atualizacao": "não-data"}
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.ult_atualizacao is None


def test_from_dict_codibge_nao_inteiro_ignora() -> None:
    payload = {**_BASE_PAYLOAD, "codibge": "abc"}
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.municipio is not None
    assert alerta.municipio.codigo_ibge is None


def test_from_dict_uf_curta_municipio_none() -> None:
    payload = {**_BASE_PAYLOAD, "uf": "A"}
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.municipio is None


# ============================================================
# Imutabilidade e serialização
# ============================================================


def test_immutabilidade_alerta() -> None:
    alerta = Alerta(
        cod_alerta="123",
        fonte=FonteDado.CEMADEN,
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
        fonte=FonteDado.CEMADEN,
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
        fonte=FonteDado.EONET,
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
        fonte=FonteDado.CEMADEN,
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
        fonte=FonteDado.EONET,
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
            fonte=FonteDado.CEMADEN,
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
            fonte=FonteDado.CEMADEN,
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
            fonte=FonteDado.CEMADEN,
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
        fonte=FonteDado.CEMADEN,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=-8.05, longitude=-34.88),
        data_criacao=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
        cobrade_codigo=None,
        fonte_classificacao=FonteClassificacao.INDETERMINADA,
    )
    assert alerta.cobrade_codigo is None
    assert alerta.fonte_classificacao == FonteClassificacao.INDETERMINADA


# ============================================================
# Camada 4 B.0.a — fonte como atributo do modelo
# ============================================================


def test_from_dict_exige_fonte_como_kwarg():
    """from_dict sem fonte deve levantar TypeError (kwarg obrigatório)."""
    payload = {
        "cod_alerta": "1",
        "evento": "Risco Hidrológico",
        "nivel": "ALTO",
        "latitude": -10.0,
        "longitude": -40.0,
        "datahoracriacao": "2026-05-13T10:00:00",
    }
    with pytest.raises(TypeError):
        Alerta.from_dict(payload)


def test_from_dict_rejeita_fonte_como_string_em_strict():
    """from_dict NÃO aceita string para fonte — Annotated[FonteDado, Strict()] no campo.

    Strict() em fonte bloqueia coerção string → enum. Mesmo from_dict passando
    o parâmetro direto para cls(fonte=fonte), string solta quebra na construção.
    """
    payload = {
        "cod_alerta": "1",
        "evento": "Risco Hidrológico",
        "nivel": "ALTO",
        "latitude": -10.0,
        "longitude": -40.0,
        "datahoracriacao": "2026-05-13T10:00:00",
    }
    with pytest.raises(ValidationError):
        Alerta.from_dict(payload, fonte="CEMADEN")


def test_from_dict_aceita_fonte_como_enum():
    """from_dict com fonte=FonteDado.CEMADEN constrói Alerta com fonte populada."""
    payload = {
        "cod_alerta": "1",
        "evento": "Risco Hidrológico",
        "nivel": "ALTO",
        "latitude": -10.0,
        "longitude": -40.0,
        "datahoracriacao": "2026-05-13T10:00:00",
    }
    alerta = Alerta.from_dict(payload, fonte=FonteDado.CEMADEN)
    assert alerta.fonte == FonteDado.CEMADEN


def test_alerta_construtor_exige_fonte():
    """Construtor direto sem fonte levanta ValidationError."""
    with pytest.raises(ValidationError):
        Alerta(
            cod_alerta="1",
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
            data_criacao=datetime(2026, 5, 13, tzinfo=timezone.utc),
        )


def test_alerta_construtor_rejeita_fonte_string():
    """Strict() bloqueia coerção string → FonteDado no construtor direto."""
    with pytest.raises(ValidationError):
        Alerta(
            cod_alerta="1",
            fonte="CEMADEN",  # string solta — deve falhar
            tipo_evento=TipoEvento.HIDROLOGICO,
            nivel_risco=NivelRisco.ALTO,
            coordenadas=Coordenadas(latitude=-10.0, longitude=-40.0),
            data_criacao=datetime(2026, 5, 13, tzinfo=timezone.utc),
        )
