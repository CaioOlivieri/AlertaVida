"""Testes do entrypoint manual `python -m alertavida.monitor`."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from alertavida.domain.enums import FonteDado
from alertavida.ingestion.orquestrador import RelatorioFonte, RelatorioIngestao
from alertavida.monitor import main


def test_main_executa_ingestao_e_imprime_relatorio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A função main deve orquestrar a criação do banco, ingestão e impressão."""
    # Arrange: relatório dummy para o mock de executar_ingestao
    mock_relatorio_fonte = RelatorioFonte(
        fonte=FonteDado.CEMADEN,
        coletados=5,
        novos=2,
        atualizados=1,
        inalterados=2,
        descartados=0,
        falha_coleta=False,
        coletado_em=datetime(2026, 5, 19, 15, 0, tzinfo=UTC),
        duracao_segundos=0.5,
    )
    dummy_report = RelatorioIngestao(
        por_fonte=(mock_relatorio_fonte,),
        agora=datetime(2026, 5, 19, 15, 0, tzinfo=UTC),
    )

    mock_criar_banco = MagicMock()
    mock_executar_ingestao = MagicMock(return_value=dummy_report)
    mock_print = MagicMock()
    fontes = [MagicMock(), MagicMock()]

    monkeypatch.setattr("alertavida.monitor.criar_banco", mock_criar_banco)
    monkeypatch.setattr("alertavida.monitor.executar_ingestao", mock_executar_ingestao)
    monkeypatch.setattr("builtins.print", mock_print)
    monkeypatch.setattr("alertavida.monitor.fontes_producao", lambda: fontes)

    # Act
    result = main()

    # Assert
    mock_criar_banco.assert_called_once()
    mock_executar_ingestao.assert_called_once_with(fontes)
    mock_print.assert_called_once()
    assert "CEMADEN: 5 coletados" in mock_print.call_args[0][0]
    assert "Total: 5 alertas" in mock_print.call_args[0][0]
    assert result == 0
