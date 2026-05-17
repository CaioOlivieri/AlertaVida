"""Testes do entrypoint manual `python -m alertavida.monitor`.

Foca em `_formatar_relatorio` (função pura). A orquestração real é
testada em `tests/ingestion/test_orquestrador.py`.
"""

from datetime import UTC, datetime

from alertavida.domain.enums import FonteDado
from alertavida.ingestion.orquestrador import RelatorioFonte, RelatorioIngestao
from alertavida.monitor import _formatar_relatorio


def test_formatar_relatorio_com_sucesso_inclui_contadores() -> None:
    """Relatório formatado de fonte bem-sucedida lista todos os contadores."""
    rf = RelatorioFonte(
        fonte=FonteDado.CEMADEN,
        coletados=15,
        novos=3,
        atualizados=1,
        inalterados=10,
        descartados=1,
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
