"""CemadenSource — DataSource concreta para o painel de alertas do CEMADEN.

Migra a lógica de normalização de payload e mapeamento para domínio Alerta que
vivia em monitor.py (pré-B.1.b). O transporte HTTP (retry/backoff), o parsing
de JSON e o skeleton de coletar() são compartilhados via
`HttpDataSource` (sources/_http.py, issue #20) — CemadenSource só implementa
o que é específico: `_normalize_payload` e `_montar_alerta`.

Design decisions registradas em wiki/decisions/decision-record.md:
- opener injetável via construtor (testes explícitos, sem patch por string)
- url injetável via construtor (futuro: staging, mock server)
- timeout_segundos injetável (futuro: ajuste por ambiente)
- keyword-only no __init__ (legibilidade no call site, herdado de HttpDataSource)

Invariantes do contrato CEMADEN:
- coletar() (em HttpDataSource) captura APENAS ValueError ao montar alerta.
  Bugs internos (TypeError, AttributeError, KeyError) propagam para diagnóstico.
- Falhas de rodada (rede, HTTPError, JSON inválido) sobem como FalhaDeColeta
  com fonte=CEMADEN — geradas em sources/_http.py.
"""

from __future__ import annotations

from alertavida.domain import Alerta
from alertavida.domain.cobrade import mapear_cemaden
from alertavida.domain.enums import FonteClassificacao, FonteDado, TipoEvento
from alertavida.domain.geographic import classificar_escopo
from alertavida.sources._http import HttpDataSource
from alertavida.sources.base import FalhaDeColeta

URL_CEMADEN = "https://painelalertas.cemaden.gov.br/wsAlertas2"


class CemadenSource(HttpDataSource):
    """DataSource para o painel de alertas do CEMADEN.

    Construtor keyword-only herdado de HttpDataSource:
        CemadenSource()                          # produção
        CemadenSource(opener=fake)               # teste
        CemadenSource(url=staging_url)           # ambiente alternativo
    """

    URL = URL_CEMADEN
    USER_AGENT = "monitor-alertas/1.0"

    @property
    def fonte(self) -> FonteDado:
        return FonteDado.CEMADEN

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

        Nota (issue #19): `Alerta.from_dict` só reconhece a chave real `evento`
        para tipo_evento — sem ela, já levanta ValueError antes desta função
        continuar. Por isso `categoria`/`tipo_evento`/`cobrade` abaixo não
        precisam de fallback: se chegamos aqui, `item["evento"]` existe e é
        não-vazio (o pior caso, sufixo sem categoria, já cai em INDETERMINADO/
        None sozinho — `_categoria_do_evento` e os mapeamentos tratam string
        vazia sem lançar).
        """
        if not isinstance(item, dict):
            raise ValueError(f"item deve ser dict, recebido {type(item).__name__}")
        alerta = Alerta.from_dict(item, fonte=self.fonte)
        escopo = classificar_escopo(alerta.coordenadas)

        categoria = self._categoria_do_evento(item)
        tipo_evento = TipoEvento.from_string(categoria)
        cobrade = mapear_cemaden(categoria)
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
