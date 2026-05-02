from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import alertavida.scheduler as scheduler


def test_agendamento_executa_imediatamente():
    scheduler_mock = Mock()
    with patch("alertavida.scheduler.BackgroundScheduler", return_value=scheduler_mock):
        with patch("alertavida.scheduler.datetime") as mock_datetime:
            with patch("alertavida.scheduler.time.sleep", side_effect=KeyboardInterrupt):
                with patch("alertavida.scheduler.sys.exit"):
                    now = datetime(2026, 4, 28, 18, 0, 0)
                    mock_datetime.now.return_value = now
                    scheduler.agendar_ingestao()

    ingestao_kwargs = scheduler_mock.add_job.call_args_list[0].kwargs
    assert ingestao_kwargs["next_run_time"] == now


def test_intervalo_correto():
    scheduler_mock = Mock()
    with patch("alertavida.scheduler.BackgroundScheduler", return_value=scheduler_mock):
        with patch("alertavida.scheduler.datetime") as mock_datetime:
            with patch("alertavida.scheduler.time.sleep", side_effect=KeyboardInterrupt):
                with patch("alertavida.scheduler.sys.exit"):
                    mock_datetime.now.return_value = datetime.now()
                    scheduler.agendar_ingestao()

    args = scheduler_mock.add_job.call_args_list[0].args
    kwargs = scheduler_mock.add_job.call_args_list[0].kwargs
    assert args[1] == "interval"
    assert kwargs["minutes"] == 5


def test_listener_continua_apos_erro(caplog):
    scheduler_mock = Mock()
    with patch("alertavida.scheduler.BackgroundScheduler", return_value=scheduler_mock):
        with patch("alertavida.scheduler.datetime") as mock_datetime:
            with patch("alertavida.scheduler.time.sleep", side_effect=KeyboardInterrupt):
                with patch("alertavida.scheduler.sys.exit"):
                    mock_datetime.now.return_value = datetime.now()
                    scheduler.agendar_ingestao()

    listener, mask = scheduler_mock.add_listener.call_args.args
    assert mask == scheduler.EVENT_JOB_ERROR

    evento = SimpleNamespace(exception=RuntimeError("falha simulada"))
    caplog.set_level("ERROR", logger="alertavida.scheduler")
    listener(evento)
    assert "[ERRO] Rodada de ingestão falhou: falha simulada" in caplog.text
    assert any(record.levelname == "ERROR" for record in caplog.records)


def test_keyboard_interrupt_encerra_limpo():
    scheduler_mock = Mock()
    with patch("alertavida.scheduler.BackgroundScheduler", return_value=scheduler_mock):
        with patch("alertavida.scheduler.time.sleep", side_effect=KeyboardInterrupt):
            with patch("alertavida.scheduler.sys.exit") as mock_exit:
                scheduler.agendar_ingestao()

    scheduler_mock.shutdown.assert_called_once_with(wait=False)
    mock_exit.assert_called_once_with(0)
