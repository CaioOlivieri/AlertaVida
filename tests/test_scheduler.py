from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import alertavida.scheduler as scheduler


def test_agendamento_executa_imediatamente():
    scheduler_mock = Mock()
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
        patch("alertavida.scheduler.datetime") as mock_datetime,
    ):
        now = datetime(2026, 4, 28, 18, 0, 0)
        mock_datetime.now.return_value = now
        scheduler.agendar_ingestao()

    ingestao_kwargs = scheduler_mock.add_job.call_args_list[0].kwargs
    assert ingestao_kwargs["next_run_time"] == now


def test_intervalo_correto():
    scheduler_mock = Mock()
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
    ):
        scheduler.agendar_ingestao()

    args = scheduler_mock.add_job.call_args_list[0].args
    kwargs = scheduler_mock.add_job.call_args_list[0].kwargs
    assert args[1] == "interval"
    assert kwargs["minutes"] == 5


def test_configuracao_dos_jobs():
    """Ambos os jobs mantêm a config anti-pile-up e o dispatcher roda a cada 30s."""
    scheduler_mock = Mock()
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
    ):
        scheduler.agendar_ingestao()

    ingestao_kwargs = scheduler_mock.add_job.call_args_list[0].kwargs
    assert ingestao_kwargs["id"] == "ingestao"
    assert ingestao_kwargs["max_instances"] == 1
    assert ingestao_kwargs["coalesce"] is True
    assert ingestao_kwargs["misfire_grace_time"] == 60

    dispatcher_kwargs = scheduler_mock.add_job.call_args_list[1].kwargs
    assert dispatcher_kwargs["id"] == "dispatcher"
    assert dispatcher_kwargs["seconds"] == 30
    assert dispatcher_kwargs["max_instances"] == 1
    assert dispatcher_kwargs["coalesce"] is True
    assert dispatcher_kwargs["misfire_grace_time"] == 60


def test_listener_continua_apos_erro(caplog):
    scheduler_mock = Mock()
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
    ):
        scheduler.agendar_ingestao()

    listener, mask = scheduler_mock.add_listener.call_args.args
    assert mask == scheduler.EVENT_JOB_ERROR

    evento = SimpleNamespace(exception=RuntimeError("falha simulada"))
    caplog.set_level("ERROR", logger="alertavida.scheduler")
    listener(evento)
    assert "[ERRO] Rodada de ingestão falhou: falha simulada" in caplog.text
    assert any(record.levelname == "ERROR" for record in caplog.records)


def test_keyboard_interrupt_encerra_limpo(caplog):
    scheduler_mock = Mock()
    scheduler_mock.start.side_effect = KeyboardInterrupt
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
    ):
        caplog.set_level("INFO", logger="alertavida.scheduler")
        scheduler.agendar_ingestao()

    scheduler_mock.start.assert_called_once_with()
    scheduler_mock.shutdown.assert_called_once_with(wait=False)
    assert "Scheduler encerrado pelo usuário." in caplog.text


def test_rodar_rodada_chama_ambas_as_fontes():
    """_rodar_rodada deve executar ingestão com CemadenSource e NasaEonetSource."""
    mock_executar = MagicMock()
    mock_relatorio = MagicMock()
    mock_executar.return_value = mock_relatorio
    mock_formatar = MagicMock()
    mock_cemaden = MagicMock()
    mock_nasa = MagicMock()

    with (
        patch("alertavida.scheduler.executar_ingestao", mock_executar),
        patch("alertavida.scheduler.formatar_relatorio", mock_formatar),
        patch("alertavida.scheduler.CemadenSource", mock_cemaden),
        patch("alertavida.scheduler.NasaEonetSource", mock_nasa),
    ):
        scheduler._rodar_rodada()

    mock_cemaden.assert_called_once()
    mock_nasa.assert_called_once()
    mock_executar.assert_called_once_with(
        [mock_cemaden.return_value, mock_nasa.return_value]
    )
    mock_formatar.assert_called_once_with(mock_relatorio)
