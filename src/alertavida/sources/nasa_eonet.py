"""NasaEonetSource — DataSource concreta para a NASA EONET v3.

EONET (Earth Observatory Natural Event Tracker) entrega eventos naturais
globais (incêndios, tempestades, vulcões, inundações). Camada 4 Partes C.1+C.2.

Compartilha o transporte HTTP (retry/backoff) e o parsing de JSON com
CemadenSource via `sources/_http.py`, mas constrói o Alerta DIRETAMENTE em vez
de usar Alerta.from_dict, porque o shape do payload v3 diverge do CEMADEN:

- Coordenadas vivem em geometry[].coordinates = [lon, lat] (ordem GeoJSON,
  aninhada). from_dict espera latitude/longitude escalares no topo.
- EONET NÃO fornece severidade → nivel_risco = INDETERMINADO. Inventar nível
  violaria a honestidade de dados (wiki/patterns/code-conventions.md).
- Tipo vem de categories[].id em inglês → mapeamento próprio
  CATEGORIA_EONET_PARA_TIPO (invariante 10: cada DataSource mapeia sua própria
  terminologia para os valores neutros de TipoEvento).
- Data vive em geometry[].date por fix; um evento tem 1..N fixes → usa o fix
  MAIS RECENTE (maior date) como posição/momento corrente do alerta.

Parte C.2 atribui cobrade_codigo via mapear_eonet, que retorna código COBRADE
para categorias EONET mapeadas. Categorias não mapeadas mantêm None /
FonteClassificacao.INDETERMINADA, respeitando o invariante atômico
(cobrade_codigo IS NULL ⇔ fonte_classificacao == INDETERMINADA).

Invariantes do contrato:
- coletar() captura APENAS ValueError ao montar cada evento. Bugs internos
  (TypeError, AttributeError, KeyError) propagam para diagnóstico.
- Falhas de rodada (rede, HTTPError, JSON inválido) sobem como FalhaDeColeta
  com fonte=EONET — geradas em sources/_http.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Final
from urllib.parse import urlencode

from pydantic import ValidationError

from alertavida.domain import Alerta
from alertavida.domain.cobrade import mapear_eonet
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import (
    FonteClassificacao,
    FonteDado,
    NivelRisco,
    TipoEvento,
)
from alertavida.domain.geographic import classificar_escopo
from alertavida.sources._http import (
    TIMEOUT_SEGUNDOS,
    Opener,
    fetch_com_retry,
    opener_padrao,
    parse_json,
)
from alertavida.sources.base import DataSource, FalhaDeColeta, ResultadoColeta

EONET_BASE_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
# Recorte de produção: apenas eventos abertos/ativos (decisão C.1). Eventos
# fechados são histórico, ruído para um sistema de alerta em tempo real.
EONET_PARAMS: Final[dict[str, str | int]] = {"status": "open", "limit": 500}
URL_EONET = f"{EONET_BASE_URL}?{urlencode(EONET_PARAMS)}"
USER_AGENT: str = "AlertaVida/1.0 (+https://github.com/CaioOlivieri/AlertaVida)"

# Mapeamento categoria EONET v3 → TipoEvento (grupo COBRADE neutro).
# Inclui apenas categorias cuja correspondência de GRUPO é inequívoca.
# Categoria fora deste dict cai em TipoEvento.INDETERMINADO — não inventar.
# O código COBRADE numérico é atribuído por mapear_eonet (C.2).
CATEGORIA_EONET_PARA_TIPO: Final[dict[str, TipoEvento]] = {
    "wildfires": TipoEvento.CLIMATOLOGICO,
    "floods": TipoEvento.HIDROLOGICO,
    "severeStorms": TipoEvento.METEOROLOGICO,
    "volcanoes": TipoEvento.GEOLOGICO,
    "landslides": TipoEvento.GEOLOGICO,
}


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
        opener: Opener = opener_padrao,
        timeout_segundos: float = TIMEOUT_SEGUNDOS,
    ) -> None:
        self._url = url
        self._opener = opener
        self._timeout_segundos = timeout_segundos

    @property
    def fonte(self) -> FonteDado:
        return FonteDado.EONET

    def coletar(self) -> ResultadoColeta:
        raw = fetch_com_retry(
            self._url,
            fonte=self.fonte,
            opener=self._opener,
            user_agent=USER_AGENT,
            timeout_segundos=self._timeout_segundos,
        )
        payload = parse_json(raw, fonte=self.fonte)

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

        Atribui cobrade_codigo via mapear_eonet (C.2) e fonte_classificacao
        como MAPEADA_POR_NOME se o mapeamento for conhecido, ou INDETERMINADA
        para categorias não mapeadas (invariante atômico respeitado).

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
        cobrade = mapear_eonet(categoria)
        fonte_classificacao = (
            FonteClassificacao.MAPEADA_POR_NOME
            if cobrade is not None
            else FonteClassificacao.INDETERMINADA
        )

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
            cobrade_codigo=cobrade,
            fonte_classificacao=fonte_classificacao,
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
