"""NasaEonetSource — DataSource concreta para a NASA EONET v3.

EONET (Earth Observatory Natural Event Tracker) entrega eventos naturais
globais (incêndios, tempestades, vulcões, inundações). Camada 4 Parte C.1.

Segue o mesmo padrão de CemadenSource (HTTP + retry/backoff + normalização +
mapeamento para domínio), mas constrói o Alerta DIRETAMENTE em vez de usar
Alerta.from_dict, porque o shape do payload v3 diverge do CEMADEN:

- Coordenadas vivem em geometry[].coordinates = [lon, lat] (ordem GeoJSON,
  aninhada). from_dict espera latitude/longitude escalares no topo.
- EONET NÃO fornece severidade → nivel_risco = INDETERMINADO. Inventar nível
  violaria a honestidade de dados (wiki/patterns/code-conventions.md).
- Tipo vem de categories[].id em inglês → mapeamento próprio
  CATEGORIA_EONET_PARA_TIPO (invariante 10: cada DataSource mapeia sua própria
  terminologia para os valores neutros de TipoEvento).
- Data vive em geometry[].date por fix; um evento tem 1..N fixes → usa o fix
  MAIS RECENTE (maior date) como posição/momento corrente do alerta.

Parte C.1 NÃO atribui cobrade_codigo (fica None / FonteClassificacao
INDETERMINADA). O código COBRADE numérico exige bater na tabela oficial da
Defesa Civil e é trabalho da Parte C.2. O invariante atômico
(cobrade_codigo IS NULL ⇔ fonte_classificacao == INDETERMINADA) é respeitado.

Invariantes do contrato (espelham CemadenSource):
- coletar() captura APENAS ValueError ao montar cada evento. Bugs internos
  (TypeError, AttributeError, KeyError) propagam para diagnóstico.
- Falhas de rodada (URLError, HTTPError 5xx/408/429 após retries,
  socket.timeout, JSONDecodeError, UnicodeDecodeError) sobem como
  FalhaDeColeta com fonte=EONET, causa legível, original encadeada.
- HTTPError 4xx (exceto 408/429) propaga imediatamente sem retry.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Any, Callable, Final, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError

from alertavida.domain import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import (
    FonteClassificacao,
    FonteDado,
    NivelRisco,
    TipoEvento,
)
from alertavida.domain.geographic import classificar_escopo
from alertavida.sources.base import DataSource, FalhaDeColeta, ResultadoColeta

EONET_BASE_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
# Recorte de produção: apenas eventos abertos/ativos (decisão C.1). Eventos
# fechados são histórico, ruído para um sistema de alerta em tempo real.
EONET_PARAMS: Final[dict[str, str | int]] = {"status": "open", "limit": 500}
URL_EONET = f"{EONET_BASE_URL}?{urlencode(EONET_PARAMS)}"
TIMEOUT_SEGUNDOS: float = 30.0
MAX_TENTATIVAS: int = 4
BACKOFF_INICIAL: float = 2.0
USER_AGENT: str = "AlertaVida/1.0 (+https://github.com/CaioOlivieri/AlertaVida)"

logger = logging.getLogger(__name__)

# Mapeamento categoria EONET v3 → TipoEvento (grupo COBRADE neutro).
# Inclui apenas categorias cuja correspondência de GRUPO é inequívoca, espelhando
# a decisão registrada em wiki/projects/layer-4-multi-source-ingestion.md (C.2).
# Categoria fora deste dict cai em TipoEvento.INDETERMINADO — não inventar.
# O código COBRADE numérico (1.x.y.0.0) é trabalho da Parte C.2.
CATEGORIA_EONET_PARA_TIPO: Final[dict[str, TipoEvento]] = {
    "wildfires": TipoEvento.CLIMATOLOGICO,
    "floods": TipoEvento.HIDROLOGICO,
    "severeStorms": TipoEvento.METEOROLOGICO,
    "volcanoes": TipoEvento.GEOLOGICO,
    "landslides": TipoEvento.GEOLOGICO,
}


class _RespostaHTTP(Protocol):
    """Contrato mínimo que NasaEonetSource usa de uma resposta HTTP.

    Strict pelo contrato usado (read() -> bytes), não pela classe
    http.client.HTTPResponse concreta. Fakes em teste só implementam read().
    PEP 544.
    """

    def read(self) -> bytes: ...


Opener = Callable[..., AbstractContextManager[_RespostaHTTP]]


class NasaEonetSource(DataSource):
    """DataSource para a API de eventos da NASA EONET v3.

    Construtor keyword-only por legibilidade no call site:
        NasaEonetSource()                # produção
        NasaEonetSource(opener=fake)     # teste
        NasaEonetSource(url=staging_url)  # ambiente alternativo
    """

    def __init__(
        self,
        *,
        url: str = URL_EONET,
        opener: Opener = urlopen,  # type: ignore[assignment]
        timeout_segundos: float = TIMEOUT_SEGUNDOS,
    ) -> None:
        self._url = url
        self._opener = opener
        self._timeout_segundos = timeout_segundos

    @property
    def fonte(self) -> FonteDado:
        return FonteDado.EONET

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

        eventos = self._normalize_payload(payload)
        alertas: list[Alerta] = []
        descartados = 0
        for evento in eventos:
            try:
                alertas.append(self._montar_alerta(evento))
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
        """Extrai a lista events[] do envelope EONET v3.

        Levanta FalhaDeColeta para formato desconhecido (invariante 23): um
        dict sem 'events' contendo lista, ou um payload que não é dict, não
        deve silenciosamente retornar lista vazia.
        """
        if isinstance(payload, dict):
            eventos = payload.get("events")
            if isinstance(eventos, list):
                return eventos
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa="formato de payload não reconhecido: dict sem chave "
                "'events' contendo uma lista",
            )
        raise FalhaDeColeta(
            fonte=self.fonte,
            causa=f"formato de payload inesperado: esperado dict com 'events', "
            f"recebido {type(payload).__name__}",
        )

    def _montar_alerta(self, evento: dict) -> Alerta:
        """Converte um evento bruto da EONET em Alerta de domínio.

        Levanta ValueError se o evento não tiver os campos mínimos (id,
        geometry Point com coordenadas e data válidas). Captura em coletar()
        conta como descartado; bugs internos (TypeError etc.) propagam.
        """
        if not isinstance(evento, dict):
            raise ValueError(f"evento deve ser dict, recebido {type(evento).__name__}")

        cod_raw = evento.get("id")
        if cod_raw is None or not str(cod_raw).strip():
            raise ValueError("evento EONET sem id")
        cod_alerta = str(cod_raw).strip()

        categoria = self._categoria_principal(evento)
        tipo_evento = CATEGORIA_EONET_PARA_TIPO.get(categoria, TipoEvento.INDETERMINADO)

        longitude, latitude, data_criacao = self._fix_mais_recente(evento.get("geometry"))
        try:
            coordenadas = Coordenadas(latitude=latitude, longitude=longitude)
        except ValidationError:
            raise ValueError("coordenadas EONET fora de faixa válida") from None

        escopo = classificar_escopo(coordenadas)
        titulo = evento.get("title")

        return Alerta(
            cod_alerta=cod_alerta,
            fonte=self.fonte,
            tipo_evento=tipo_evento,
            nivel_risco=NivelRisco.INDETERMINADO,
            coordenadas=coordenadas,
            municipio=None,
            escopo_geografico=escopo,
            data_criacao=data_criacao,
            ult_atualizacao=None,
            descricao=None if titulo is None else str(titulo),
            cobrade_codigo=None,
            fonte_classificacao=FonteClassificacao.INDETERMINADA,
        )

    @staticmethod
    def _categoria_principal(evento: dict) -> str:
        """Retorna o id da primeira categoria do evento, ou '' se ausente."""
        categorias = evento.get("categories")
        if isinstance(categorias, list):
            for cat in categorias:
                if isinstance(cat, dict):
                    cat_id = cat.get("id")
                    if cat_id is not None and str(cat_id).strip():
                        return str(cat_id).strip()
        return ""

    @staticmethod
    def _fix_mais_recente(geometry: Any) -> tuple[float, float, datetime]:
        """Seleciona o fix Point mais recente (maior date) de geometry[].

        Retorna (longitude, latitude, data) — coordinates em ordem GeoJSON.
        Levanta ValueError se geometry estiver vazia/ausente ou não tiver
        nenhum fix Point com coordenadas e data válidas (evento descartado).

        A seleção é por DATA, não por posição na lista: a API não garante
        ordenação cronológica dos fixes.
        """
        if not isinstance(geometry, list) or not geometry:
            raise ValueError("evento EONET sem geometry")

        melhor: tuple[datetime, float, float] | None = None
        for fix in geometry:
            if not isinstance(fix, dict) or fix.get("type") != "Point":
                continue
            coords = fix.get("coordinates")
            if not isinstance(coords, list) or len(coords) < 2:
                continue
            data_raw = fix.get("date")
            if data_raw is None or not str(data_raw).strip():
                continue
            try:
                data = datetime.fromisoformat(str(data_raw))
            except ValueError:
                continue
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)
            try:
                longitude = float(coords[0])
                latitude = float(coords[1])
            except (TypeError, ValueError):
                continue
            if melhor is None or data > melhor[0]:
                melhor = (data, longitude, latitude)

        if melhor is None:
            raise ValueError("evento EONET sem fix Point válido")
        data, longitude, latitude = melhor
        return longitude, latitude, data
