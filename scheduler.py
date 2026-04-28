from datetime import datetime
import sys
import time

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

from monitor import executar_ingestao

INTERVALO_MINUTOS = 5


def _on_job_error(event) -> None:
    if event.exception:
        print(f"[ERRO] Rodada de ingestão falhou: {event.exception}")


def _rodar_rodada() -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Iniciando rodada de ingestão...")
    executar_ingestao()
    print(f"Próxima rodada em {INTERVALO_MINUTOS} minutos.")


def agendar_ingestao() -> None:
    scheduler = BackgroundScheduler()
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    scheduler.add_job(
        _rodar_rodada,
        "interval",
        minutes=INTERVALO_MINUTOS,
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    print(
        f"Scheduler iniciado. Executando ingestão a cada {INTERVALO_MINUTOS} minutos. "
        "Pressione Ctrl+C para encerrar."
    )
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler encerrado pelo usuário.")
        scheduler.shutdown(wait=False)
        sys.exit(0)


if __name__ == "__main__":
    agendar_ingestao()
