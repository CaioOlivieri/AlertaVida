"""Testes do transporte HTTP compartilhado — sources/_http.py.

Consolida os testes de retry/backoff que antes viviam duplicados em
test_cemaden.py e test_nasa_eonet.py (uma classe TestFetchComRetry em cada).
"""

import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from alertavida.domain.enums import FonteDado
from alertavida.sources import FalhaDeColeta
from alertavida.sources._http import fetch_com_retry, parse_json


def _opener_de_payload(payload_bytes: bytes):
    """Opener fake que retorna o payload dado em todas as chamadas."""
    response = Mock()
    response.read.return_value = payload_bytes
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return Mock(return_value=context)


def _httperror(code: int) -> HTTPError:
    return HTTPError(url="https://exemplo", code=code, msg="erro", hdrs=None, fp=None)


def _chamar(opener):
    return fetch_com_retry(
        "https://exemplo",
        fonte=FonteDado.CEMADEN,
        opener=opener,
        user_agent="test/1.0",
    )


# ============================================================
# fetch_com_retry
# ============================================================


class TestFetchComRetry:
    def test_sucesso_primeira_tentativa(self, monkeypatch):
        payload = b'{"ok": true}'
        opener = _opener_de_payload(payload)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        assert _chamar(opener) == payload
        assert opener.call_count == 1

    def test_sucesso_apos_falhas_temporarias(self, monkeypatch):
        ctx_ok = _opener_de_payload(b"ok").return_value
        opener = Mock(side_effect=[URLError("timeout"), URLError("conexao"), ctx_ok])
        sleeps = []
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda s: sleeps.append(s))
        assert _chamar(opener) == b"ok"
        assert opener.call_count == 3
        assert len(sleeps) == 2

    def test_4xx_vira_falha_sem_retry(self, monkeypatch):
        opener = Mock(side_effect=_httperror(404))
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            _chamar(opener)
        assert isinstance(exc_info.value.original, HTTPError)
        assert exc_info.value.original.code == 404
        assert opener.call_count == 1

    def test_429_faz_retry(self, monkeypatch):
        ctx_ok = _opener_de_payload(b"ok").return_value
        opener = Mock(side_effect=[_httperror(429), ctx_ok])
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        assert _chamar(opener) == b"ok"
        assert opener.call_count == 2

    def test_5xx_faz_retry_e_esgota(self, monkeypatch):
        opener = Mock(side_effect=_httperror(503))
        sleeps = []
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda s: sleeps.append(s))
        with pytest.raises(FalhaDeColeta) as exc_info:
            _chamar(opener)
        assert exc_info.value.original.code == 503
        assert "HTTPError 503" in exc_info.value.causa
        assert opener.call_count == 4
        assert len(sleeps) == 3

    def test_esgota_tentativas_em_urlerror(self, monkeypatch):
        opener = Mock(side_effect=URLError("falha"))
        sleeps = []
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda s: sleeps.append(s))
        with pytest.raises(FalhaDeColeta) as exc_info:
            _chamar(opener)
        assert isinstance(exc_info.value.original, URLError)
        assert exc_info.value.fonte == FonteDado.CEMADEN
        assert opener.call_count == 4
        assert len(sleeps) == 3


# ============================================================
# parse_json
# ============================================================


class TestParseJson:
    def test_json_valido(self):
        assert parse_json(b'{"events": []}', fonte=FonteDado.EONET) == {"events": []}

    def test_unicode_invalido_vira_falha(self):
        with pytest.raises(FalhaDeColeta) as exc_info:
            parse_json(b"\xff\xfe invalido", fonte=FonteDado.EONET)
        assert isinstance(exc_info.value.original, UnicodeDecodeError)

    def test_json_invalido_vira_falha(self):
        with pytest.raises(FalhaDeColeta) as exc_info:
            parse_json(b"{ nao eh json", fonte=FonteDado.CEMADEN)
        assert isinstance(exc_info.value.original, json.JSONDecodeError)
