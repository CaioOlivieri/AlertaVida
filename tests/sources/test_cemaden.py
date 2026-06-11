"""Testes de CemadenSource — Camada 4 Parte B.1.b."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from alertavida.domain.enums import FonteClassificacao, FonteDado
from alertavida.sources import FalhaDeColeta
from alertavida.sources.cemaden import CemadenSource
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


def _opener_que_falha(*excecoes):
    """Cria um opener fake que levanta cada exceção em sequência."""
    return Mock(side_effect=list(excecoes))


_ITEM_VALIDO = {
    "codigoalerta": "12345",
    "municipio": "Rio de Janeiro",
    "estado": "RJ",
    "tipoevento": "Alagamento",
    "nivel": "MODERADO",
    "datahoracriacao": "2025-12-20T14:30:00",
    "latitude": -22.91,
    "longitude": -43.17,
}


# ============================================================
# _montar_alerta — migrados de test_monitor.py (7 testes)
# ============================================================

class TestMontarAlerta:
    def test_mapeia_nomes_padrao_cemaden(self):
        source = CemadenSource()
        out = source._montar_alerta(_ITEM_VALIDO)
        assert out.cod_alerta == "12345"
        assert out.municipio is not None
        assert out.municipio.nome == "Rio de Janeiro"
        assert out.municipio.uf == "RJ"
        assert out.tipo_evento.value == "HIDROLOGICO"
        assert out.nivel_risco.value == "MODERADO"
        assert out.coordenadas.latitude == -22.91
        assert out.escopo_geografico.value == "BRASIL"
        assert out.data_criacao == datetime(2025, 12, 20, 14, 30, tzinfo=timezone.utc)

    def test_mapeia_nomes_alternativos(self):
        item = {
            "cod_alerta": 99,
            "cidade": "Curitiba",
            "estado": "PR",
            "tipo_evento": "Deslizamento",
            "nivel": "ALTO",
            "data_criacao": "2024-11-01 08:00:00",
            "latitude": -25.43,
            "longitude": -49.27,
        }
        source = CemadenSource()
        out = source._montar_alerta(item)
        assert out.cod_alerta == "99"
        assert out.tipo_evento.value == "GEOLOGICO"
        assert out.nivel_risco.value == "ALTO"

    def test_lanca_sem_cod_alerta(self):
        source = CemadenSource()
        item = {"municipio": "X", "uf": "SP", "latitude": -23.55, "longitude": -46.63}
        with pytest.raises(ValueError):
            source._montar_alerta(item)

    def test_lanca_sem_coordenadas(self):
        source = CemadenSource()
        item = {
            "cod_alerta": 100, "municipio": "X", "uf": "SP",
            "tipoevento": "Risco Hidrológico", "nivel": "ALTO",
            "datahoracriacao": "2026-04-29T10:00:00",
        }
        with pytest.raises(ValueError):
            source._montar_alerta(item)

    def test_lanca_quando_obrigatorios_ausentes(self):
        source = CemadenSource()
        with pytest.raises(ValueError):
            source._montar_alerta({"id": 7})

    def test_lanca_se_item_nao_e_dict(self):
        source = CemadenSource()
        with pytest.raises(ValueError):
            source._montar_alerta([])  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            source._montar_alerta("x")  # type: ignore[arg-type]

    def test_lanca_quando_item_e_none(self):
        source = CemadenSource()
        with pytest.raises(ValueError):
            source._montar_alerta(None)  # type: ignore[arg-type]


# ============================================================
# _montar_alerta — COBRADE (3 testes migrados de A.2)
# ============================================================

class TestMontarAlertaCobrade:
    _BASE = {
        "codigoalerta": "1001", "nivel": "MODERADO", "estado": "PE",
        "municipio": "Recife", "datahoracriacao": "2026-05-01T10:00:00",
        "latitude": -8.05, "longitude": -34.88,
    }

    def test_risco_hidrologico_popula_cobrade(self):
        source = CemadenSource()
        alerta = source._montar_alerta({**self._BASE, "tipoevento": "Risco Hidrológico"})
        assert alerta.cobrade_codigo == "1.2.0.0.0"
        assert alerta.fonte_classificacao == FonteClassificacao.MAPEADA_POR_NOME

    def test_movimentos_de_massa_popula_cobrade(self):
        source = CemadenSource()
        alerta = source._montar_alerta({**self._BASE, "tipoevento": "Movimentos de Massa", "nivel": "ALTO"})
        assert alerta.cobrade_codigo == "1.1.3.0.0"
        assert alerta.fonte_classificacao == FonteClassificacao.MAPEADA_POR_NOME

    def test_tipoevento_desconhecido_cobrade_none(self):
        source = CemadenSource()
        alerta = source._montar_alerta({**self._BASE, "tipoevento": "Tipo Desconhecido"})
        assert alerta.cobrade_codigo is None
        assert alerta.fonte_classificacao == FonteClassificacao.INDETERMINADA


# ============================================================
# _fetch_com_retry — migrados de test_monitor.py (4 testes)
# ============================================================

class TestFetchComRetry:
    def test_sucesso_primeira_tentativa(self, monkeypatch):
        payload = b'{"ok": true}'
        opener = _opener_de_payload(payload)
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        out = source._fetch_com_retry()
        assert out == payload
        assert opener.call_count == 1

    def test_sucesso_apos_falhas_temporarias(self, monkeypatch):
        payload = b"ok"
        ctx_ok = _opener_de_payload(payload).return_value
        opener = Mock(side_effect=[URLError("timeout"), URLError("conexao"), ctx_ok])
        sleeps = []
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda s: sleeps.append(s))
        source = CemadenSource(opener=opener)
        out = source._fetch_com_retry()
        assert out == payload
        assert opener.call_count == 3
        assert len(sleeps) == 2

    def test_falha_4xx_nao_faz_retry(self, monkeypatch):
        err = HTTPError(url="https://exemplo", code=404, msg="Not Found", hdrs=None, fp=None)
        opener = Mock(side_effect=err)
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        with pytest.raises(HTTPError) as exc_info:
            source._fetch_com_retry()
        assert exc_info.value.code == 404
        assert opener.call_count == 1

    def test_esgota_tentativas_e_propaga(self, monkeypatch):
        opener = Mock(side_effect=URLError("falha"))
        sleeps = []
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda s: sleeps.append(s))
        source = CemadenSource(opener=opener)
        with pytest.raises(URLError):
            source._fetch_com_retry()
        assert opener.call_count == 4
        assert len(sleeps) == 3


# ============================================================
# coletar — invariantes de B.1 (testes NOVOS)
# ============================================================

class TestColetarInvariantes:
    def test_coletado_em_e_aware(self, monkeypatch):
        opener = _opener_de_payload(b'{"alertas":[]}')
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        resultado = source.coletar()
        assert resultado.coletado_em.tzinfo is not None

    def test_alertas_retornados_tem_fonte_cemaden(self, monkeypatch):
        payload = json.dumps({"alertas": [_ITEM_VALIDO]}).encode("utf-8")
        opener = _opener_de_payload(payload)
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        resultado = source.coletar()
        assert len(resultado.alertas) == 1
        assert resultado.alertas[0].fonte == FonteDado.CEMADEN

    def test_propaga_typeerror_como_bug(self, monkeypatch):
        """Invariante crítica B.1: coletar só captura ValueError no loop.
        Bugs internos (TypeError, AttributeError, KeyError) propagam.
        """
        payload = json.dumps({"alertas": [_ITEM_VALIDO]}).encode("utf-8")
        opener = _opener_de_payload(payload)
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)

        def montar_que_levanta_typeerror(self, item):
            raise TypeError("bug interno simulado")

        monkeypatch.setattr(CemadenSource, "_montar_alerta", montar_que_levanta_typeerror)
        source = CemadenSource(opener=opener)
        with pytest.raises(TypeError, match="bug interno simulado"):
            source.coletar()

    def test_propaga_attributeerror_como_bug(self, monkeypatch):
        payload = json.dumps({"alertas": [_ITEM_VALIDO]}).encode("utf-8")
        opener = _opener_de_payload(payload)
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)

        def montar_que_levanta_attributeerror(self, item):
            raise AttributeError("bug interno simulado")

        monkeypatch.setattr(CemadenSource, "_montar_alerta", montar_que_levanta_attributeerror)
        source = CemadenSource(opener=opener)
        with pytest.raises(AttributeError):
            source.coletar()


# ============================================================
# coletar — FalhaDeColeta (testes NOVOS)
# ============================================================

class TestColetarFalhaDeColeta:
    def test_levanta_falha_em_rede_esgotada(self, monkeypatch):
        opener = Mock(side_effect=URLError("falha persistente"))
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        with pytest.raises(FalhaDeColeta) as exc_info:
            source.coletar()
        assert exc_info.value.fonte == FonteDado.CEMADEN
        assert isinstance(exc_info.value.original, URLError)

    def test_levanta_falha_em_json_invalido(self, monkeypatch):
        opener = _opener_de_payload(b"{ nao eh json valido")
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        with pytest.raises(FalhaDeColeta) as exc_info:
            source.coletar()
        assert exc_info.value.fonte == FonteDado.CEMADEN
        assert isinstance(exc_info.value.original, json.JSONDecodeError)

    def test_levanta_falha_em_unicode_invalido(self, monkeypatch):
        opener = _opener_de_payload(b"\xff\xfe invalido utf-8")
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        with pytest.raises(FalhaDeColeta) as exc_info:
            source.coletar()
        assert exc_info.value.fonte == FonteDado.CEMADEN
        assert isinstance(exc_info.value.original, UnicodeDecodeError)

    def test_levanta_falha_quando_dict_sem_chave_conhecida(self, monkeypatch):
        opener = _opener_de_payload(b'{"widgets":[]}')
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        with pytest.raises(FalhaDeColeta) as exc_info:
            source.coletar()
        assert exc_info.value.fonte == FonteDado.CEMADEN
        assert "não reconhecido" in exc_info.value.causa

    def test_levanta_falha_quando_payload_nao_e_list_nem_dict(self, monkeypatch):
        opener = _opener_de_payload(b'"string isolada"')
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        source = CemadenSource(opener=opener)
        with pytest.raises(FalhaDeColeta) as exc_info:
            source.coletar()
        assert exc_info.value.fonte == FonteDado.CEMADEN
        assert "inesperado" in exc_info.value.causa


# ============================================================
# coletar — contrato parametrizado (B.1.a)
# ============================================================

class TestContrato:
    def test_obedece_contrato_data_source(self, monkeypatch):
        payload = json.dumps({"alertas": [_ITEM_VALIDO]}).encode("utf-8")
        opener = _opener_de_payload(payload)
        monkeypatch.setattr("alertavida.sources.cemaden.time.sleep", lambda _: None)
        verificar_contrato_data_source(lambda: CemadenSource(opener=opener))
