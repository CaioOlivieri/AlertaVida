import json
import logging
import os
import socket
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alertavida.database import (
    aplicar_resultado_deteccao,
    buscar_snapshots_ativos,
    criar_banco,
)
from alertavida.domain import Alerta
from alertavida.domain.cobrade import mapear_cemaden
from alertavida.domain.detector import detectar_mudancas
from alertavida.domain.enums import FonteClassificacao
from alertavida.domain.geographic import classificar_escopo

if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"
FONTE_CEMADEN = "CEMADEN"
logger = logging.getLogger(__name__)


def montar_alerta(item: dict) -> Alerta:
    """Converte item bruto do CEMADEN em Alerta de domínio.

    Levanta ValueError se o item não tiver os campos obrigatórios.
    """
    if not isinstance(item, dict):
        raise ValueError(f"item deve ser dict, recebido {type(item).__name__}")
    alerta = Alerta.from_dict(item)
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


def normalize_alert_list(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("alertas", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    return []


def fetch_alertas_com_retry(
    url: str,
    max_tentativas: int = 4,
    backoff_inicial: float = 2.0,
) -> bytes:
    ultima_excecao = None
    request = Request(url, headers={"User-Agent": "monitor-alertas/1.0"})

    for tentativa in range(max_tentativas):
        tentativa_humana = tentativa + 1
        logger.info("[Tentativa %s/%s]", tentativa_humana, max_tentativas)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            ultima_excecao = exc
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                raise
        except (URLError, socket.timeout) as exc:
            ultima_excecao = exc

        if tentativa_humana < max_tentativas:
            espera = backoff_inicial * (2**tentativa)
            logger.warning("Aguardando %gs antes da próxima tentativa...", espera)
            time.sleep(espera)

    assert ultima_excecao is not None
    raise ultima_excecao


def executar_ingestao():
    criar_banco()
    try:
        raw = fetch_alertas_com_retry(URL)
    except (HTTPError, URLError, socket.timeout) as exc:
        logger.error("Erro ao consultar a API após múltiplas tentativas: %s", exc)
        sys.exit(1)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("Falha ao interpretar JSON: %s", exc)
        sys.exit(1)

    itens_brutos = normalize_alert_list(payload)
    total_recebido = len(itens_brutos)

    alertas_validos: dict[str, Alerta] = {}
    descartados = 0
    for item in itens_brutos:
        try:
            alerta = montar_alerta(item)
            alertas_validos[alerta.cod_alerta] = alerta
        except ValueError:
            descartados += 1

    snapshots = buscar_snapshots_ativos(FONTE_CEMADEN)
    resultado = detectar_mudancas(list(alertas_validos.values()), snapshots, FONTE_CEMADEN)

    agora = datetime.now().isoformat(timespec="seconds")
    erros = 0
    try:
        for alerta in alertas_validos.values():
            logger.debug(
                "Alerta %s: %s/%s — %s — %s",
                alerta.cod_alerta,
                alerta.municipio.nome if alerta.municipio else "?",
                alerta.municipio.uf if alerta.municipio else "?",
                alerta.tipo_evento,
                alerta.nivel_risco,
            )
        aplicar_resultado_deteccao(resultado, alertas_validos, FONTE_CEMADEN, agora)
    except Exception:  # noqa: BLE001 - proteção do ciclo de ingestão
        erros = len(alertas_validos)
        logger.exception("Falha na transação do banco")
        novos = atualizados = inalterados = 0
    else:
        novos = sum(1 for e in resultado.eventos if e.tipo == "AlertaCriado")
        atualizados = sum(1 for e in resultado.eventos if e.tipo == "AlertaAtualizado")
        inalterados = len(resultado.codigos_vistos) - novos - atualizados

    resolvidos = sum(1 for e in resultado.eventos if e.tipo == "AlertaResolvido")
    ausentes = len(resultado.codigos_ausentes)

    if not itens_brutos:
        logger.info("Nenhum alerta encontrado.")

    print()
    print("=== Resumo ===")
    print(f"Total recebido  : {total_recebido}")
    print(f"Novos           : {novos}")
    print(f"Atualizados     : {atualizados}")
    print(f"Inalterados     : {inalterados}")
    print(f"Descartados     : {descartados}")
    print(f"Erros           : {erros}")
    print(f"Ausentes (+1)   : {ausentes}")
    print(f"Resolvidos      : {resolvidos}")

    assert novos + atualizados + inalterados + descartados + erros == total_recebido, (
        f"Contadores inconsistentes: "
        f"{novos}+{atualizados}+{inalterados}+{descartados}+{erros} != {total_recebido}"
    )


main = executar_ingestao


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    executar_ingestao()
