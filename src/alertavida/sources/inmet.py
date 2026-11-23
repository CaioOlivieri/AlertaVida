"""InmetSource — avisos meteorológicos do INMET (issue #153).

Não é uma `DataSource`: não produz `Alerta`s. Produz `AvisoMeteorologico`s,
contexto para incidentes (ver `domain/aviso.py`). Reusa o transporte de
`sources/_http.py` — retry/backoff, teto de tamanho, redirect só para HTTPS,
toda falha virando `FalhaDeColeta`.

Endpoint: `https://apiprevmet3.inmet.gov.br/avisos/ativos` — backend do
portal de avisos, **não uma API documentada** e sem licença publicada
(wiki/raw/analise-inmet-2026-11-23.md). O teste de contrato diário
(`tests/test_contrato_inmet.py`) é o aviso de mudança de formato.

Duas armadilhas medidas, tratadas aqui:

- **Fuso.** `data_inicio` vem como `"2026-11-24T00:00:00.000Z"`, mas o CAP
  do mesmo aviso diz `onset 2026-11-24T00:00:00-03:00`: o `Z` é horário de
  Brasília rotulado errado (mesma armadilha da #127). Usamos `inicio`/`fim`
  (`"2026-11-24 00:00"`, sem fuso) lidos como UTC-3 — e nunca o `Z`.
- **Peso.** Cada aviso carrega um ícone PNG em base64 — a maior parte dos
  ~280 KB. O campo é ignorado.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Final

from pydantic import ValidationError

from alertavida.domain.aviso import AvisoMeteorologico, SeveridadeAviso
from alertavida.domain.enums import FonteDado
from alertavida.sources._http import (
    TIMEOUT_SEGUNDOS,
    Opener,
    fetch_com_retry,
    opener_padrao,
    parse_json,
)
from alertavida.sources.base import FalhaDeColeta

URL_INMET_AVISOS: Final[str] = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
USER_AGENT_INMET: Final[str] = "AlertaVida/1.0 (+https://github.com/CaioOlivieri/AlertaVida)"
# Brasília, sem horário de verão desde 2019 — mesma constante que o CEMADEN
# usa (#127), declarada aqui porque o fuso é da fonte.
FUSO_INMET: Final[timezone] = timezone(timedelta(hours=-3))
GRUPOS_DO_ENVELOPE: Final[tuple[str, ...]] = ("hoje", "futuro")

logger = logging.getLogger(__name__)


def _instante_local(valor: object) -> datetime:
    """`"2026-11-24 00:00"` (horário de Brasília) -> datetime aware em UTC."""
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"instante ausente: {valor!r}")
    local = datetime.strptime(valor.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=FUSO_INMET)
    return local.astimezone(timezone.utc)


def _codigos_ibge(valor: object) -> frozenset[int]:
    if not isinstance(valor, str):
        raise ValueError("geocodes ausente")
    return frozenset(int(parte) for parte in valor.split(",") if parte.strip())


def montar_aviso(item: dict) -> AvisoMeteorologico:
    """Item bruto do JSON -> AvisoMeteorologico. ValueError descarta o item."""
    if not isinstance(item, dict):
        raise ValueError(f"item deve ser dict, recebido {type(item).__name__}")
    try:
        return AvisoMeteorologico(
            codigo_cap=str(item["codigo"]),
            id_aviso=int(item["id_aviso"]),
            id_sequencia=int(item["id_sequencia"]),
            evento=str(item["descricao"]).strip(),
            severidade=SeveridadeAviso.from_inmet(item["severidade"]),
            inicio=_instante_local(item["inicio"]),
            fim=_instante_local(item["fim"]),
            codigos_ibge=_codigos_ibge(item["geocodes"]),
            encerrado=bool(item.get("encerrado", False)),
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"campo ausente ou malformado: {exc}") from exc
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


class InmetSource:
    """Coletor de avisos ativos (hoje + futuro) do INMET."""

    fonte: Final = FonteDado.INMET

    def __init__(
        self,
        *,
        url: str = URL_INMET_AVISOS,
        opener: Opener = opener_padrao,
        timeout_segundos: float = TIMEOUT_SEGUNDOS,
    ) -> None:
        self._url = url
        self._opener = opener
        self._timeout_segundos = timeout_segundos

    def coletar(self) -> tuple[list[AvisoMeteorologico], int]:
        """(avisos válidos, descartados). Falha de rodada -> FalhaDeColeta."""
        raw = fetch_com_retry(
            self._url,
            fonte=self.fonte,
            opener=self._opener,
            user_agent=USER_AGENT_INMET,
            timeout_segundos=self._timeout_segundos,
        )
        payload = parse_json(raw, fonte=self.fonte)
        if not isinstance(payload, dict) or not all(
            isinstance(payload.get(g), list) for g in GRUPOS_DO_ENVELOPE
        ):
            raise FalhaDeColeta(
                fonte=self.fonte,
                causa="formato de payload não reconhecido: esperado dict com listas "
                f"{list(GRUPOS_DO_ENVELOPE)}",
            )
        avisos: dict[str, AvisoMeteorologico] = {}
        descartados = 0
        for grupo in GRUPOS_DO_ENVELOPE:
            for item in payload[grupo]:
                try:
                    aviso = montar_aviso(item)
                except ValueError as exc:
                    descartados += 1
                    logger.warning("Aviso INMET descartado: %s", exc)
                    continue
                avisos[aviso.codigo_cap] = aviso  # o mesmo aviso pode vir em hoje e futuro
        return list(avisos.values()), descartados
