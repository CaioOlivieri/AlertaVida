"""Testes de executar_ingestao — orquestração do pipeline.

Após B.1.b, testes CEMADEN-específicos vivem em tests/sources/test_cemaden.py.
Estes 3 testes migrarão para tests/ingestao/test_orquestrador.py em B.2.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from alertavida.domain import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.detector import EventoDetectado, ResultadoDeteccao
from alertavida.domain.enums import (
    EscopoGeografico, FonteClassificacao, FonteDado,
    NivelRisco, TipoEvento,
)
from alertavida.domain.municipio import Municipio
from alertavida.monitor import executar_ingestao
from alertavida.sources import FalhaDeColeta, ResultadoColeta


def _alerta_exemplo(cod: str = "12345") -> Alerta:
    return Alerta(
        cod_alerta=cod,
        fonte=FonteDado.CEMADEN,
        municipio=Municipio(nome="Rio de Janeiro", uf="RJ"),
        coordenadas=Coordenadas(latitude=-22.91, longitude=-43.17),
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.MODERADO,
        data_criacao=datetime(2025, 12, 20, 14, 30, tzinfo=timezone.utc),
        escopo_geografico=EscopoGeografico.BRASIL,
        cobrade_codigo=None,
        fonte_classificacao=FonteClassificacao.INDETERMINADA,
    )


def test_executar_ingestao_usa_busca_snapshots_e_aplica_resultado():
    alerta = _alerta_exemplo()
    resultado_coleta = ResultadoColeta(
        alertas=[alerta], descartados=0,
        coletado_em=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    resultado_det = ResultadoDeteccao(
        eventos=[EventoDetectado(
            tipo="AlertaCriado", cod_alerta="12345",
            fonte=FonteDado.CEMADEN,
            payload={"cod_alerta": "12345", "fonte": "CEMADEN"},
        )],
        codigos_vistos={"12345"}, codigos_ausentes=set(),
        codigos_resolvidos=set(),
        fonte_por_codigo={"12345": FonteDado.CEMADEN},
    )

    with patch("alertavida.monitor.criar_banco") as mock_criar:
        with patch("alertavida.monitor.CemadenSource") as mock_source_cls:
            mock_source = mock_source_cls.return_value
            mock_source.fonte = FonteDado.CEMADEN
            mock_source.coletar.return_value = resultado_coleta
            with patch("alertavida.monitor.buscar_snapshots_ativos", return_value=[]) as mock_busca:
                with patch("alertavida.monitor.detectar_mudancas", return_value=resultado_det):
                    with patch("alertavida.monitor.aplicar_resultado_deteccao") as mock_aplicar:
                        executar_ingestao()

    mock_criar.assert_called_once()
    mock_busca.assert_called_once_with(FonteDado.CEMADEN)
    mock_aplicar.assert_called_once()


def test_executar_ingestao_conta_descartados_sem_erro_transacao():
    alerta = _alerta_exemplo("88")
    resultado_coleta = ResultadoColeta(
        alertas=[alerta], descartados=1,
        coletado_em=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    resultado_det = ResultadoDeteccao(
        eventos=[], codigos_vistos={"88"}, codigos_ausentes=set(),
        codigos_resolvidos=set(),
        fonte_por_codigo={"88": FonteDado.CEMADEN},
    )

    with patch("alertavida.monitor.criar_banco"):
        with patch("alertavida.monitor.CemadenSource") as mock_source_cls:
            mock_source = mock_source_cls.return_value
            mock_source.fonte = FonteDado.CEMADEN
            mock_source.coletar.return_value = resultado_coleta
            with patch("alertavida.monitor.buscar_snapshots_ativos", return_value=[]):
                with patch("alertavida.monitor.detectar_mudancas", return_value=resultado_det):
                    with patch("alertavida.monitor.aplicar_resultado_deteccao") as mock_aplicar:
                        executar_ingestao()
    assert mock_aplicar.call_count == 1


def test_executar_ingestao_loga_e_sai_em_falha_de_coleta():
    """Invariante: FalhaDeColeta no source faz executar_ingestao chamar sys.exit(1).
    Banco NÃO é tocado depois da falha."""
    with patch("alertavida.monitor.criar_banco"):
        with patch("alertavida.monitor.CemadenSource") as mock_source_cls:
            mock_source = mock_source_cls.return_value
            mock_source.coletar.side_effect = FalhaDeColeta(
                fonte=FonteDado.CEMADEN,
                causa="rede esgotada após 4 tentativas",
            )
            with patch("alertavida.monitor.buscar_snapshots_ativos") as mock_busca:
                with patch("alertavida.monitor.aplicar_resultado_deteccao") as mock_aplicar:
                    with pytest.raises(SystemExit) as exc_info:
                        executar_ingestao()
    assert exc_info.value.code == 1
    mock_busca.assert_not_called()
    mock_aplicar.assert_not_called()
