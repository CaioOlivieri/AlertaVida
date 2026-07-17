"""Testes do transporte HTTP compartilhado — sources/_http.py.

Consolida os testes de retry/backoff que antes viviam duplicados em
test_cemaden.py e test_nasa_eonet.py (uma classe TestFetchComRetry em cada).
"""

import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from alertavida.domain.enums import FonteDado
from alertavida.sources import FalhaDeColeta
from alertavida.sources._http import (
    _RedirectHTTPSObrigatorioHandler,
    fetch_com_retry,
    opener_padrao,
    parse_json,
)


def _opener_de_payload(payload_bytes: bytes):
    """Opener fake que retorna o payload dado em todas as chamadas."""
    response = Mock()
    response.read.return_value = payload_bytes
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return Mock(return_value=context)


def _opener_de_payload_truncavel(payload_bytes: bytes):
    """Opener fake cujo read(n) recorta o payload, como http.client.HTTPResponse.

    Necessário para testar o cap de tamanho: um fake que ignora `n` (como
    `_opener_de_payload`) nunca provaria que fetch_com_retry passa o limite
    adiante em vez de bufferizar a resposta inteira.
    """
    response = Mock()
    response.read = Mock(side_effect=lambda n=-1: payload_bytes if n < 0 else payload_bytes[:n])
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return Mock(return_value=context)


def _httperror(code: int) -> HTTPError:
    return HTTPError(url="https://exemplo", code=code, msg="erro", hdrs=None, fp=None)


def _chamar(opener, **kwargs):
    return fetch_com_retry(
        "https://exemplo",
        fonte=FonteDado.CEMADEN,
        opener=opener,
        user_agent="test/1.0",
        **kwargs,
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

    def test_resposta_acima_do_limite_falha_sem_retry(self, monkeypatch):
        """Response maior que max_resposta_bytes vira FalhaDeColeta imediata.

        O fake de opener honra o argumento de read(n) (como http.client.
        HTTPResponse.read(amt) faz), provando que fetch_com_retry lê apenas
        limite+1 bytes em vez de bufferizar o corpo inteiro.
        """
        payload = b"x" * 15
        opener = _opener_de_payload_truncavel(payload)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            _chamar(opener, max_resposta_bytes=10)
        assert "10 bytes" in exc_info.value.causa
        assert opener.call_count == 1
        response = opener.return_value.__enter__.return_value
        response.read.assert_called_once_with(11)

    def test_resposta_dentro_do_limite_sucede(self, monkeypatch):
        payload = b"x" * 10
        opener = _opener_de_payload_truncavel(payload)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        assert _chamar(opener, max_resposta_bytes=10) == payload
        assert opener.call_count == 1

    def test_redirect_downgrade_vira_falha_sem_retry(self, monkeypatch):
        """Simula o HTTPError que _RedirectHTTPSObrigatorioHandler levanta.

        302 não está em {5xx, 408, 429}, então falha imediatamente — sem os
        4 ciclos de retry que o código pré-#39 faria (código 3xx caía no
        `else` implícito da checagem antiga, só falhando após esgotar).
        """
        erro = HTTPError(
            url="http://exemplo.com/malicioso",
            code=302,
            msg="redirect para esquema não-https recusado",
            hdrs=None,
            fp=None,
        )
        opener = Mock(side_effect=erro)
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        with pytest.raises(FalhaDeColeta) as exc_info:
            _chamar(opener)
        assert exc_info.value.original is erro
        assert opener.call_count == 1


# ============================================================
# _RedirectHTTPSObrigatorioHandler / opener_padrao
# ============================================================


class TestRedirectHTTPSObrigatorioHandler:
    def test_recusa_redirect_para_http(self):
        handler = _RedirectHTTPSObrigatorioHandler()
        req = Request("https://exemplo.com/original")
        with pytest.raises(HTTPError) as exc_info:
            handler.redirect_request(
                req, None, 302, "Found", None, "http://exemplo.com/malicioso"
            )
        assert exc_info.value.code == 302
        assert "http://exemplo.com/malicioso" in str(exc_info.value)

    def test_permite_redirect_https_para_https(self):
        handler = _RedirectHTTPSObrigatorioHandler()
        req = Request("https://exemplo.com/original")
        nova = handler.redirect_request(
            req, None, 302, "Found", None, "https://exemplo.com/novo"
        )
        assert nova is not None
        assert nova.full_url == "https://exemplo.com/novo"

    def test_opener_padrao_usa_o_handler_https_obrigatorio(self):
        director = opener_padrao.__self__  # type: ignore[attr-defined]
        assert any(
            isinstance(h, _RedirectHTTPSObrigatorioHandler) for h in director.handlers
        )


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
