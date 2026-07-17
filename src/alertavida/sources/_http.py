"""Transporte HTTP compartilhado entre DataSources — Camada 4 (consolidação C.x).

Antes desta extração, CemadenSource e NasaEonetSource duplicavam ~50 linhas
idênticas de retry/backoff e parsing de JSON. Centralizar aqui garante uma única
implementação da política de resiliência (invariantes 3, 19, 20, 24, 25):

- retry apenas em 5xx / 408 / 429 / URLError / socket.timeout;
- HTTPError fora desse conjunto (4xx exceto 408/429, e qualquer redirect
  recusado por opener_padrao) falha imediatamente, sem retry;
- response acima de MAX_RESPOSTA_BYTES falha imediatamente, sem retry;
- toda falha de transporte/parsing vira FalhaDeColeta(fonte=...) com a exceção
  original encadeada — nenhuma exceção crua de rede vaza para o orquestrador.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from contextlib import AbstractContextManager
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from alertavida.domain.enums import FonteDado
from alertavida.sources.base import FalhaDeColeta

TIMEOUT_SEGUNDOS: float = 30.0
MAX_TENTATIVAS: int = 4
BACKOFF_INICIAL: float = 2.0
MAX_RESPOSTA_BYTES: int = 20 * 1024 * 1024  # 20 MB

logger = logging.getLogger(__name__)


class RespostaHTTP(Protocol):
    """Contrato mínimo que as sources usam de uma resposta HTTP (read(n) -> bytes).

    Strict pelo contrato usado, não pela classe http.client.HTTPResponse
    concreta. Fakes em teste só precisam implementar read(). PEP 544.
    read(n) aceita um limite de bytes (invariante 24) — http.client.HTTPResponse
    já suporta read(amt), então não é um contrato novo, só o parâmetro que
    fetch_com_retry passa a usar.
    """

    def read(self, n: int = -1) -> bytes: ...


Opener = Callable[..., AbstractContextManager[RespostaHTTP]]


class _RedirectHTTPSObrigatorioHandler(HTTPRedirectHandler):
    """Recusa redirect para URL não-https (invariante 25).

    As duas fontes de produção são https; um redirect para http só pode vir de
    um servidor mal configurado ou de um atacante de rede forjando o downgrade
    para injetar alertas falsos em texto plano. Nenhum dos dois casos é
    legítimo, então a recusa vira falha imediata (via HTTPError, tratado como
    tal por fetch_com_retry) em vez de seguir o redirect.
    """

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        if not newurl.startswith("https://"):
            raise HTTPError(
                newurl,
                code,
                f"redirect para esquema não-https recusado: {newurl}",
                headers,
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


opener_padrao: Opener = build_opener(_RedirectHTTPSObrigatorioHandler).open  # type: ignore[assignment]


def fetch_com_retry(
    url: str,
    *,
    fonte: FonteDado,
    opener: Opener,
    user_agent: str,
    timeout_segundos: float = TIMEOUT_SEGUNDOS,
    max_tentativas: int = MAX_TENTATIVAS,
    backoff_inicial: float = BACKOFF_INICIAL,
    max_resposta_bytes: int = MAX_RESPOSTA_BYTES,
) -> bytes:
    """GET com retry/backoff exponencial. Levanta FalhaDeColeta ao esgotar.

    Retry apenas em 5xx / 408 / 429 / URLError / socket.timeout. Qualquer outro
    HTTPError (4xx exceto 408/429; redirect recusado por opener_padrao, que
    surge como HTTPError não-5xx) vira FalhaDeColeta imediatamente, sem retry.
    Response acima de max_resposta_bytes também vira FalhaDeColeta imediata,
    sem retry — corpo gigante não é falha transiente. Esgotadas as tentativas,
    a última exceção vira FalhaDeColeta com `original` encadeada.
    """
    request = Request(url, headers={"User-Agent": user_agent})
    ultima_excecao: Exception | None = None

    for tentativa in range(max_tentativas):
        tentativa_humana = tentativa + 1
        logger.info("[Tentativa %s/%s]", tentativa_humana, max_tentativas)
        try:
            with opener(request, timeout=timeout_segundos) as response:
                corpo = response.read(max_resposta_bytes + 1)
        except HTTPError as exc:
            ultima_excecao = exc
            if not (500 <= exc.code < 600 or exc.code in (408, 429)):
                raise FalhaDeColeta(
                    fonte=fonte, causa=f"HTTPError {exc.code}", original=exc
                ) from exc
        except (URLError, socket.timeout) as exc:
            ultima_excecao = exc
        else:
            if len(corpo) > max_resposta_bytes:
                raise FalhaDeColeta(
                    fonte=fonte,
                    causa=f"response excede o limite de {max_resposta_bytes} bytes",
                )
            return corpo

        if tentativa_humana < max_tentativas:
            espera = backoff_inicial * (2**tentativa)
            logger.warning("Aguardando %gs antes da próxima tentativa...", espera)
            time.sleep(espera)

    assert ultima_excecao is not None
    if isinstance(ultima_excecao, HTTPError):
        causa = f"HTTPError {ultima_excecao.code}"
    else:
        causa = f"rede esgotada após {max_tentativas} tentativas"
    raise FalhaDeColeta(fonte=fonte, causa=causa, original=ultima_excecao) from ultima_excecao


def parse_json(raw: bytes, *, fonte: FonteDado) -> object:
    """Decodifica UTF-8 + json.loads. Levanta FalhaDeColeta em falha de parsing."""
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise FalhaDeColeta(fonte=fonte, causa="response não é UTF-8", original=exc) from exc
    except json.JSONDecodeError as exc:
        raise FalhaDeColeta(fonte=fonte, causa="response não é JSON válido", original=exc) from exc
