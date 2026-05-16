"""CemadenSource — DataSource concreta para o painel de alertas do CEMADEN.

Migra a lógica HTTP+retry+backoff, normalização de payload e mapeamento
para domínio Alerta que vivia em monitor.py (pré-B.1.b).

Design decisions registradas em CONTEXT.md §8:
- opener injetável via construtor (testes explícitos, sem patch por string)
- url injetável via construtor (futuro: staging, mock server)
- timeout_segundos injetável (futuro: ajuste por ambiente)
- keyword-only no __init__ (legibilidade no call site)
- Protocol local _RespostaHTTP (strict pelo contrato usado, não pela classe HTTPResponse concreta)

Invariantes do contrato CEMADEN:
- coletar() captura APENAS ValueError ao montar alerta. Bugs internos
  (TypeError, AttributeError, KeyError) propagam para diagnóstico.
- Falhas de rodada (URLError, HTTPError 5xx/408/429 após retries,
  socket.timeout, JSONDecodeError, UnicodeDecodeError) sobem como
  FalhaDeColeta com fonte=CEMADEN, causa legível, original encadeada.
- HTTPError 4xx (exceto 408/429) propaga imediatamente sem retry.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alertavida.domain import Alerta
from alertavida.domain.cobrade import mapear_cemaden
from alertavida.domain.enums import FonteClassificacao, FonteDado
from alertavida.domain.geographic import classificar_escopo
from alertavida.sources.base import DataSource, FalhaDeColeta, ResultadoColeta

URL_CEMADEN = "https://painelalertas.cemaden.gov.br/wsAlertas2"
TIMEOUT_SEGUNDOS: float = 30.0
MAX_TENTATIVAS: int = 4
BACKOFF_INICIAL: float = 2.0
USER_AGENT: str = "monitor-alertas/1.0"

logger = logging.getLogger(__name__)


class _RespostaHTTP(Protocol):
    """Contrato mínimo que CemadenSource usa de uma resposta HTTP.

    Strict pelo contrato usado, não pela classe http.client.HTTPResponse
    concreta. Fakes em teste só precisam implementar read() -> bytes.
    PEP 544.
    """

    def read(self) -> bytes: ...


Opener = Callable[[Request], AbstractContextManager[_RespostaHTTP]]


class CemadenSource(DataSource):
    """DataSource para o painel de alertas do CEMADEN.

    Construtor keyword-only por legibilidade no call site:
        CemadenSource()                          # produção
        CemadenSource(opener=fake)               # teste
        CemadenSource(url=staging_url)           # ambiente alternativo
    """

    def __init__(
        self,
        *,
        url: str = URL_CEMADEN,
        opener: Opener = urlopen,  # type: ignore[assignment]
        timeout_segundos: float = TIMEOUT_SEGUNDOS,
    ) -> None:
        self._url = url
        self._opener = opener
        self._timeout_segundos = timeout_segundos

    @property
    def fonte(self) -> FonteDado:
        return FonteDado.CEMADEN

    def coletar(self) -> ResultadoColeta:
        try:
            raw = self._fetch_com_retry()
        except (URLError, socket.timeout) as exc:
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa=f"rede esgotada após {MAX_TENTATIVAS} tentativas",
                original=exc,
            ) from exc
        except HTTPError as exc:
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa=f"HTTPError {exc.code}",
                original=exc,
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa="response não é UTF-8",
                original=exc,
            ) from exc
        except json.JSONDecodeError as exc:
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa="response não é JSON válido",
                original=exc,
            ) from exc

        itens_brutos = self._normalize_payload(payload)
        alertas: list[Alerta] = []
        descartados = 0
        for item in itens_brutos:
            try:
                alertas.append(self._montar_alerta(item))
            except ValueError:
                descartados += 1
            # Outras exceções (TypeError, AttributeError, KeyError) propagam: são bug.

        return ResultadoColeta(
            alertas=alertas,
            descartados=descartados,
            coletado_em=datetime.now(timezone.utc),
        )

    def _fetch_com_retry(self) -> bytes:
        ultima_excecao: Exception | None = None
        request = Request(self._url, headers={"User-Agent": USER_AGENT})

        for tentativa in range(MAX_TENTATIVAS):
            tentativa_humana = tentativa + 1
            logger.info("[Tentativa %s/%s]", tentativa_humana, MAX_TENTATIVAS)
            try:
                with self._opener(request, timeout=self._timeout_segundos) as response:  # type: ignore[call-arg]
                    return response.read()
            except HTTPError as exc:
                ultima_excecao = exc
                if 400 <= exc.code < 500 and exc.code not in (408, 429):
                    raise
            except (URLError, socket.timeout) as exc:
                ultima_excecao = exc

            if tentativa_humana < MAX_TENTATIVAS:
                espera = BACKOFF_INICIAL * (2**tentativa)
                logger.warning("Aguardando %gs antes da próxima tentativa...", espera)
                time.sleep(espera)

        assert ultima_excecao is not None
        raise ultima_excecao

    def _normalize_payload(self, payload: object) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("alertas", "data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _montar_alerta(self, item: dict) -> Alerta:
        """Converte item bruto do CEMADEN em Alerta de domínio.

        Levanta ValueError se item não tiver campos obrigatórios.
        Captura em coletar() conta como descartado; bugs internos
        (TypeError etc.) propagam.
        """
        if not isinstance(item, dict):
            raise ValueError(f"item deve ser dict, recebido {type(item).__name__}")
        alerta = Alerta.from_dict(item, fonte=self.fonte)
        escopo = classificar_escopo(alerta.coordenadas)

        tipo_evento_bruto = item.get("tipoevento") or ""
        cobrade = mapear_cemaden(tipo_evento_bruto)
        if cobrade is not None:
            fonte_classificacao = FonteClassificacao.MAPEADA_POR_NOME
        else:
            fonte_classificacao = FonteClassificacao.INDETERMINADA

        return alerta.model_copy(update={
            "escopo_geografico": escopo,
            "cobrade_codigo": cobrade,
            "fonte_classificacao": fonte_classificacao,
        })
