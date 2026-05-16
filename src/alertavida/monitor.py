import logging
import os
import sys
from datetime import datetime

from alertavida.database import (
    aplicar_resultado_deteccao,
    buscar_snapshots_ativos,
    criar_banco,
)
from alertavida.domain import Alerta
from alertavida.domain.detector import detectar_mudancas
from alertavida.sources import FalhaDeColeta
from alertavida.sources.cemaden import CemadenSource

if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


logger = logging.getLogger(__name__)


def executar_ingestao():
    criar_banco()
    source = CemadenSource()
    try:
        resultado = source.coletar()
    except FalhaDeColeta as exc:
        logger.error("Falha na coleta %s: %s", exc.fonte.value, exc.causa)
        sys.exit(1)

    alertas_validos: dict[str, Alerta] = {a.cod_alerta: a for a in resultado.alertas}
    descartados = resultado.descartados
    total_recebido = len(resultado.alertas) + descartados

    snapshots = buscar_snapshots_ativos(source.fonte)
    resultado_det = detectar_mudancas(list(alertas_validos.values()), snapshots)

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
        aplicar_resultado_deteccao(resultado_det, alertas_validos, agora)
    except Exception:  # noqa: BLE001 - proteção do ciclo de ingestão
        erros = len(alertas_validos)
        logger.exception("Falha na transação do banco")
        novos = atualizados = inalterados = 0
    else:
        novos = sum(1 for e in resultado_det.eventos if e.tipo == "AlertaCriado")
        atualizados = sum(1 for e in resultado_det.eventos if e.tipo == "AlertaAtualizado")
        inalterados = len(resultado_det.codigos_vistos) - novos - atualizados

    resolvidos = sum(1 for e in resultado_det.eventos if e.tipo == "AlertaResolvido")
    ausentes = len(resultado_det.codigos_ausentes)

    if not total_recebido:
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
