"""Testes do entrypoint manual `python -m alertavida.monitor`.

Foca em `_formatar_relatorio` (função pura). A orquestração real é
testada em `tests/ingestion/test_orquestrador.py`.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from alertavida.domain.enums import FonteDado
from alertavida.ingestion.orquestrador import RelatorioFonte, RelatorioIngestao
from alertavida.monitor import _formatar_relatorio, main


def test_formatar_relatorio_com_sucesso_inclui_contadores() -> None:
    """Relatório formatado de fonte bem-sucedida lista todos os contadores."""
    rf = RelatorioFonte(
        fonte=FonteDado.CEMADEN,
        coletados=15,
        novos=3,
        atualizados=1,
        inalterados=10,
        descartados=1,
        reativados=0,
        falha_coleta=False,
        coletado_em=datetime(2026, 5, 19, 14, 30, tzinfo=UTC),
        duracao_segundos=1.23,
    )
    relatorio = RelatorioIngestao(
        por_fonte=(rf,),
        agora=datetime(2026, 5, 19, 14, 30, tzinfo=UTC),
    )

    saida = _formatar_relatorio(relatorio)

    assert "CEMADEN" in saida
    assert "15 coletados" in saida
    assert "3 novos" in saida
    assert "1 atualizado" in saida
    assert "0 reativados" in saida
    assert "10 inalterados" in saida
    assert "1 descartado" in saida
    assert "1.23s" in saida
    assert "Total: 15 alertas" in saida


def test_formatar_relatorio_com_falha_indica_falha_de_coleta() -> None:
    """Relatório formatado de fonte que falhou destaca 'FALHA de coleta'."""
    rf = RelatorioFonte(
        fonte=FonteDado.CEMADEN,
        coletados=0,
        novos=0,
        atualizados=0,
        inalterados=0,
        descartados=0,
        falha_coleta=True,
        coletado_em=None,
        duracao_segundos=0.05,
    )
    relatorio = RelatorioIngestao(
        por_fonte=(rf,),
        agora=datetime(2026, 5, 19, 14, 30, tzinfo=UTC),
    )

    saida = _formatar_relatorio(relatorio)

    assert "CEMADEN" in saida
    assert "FALHA de coleta" in saida
    assert "0.05s" in saida
    assert "Total: 0 alertas" in saida


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
    mock_cemaden_source = MagicMock()

    monkeypatch.setattr("alertavida.monitor.criar_banco", mock_criar_banco)
    monkeypatch.setattr("alertavida.monitor.executar_ingestao", mock_executar_ingestao)
    monkeypatch.setattr("builtins.print", mock_print)
    monkeypatch.setattr("alertavida.monitor.CemadenSource", mock_cemaden_source)

    # Act
    result = main()

    # Assert
    mock_criar_banco.assert_called_once()
    mock_cemaden_source.assert_called_once()
    mock_executar_ingestao.assert_called_once_with([mock_cemaden_source.return_value])
    mock_print.assert_called_once()
    assert "CEMADEN: 5 coletados" in mock_print.call_args[0][0]
    assert "Total: 5 alertas" in mock_print.call_args[0][0]
    assert result == 0
