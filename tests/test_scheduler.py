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
    """Todos os jobs mantêm a config anti-pile-up; dispatcher a cada 30s e
    avisos (#153) a cada 30 min. Busca por id, não por posição."""
    scheduler_mock = Mock()
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
    ):
        scheduler.agendar_ingestao()

    jobs = {c.kwargs["id"]: c.kwargs for c in scheduler_mock.add_job.call_args_list}
    assert set(jobs) == {"ingestao", "avisos", "dispatcher"}
    for kwargs in jobs.values():
        assert kwargs["max_instances"] == 1
        assert kwargs["coalesce"] is True
        assert kwargs["misfire_grace_time"] == 60
    assert jobs["ingestao"]["minutes"] == 5
    assert jobs["dispatcher"]["seconds"] == 30
    assert jobs["avisos"]["minutes"] == 30


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
    scheduler_mock.shutdown.assert_called_once_with(wait=True)
    assert "aguardando rodada em andamento encerrar..." in caplog.text


def test_sigterm_aciona_shutdown_com_espera(caplog):
    """SIGTERM (systemctl stop/restart) deve drenar a rodada em andamento, não abortá-la."""
    scheduler_mock = Mock()
    with (
        patch("alertavida.scheduler.criar_banco"),
        patch("alertavida.scheduler.BlockingScheduler", return_value=scheduler_mock),
        patch("alertavida.scheduler.signal.signal") as signal_mock,
    ):
        caplog.set_level("INFO", logger="alertavida.scheduler")
        scheduler.agendar_ingestao()

    sinal, handler = signal_mock.call_args.args
    assert sinal == scheduler.signal.SIGTERM

    handler(scheduler.signal.SIGTERM, None)
    scheduler_mock.shutdown.assert_called_once_with(wait=True)
    assert "SIGTERM recebido, aguardando rodada em andamento encerrar..." in caplog.text


def test_rodar_rodada_usa_as_fontes_de_producao():
    """_rodar_rodada executa a ingestão com `bootstrap.fontes_producao()` (#131)."""
    mock_executar = MagicMock()
    mock_relatorio = MagicMock()
    mock_executar.return_value = mock_relatorio
    mock_formatar = MagicMock()
    fontes = [MagicMock(), MagicMock()]

    with (
        patch("alertavida.scheduler.executar_ingestao", mock_executar),
        patch("alertavida.scheduler.formatar_relatorio", mock_formatar),
        patch("alertavida.scheduler.fontes_producao", return_value=fontes),
    ):
        scheduler._rodar_rodada()

    mock_executar.assert_called_once_with(fontes)
    mock_formatar.assert_called_once_with(mock_relatorio)
