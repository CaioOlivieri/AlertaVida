"""Testes de NasaEonetSource — Camada 4 Parte C.1.b."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from alertavida.domain.enums import (
    EscopoGeografico,
    FonteClassificacao,
    FonteDado,
    NivelRisco,
    TipoEvento,
)
from alertavida.sources import FalhaDeColeta
from alertavida.sources.nasa_eonet import NasaEonetSource
from tests.fixtures.eonet import (
    CATEGORIA_DESCONHECIDA,
    EVENTO_SEM_GEOMETRY,
    INCENDIO_BRASIL,
    INCENDIO_EXTERIOR,
    TEMPESTADE_MULTI_FIX,
    evento,
    fix_point,
    payload,
)
from tests.sources.contrato import verificar_contrato_data_source

# ============================================================
# Helpers
# ============================================================


def _opener_de_payload(payload_bytes: bytes):
    """Cria um opener fake que retorna o payload dado em todas as chamadas."""
    response = Mock()
    response.read.return_value = payload_bytes
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return Mock(return_value=context)


def _opener_de_eventos(*eventos):
    """Opener fake que serializa um payload EONET com os eventos dados."""
    return _opener_de_payload(json.dumps(payload(list(eventos))).encode("utf-8"))


# ============================================================
# _montar_alerta
# ============================================================


class TestMontarAlerta:
    def test_evento_no_brasil(self):
        source = NasaEonetSource()
        out = source._montar_alerta(INCENDIO_BRASIL)
        assert out.cod_alerta == "EONET_BR_FIRE"
        assert out.fonte == FonteDado.EONET
        assert out.tipo_evento == TipoEvento.CLIMATOLOGICO
        assert out.nivel_risco == NivelRisco.INDETERMINADO
        assert out.coordenadas.latitude == -3.0
        assert out.coordenadas.longitude == -60.0
        assert out.escopo_geografico == EscopoGeografico.BRASIL
        assert out.municipio is None
        assert out.descricao == "Wildfire - Amazonas, Brazil"
        assert out.data_criacao == datetime(2026, 5, 18, tzinfo=timezone.utc)
        assert out.cobrade_codigo == "1.4.1.0.0"
        assert out.fonte_classificacao == FonteClassificacao.MAPEADA_POR_NOME

    def test_evento_no_exterior_e_internacional(self):
        source = NasaEonetSource()
        out = source._montar_alerta(INCENDIO_EXTERIOR)
        assert out.escopo_geografico == EscopoGeografico.INTERNACIONAL

    def test_multi_fix_usa_o_mais_recente_por_data(self):
        source = NasaEonetSource()
        out = source._montar_alerta(TEMPESTADE_MULTI_FIX)
        # Fix mais recente: 2026-05-18T12:00:00Z em (-42, -22), apesar de estar
        # no meio da lista (índice 1).
        assert out.tipo_evento == TipoEvento.METEOROLOGICO
        assert out.coordenadas.longitude == -42.0
        assert out.coordenadas.latitude == -22.0
        assert out.data_criacao == datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)

    def test_montar_alerta_wildfires_mapeia_cobrade(self):
        """C.2 mapeia wildfires → 1.4.1.0.0 com MAPEADA_POR_NOME."""
        source = NasaEonetSource()
        out = source._montar_alerta(INCENDIO_BRASIL)
        assert out.cobrade_codigo == "1.4.1.0.0"
        assert out.fonte_classificacao == FonteClassificacao.MAPEADA_POR_NOME

    def test_montar_alerta_categoria_desconhecida_mantem_indeterminado(self):
        """Categoria não mapeada (waterColor) mantém cobrade=None e INDETERMINADA."""
        source = NasaEonetSource()
        out = source._montar_alerta(CATEGORIA_DESCONHECIDA)
        assert out.cobrade_codigo is None
        assert out.fonte_classificacao == FonteClassificacao.INDETERMINADA

    def test_categoria_desconhecida_vira_indeterminado(self):
        source = NasaEonetSource()
        out = source._montar_alerta(CATEGORIA_DESCONHECIDA)
        assert out.tipo_evento == TipoEvento.INDETERMINADO

    def test_lanca_sem_geometry(self):
        source = NasaEonetSource()
        with pytest.raises(ValueError):
            source._montar_alerta(EVENTO_SEM_GEOMETRY)

    def test_lanca_sem_id(self):
        source = NasaEonetSource()
        ev = evento(
            id="",
            categoria="wildfires",
            geometry=[fix_point((-50.0, -10.0), "2026-05-18T00:00:00Z")],
        )
        with pytest.raises(ValueError):
            source._montar_alerta(ev)

    def test_lanca_se_nao_for_dict(self):
        source = NasaEonetSource()
        with pytest.raises(ValueError):
            source._montar_alerta([])  # type: ignore[arg-type]

    def test_lanca_coordenadas_fora_de_faixa(self):
        source = NasaEonetSource()
        ev = evento(
            id="EONET_BAD",
            categoria="wildfires",
            geometry=[fix_point((-50.0, 200.0), "2026-05-18T00:00:00Z")],
        )
        with pytest.raises(ValueError):
            source._montar_alerta(ev)

    def test_lanca_se_nenhum_fix_e_point(self):
        source = NasaEonetSource()
        ev = evento(
            id="EONET_POLY",
            categoria="wildfires",
            geometry=[{"type": "Polygon", "coordinates": [], "date": "2026-05-18T00:00:00Z"}],
        )
        with pytest.raises(ValueError):
            source._montar_alerta(ev)


# ============================================================
# coletar — invariantes
# ============================================================


class TestColetar:
    def test_coletado_em_e_aware(self, monkeypatch):
        opener = _opener_de_eventos()
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        resultado = NasaEonetSource(opener=opener).coletar()
        assert resultado.coletado_em.tzinfo is not None

    def test_alertas_tem_fonte_eonet(self, monkeypatch):
        opener = _opener_de_eventos(INCENDIO_BRASIL)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        resultado = NasaEonetSource(opener=opener).coletar()
        assert len(resultado.alertas) == 1
        assert resultado.alertas[0].fonte == FonteDado.EONET

    def test_evento_sem_geometry_conta_como_descartado(self, monkeypatch):
        opener = _opener_de_eventos(INCENDIO_BRASIL, EVENTO_SEM_GEOMETRY)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        resultado = NasaEonetSource(opener=opener).coletar()
        assert len(resultado.alertas) == 1
        assert resultado.descartados == 1

    def test_propaga_typeerror_como_bug(self, monkeypatch):
        opener = _opener_de_eventos(INCENDIO_BRASIL)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)

        def montar_que_levanta_typeerror(self, evento):
            raise TypeError("bug interno simulado")

        monkeypatch.setattr(NasaEonetSource, "_montar_alerta", montar_que_levanta_typeerror)
        with pytest.raises(TypeError, match="bug interno simulado"):
            NasaEonetSource(opener=opener).coletar()


# ============================================================
# coletar — FalhaDeColeta
# ============================================================


class TestColetarFalhaDeColeta:
    def test_levanta_falha_em_rede_esgotada(self, monkeypatch):
        opener = Mock(side_effect=URLError("falha persistente"))
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            NasaEonetSource(opener=opener).coletar()
        assert exc_info.value.fonte == FonteDado.EONET
        assert isinstance(exc_info.value.original, URLError)

    def test_levanta_falha_em_json_invalido(self, monkeypatch):
        opener = _opener_de_payload(b"{ nao eh json valido")
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            NasaEonetSource(opener=opener).coletar()
        assert isinstance(exc_info.value.original, json.JSONDecodeError)

    def test_levanta_falha_em_unicode_invalido(self, monkeypatch):
        opener = _opener_de_payload(b"\xff\xfe invalido utf-8")
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            NasaEonetSource(opener=opener).coletar()
        assert isinstance(exc_info.value.original, UnicodeDecodeError)

    def test_levanta_falha_quando_dict_sem_events(self, monkeypatch):
        opener = _opener_de_payload(b'{"items": []}')
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            NasaEonetSource(opener=opener).coletar()
        assert "não reconhecido" in exc_info.value.causa

    def test_levanta_falha_quando_payload_nao_e_dict(self, monkeypatch):
        opener = _opener_de_payload(b'["lista no topo"]')
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            NasaEonetSource(opener=opener).coletar()
        assert "inesperado" in exc_info.value.causa


# ============================================================
# coletar — contrato parametrizado
# ============================================================


class TestContrato:
    def test_obedece_contrato_data_source(self, monkeypatch):
        opener = _opener_de_eventos(INCENDIO_BRASIL, INCENDIO_EXTERIOR)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        verificar_contrato_data_source(lambda: NasaEonetSource(opener=opener))
