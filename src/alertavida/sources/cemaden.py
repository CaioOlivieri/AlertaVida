"""CemadenSource — DataSource concreta para o painel de alertas do CEMADEN.

Migra a lógica de normalização de payload e mapeamento para domínio Alerta que
vivia em monitor.py (pré-B.1.b). O transporte HTTP (retry/backoff) e o parsing
de JSON são compartilhados via `sources/_http.py`.

Design decisions registradas em wiki/decisions/decision-record.md:
- opener injetável via construtor (testes explícitos, sem patch por string)
- url injetável via construtor (futuro: staging, mock server)
- timeout_segundos injetável (futuro: ajuste por ambiente)
- keyword-only no __init__ (legibilidade no call site)

Invariantes do contrato CEMADEN:
- coletar() captura APENAS ValueError ao montar alerta. Bugs internos
  (TypeError, AttributeError, KeyError) propagam para diagnóstico.
- Falhas de rodada (rede, HTTPError, JSON inválido) sobem como FalhaDeColeta
  com fonte=CEMADEN — geradas em sources/_http.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.request import urlopen

from alertavida.domain import Alerta
from alertavida.domain.cobrade import mapear_cemaden
from alertavida.domain.enums import FonteClassificacao, FonteDado, TipoEvento
from alertavida.domain.geographic import classificar_escopo
from alertavida.sources._http import (
    TIMEOUT_SEGUNDOS,
    Opener,
    fetch_com_retry,
    parse_json,
)
from alertavida.sources.base import DataSource, FalhaDeColeta, ResultadoColeta

URL_CEMADEN = "https://painelalertas.cemaden.gov.br/wsAlertas2"
USER_AGENT: str = "monitor-alertas/1.0"


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
        raw = fetch_com_retry(
            self._url,
            fonte=self.fonte,
            opener=self._opener,
            user_agent=USER_AGENT,
            timeout_segundos=self._timeout_segundos,
        )
        payload = parse_json(raw, fonte=self.fonte)

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

    def _normalize_payload(self, payload: object) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("alertas", "data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa="formato de payload não reconhecido: dict sem chave "
                "conhecida ('alertas', 'data', 'items', 'results') contendo uma lista",
            )
        raise FalhaDeColeta(
            fonte=self.fonte,
            causa=f"formato de payload inesperado: esperado list ou dict, "
            f"recebido {type(payload).__name__}",
        )

    def _montar_alerta(self, item: dict) -> Alerta:
        """Converte item bruto do CEMADEN em Alerta de domínio.

        Levanta ValueError se item não tiver campos obrigatórios. Captura em
        coletar() conta como descartado; bugs internos (TypeError etc.) propagam.
        """
        if not isinstance(item, dict):
            raise ValueError(f"item deve ser dict, recebido {type(item).__name__}")
        alerta = Alerta.from_dict(item, fonte=self.fonte)
        escopo = classificar_escopo(alerta.coordenadas)

        categoria = self._categoria_do_evento(item)
        if categoria:
            tipo_evento = TipoEvento.from_string(categoria)
            cobrade = mapear_cemaden(categoria)
        else:
            # Sem a chave real `evento`: preserva o que from_dict já resolveu
            # via seus próprios aliases (fallback defensivo). Sem `evento`,
            # não há categoria granular o bastante pra mapear COBRADE.
            tipo_evento = alerta.tipo_evento
            cobrade = None
        if cobrade is not None:
            fonte_classificacao = FonteClassificacao.MAPEADA_POR_NOME
        else:
            fonte_classificacao = FonteClassificacao.INDETERMINADA

        return alerta.model_copy(
            update={
                "tipo_evento": tipo_evento,
                "escopo_geografico": escopo,
                "cobrade_codigo": cobrade,
                "fonte_classificacao": fonte_classificacao,
            }
        )

    @staticmethod
    def _categoria_do_evento(item: dict) -> str:
        """Extrai a categoria bruta do campo `evento` do CEMADEN.

        O payload real entrega `evento` como string composta
        "<categoria> - <nível>" (ex.: "Risco Hidrológico - Moderado",
        confirmado em 475 itens reais de data/samples/cemaden_raw_*.json,
        issue #30). Corta no primeiro " - " e retorna só a categoria — é
        isso que `TipoEvento.from_string` e `mapear_cemaden` esperam.
        Retorna "" se `evento` estiver ausente ou vazio (cai em
        TipoEvento.INDETERMINADO / cobrade None, sem inventar).
        """
        evento_bruto = item.get("evento")
        if not isinstance(evento_bruto, str) or not evento_bruto.strip():
            return ""
        return evento_bruto.split(" - ", 1)[0].strip()
