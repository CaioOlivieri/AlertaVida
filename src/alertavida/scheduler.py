import logging
import os
import sys
import time
from datetime import datetime

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

from alertavida.database import criar_banco
from alertavida.events import OutboxDispatcher, bus
from alertavida.ingestion.orquestrador import executar_ingestao
from alertavida.reporting import formatar_relatorio
from alertavida.sources.cemaden import CemadenSource
from alertavida.sources.nasa_eonet import NasaEonetSource

INTERVALO_MINUTOS = 5
logger = logging.getLogger(__name__)


def _on_job_error(event) -> None:
    if event.exception:
        logger.error("[ERRO] Rodada de ingestão falhou: %s", event.exception)


def _rodar_rodada() -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("[%s] Iniciando rodada de ingestão...", timestamp)
    relatorio = executar_ingestao([CemadenSource(), NasaEonetSource()])
    logger.info("Rodada concluída:\n%s", formatar_relatorio(relatorio))
    logger.info("Próxima rodada em %s minutos.", INTERVALO_MINUTOS)


def agendar_ingestao() -> None:
    criar_banco()
    scheduler = BackgroundScheduler()
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    kwargs_ingestao = {
        "minutes": INTERVALO_MINUTOS,
        "next_run_time": datetime.now(),
        "max_instances": 1,
        "coalesce": True,
        "misfire_grace_time": 60,
        "id": "ingestao",
    }
    scheduler.add_job(
        _rodar_rodada,
        "interval",
        **kwargs_ingestao,
    )
    scheduler.add_job(
        OutboxDispatcher(bus).processar_pendentes,
        "interval",
        seconds=30,
        id="dispatcher",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    logger.info(
        f"Scheduler iniciado. Executando ingestão a cada {INTERVALO_MINUTOS} minutos. "
        "Pressione Ctrl+C para encerrar."
    )
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler encerrado pelo usuário.")
        scheduler.shutdown(wait=False)
        sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    agendar_ingestao()
