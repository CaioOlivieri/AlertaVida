"""Testes do orquestrador de ingestão multi-fonte (Camada 4, Parte B.2.a)."""

import math
import sqlite3
from datetime import UTC, datetime

import pytest

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento
from alertavida.ingestion import executar_ingestao
from alertavida.sources.base import DataSource, ResultadoColeta
from tests.fixtures.sources_fake import FakeDataSource

_DATA_CRIACAO = datetime(2026, 1, 1, tzinfo=UTC)


def _alerta(cod: str, fonte: FonteDado, lat: float = -23.5, lon: float = -46.6) -> Alerta:
    """Constrói um Alerta mínimo e válido para testes."""
    return Alerta(
        cod_alerta=cod,
        fonte=fonte,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=lat, longitude=lon),
        data_criacao=_DATA_CRIACAO,
    )


# ---------------------------------------------------------------------------
# Casos principais
# ---------------------------------------------------------------------------


def test_caminho_feliz_uma_fonte(db_temporario: object) -> None:
    alertas = [
        _alerta("C1", FonteDado.CEMADEN),
        _alerta("C2", FonteDado.CEMADEN),
        _alerta("C3", FonteDado.CEMADEN),
    ]
    source = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=alertas)
    relatorio = executar_ingestao([source])

    assert len(relatorio.por_fonte) == 1
    rf = relatorio.por_fonte[0]
    assert rf.coletados == 3
    assert rf.novos == 3
    assert rf.atualizados == 0
    assert rf.inalterados == 0
    assert rf.descartados == 0
    assert rf.falha_coleta is False
    # __post_init__ garante invariante: novos+atualizados+inalterados+descartados == coletados


def test_duas_fontes_contadores_independentes(db_temporario: object) -> None:
    alertas_cemaden = [_alerta("C1", FonteDado.CEMADEN), _alerta("C2", FonteDado.CEMADEN)]
    alertas_eonet = [
        _alerta("E1", FonteDado.EONET),
        _alerta("E2", FonteDado.EONET),
        _alerta("E3", FonteDado.EONET),
    ]
    source_cemaden = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=alertas_cemaden)
    source_eonet = FakeDataSource(fonte=FonteDado.EONET, alertas=alertas_eonet)

    relatorio = executar_ingestao([source_cemaden, source_eonet])

    assert len(relatorio.por_fonte) == 2
    rf_cemaden = relatorio.por_fonte[0]
    assert rf_cemaden.fonte == FonteDado.CEMADEN
    assert rf_cemaden.coletados == 2
    assert rf_cemaden.novos == 2

    rf_eonet = relatorio.por_fonte[1]
    assert rf_eonet.fonte == FonteDado.EONET
    assert rf_eonet.coletados == 3
    assert rf_eonet.novos == 3

    assert relatorio.total == 5


def test_falha_coleta_em_uma_fonte_nao_impede_outras(db_temporario: object) -> None:
    falha = FakeDataSource(fonte=FonteDado.CEMADEN, falhar=True)
    ok = FakeDataSource(
        fonte=FonteDado.EONET,
        alertas=[_alerta("E1", FonteDado.EONET)],
    )

    relatorio = executar_ingestao([falha, ok])

    assert len(relatorio.por_fonte) == 2

    rf_falha = relatorio.por_fonte[0]
    assert rf_falha.falha_coleta is True
    assert rf_falha.coletados == 0
    assert rf_falha.novos == 0
    assert rf_falha.atualizados == 0
    assert rf_falha.inalterados == 0
    assert rf_falha.descartados == 0
    assert rf_falha.coletado_em is None

    rf_ok = relatorio.por_fonte[1]
    assert rf_ok.falha_coleta is False
    assert rf_ok.coletados == 1
    assert rf_ok.novos == 1


def test_agora_default_eh_timezone_aware() -> None:
    relatorio = executar_ingestao([])
    assert relatorio.agora.tzinfo is not None


def test_agora_injetado_eh_propagado() -> None:
    momento = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    relatorio = executar_ingestao([], agora=momento)
    assert relatorio.agora == momento


def test_ordem_das_fontes_preservada(db_temporario: object) -> None:
    fake_a = FakeDataSource(
        fonte=FonteDado.CEMADEN,
        alertas=[_alerta("A1", FonteDado.CEMADEN)],
    )
    fake_b = FakeDataSource(
        fonte=FonteDado.EONET,
        alertas=[_alerta("B1", FonteDado.EONET)],
    )
    fake_c = FakeDataSource(
        fonte=FonteDado.INMET,
        alertas=[_alerta("I1", FonteDado.INMET)],
    )

    relatorio = executar_ingestao([fake_a, fake_b, fake_c])

    assert relatorio.por_fonte[0].fonte == FonteDado.CEMADEN
    assert relatorio.por_fonte[1].fonte == FonteDado.EONET
    assert relatorio.por_fonte[2].fonte == FonteDado.INMET


def test_source_sem_alertas(db_temporario: object) -> None:
    source = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=[])

    relatorio = executar_ingestao([source])

    rf = relatorio.por_fonte[0]
    assert rf.coletados == 0
    assert rf.novos == 0
    assert rf.atualizados == 0
    assert rf.inalterados == 0
    assert rf.descartados == 0
    assert rf.falha_coleta is False


def test_total_property(db_temporario: object) -> None:
    source1 = FakeDataSource(
        fonte=FonteDado.CEMADEN,
        alertas=[_alerta("C1", FonteDado.CEMADEN), _alerta("C2", FonteDado.CEMADEN)],
    )
    source2 = FakeDataSource(
        fonte=FonteDado.EONET,
        alertas=[_alerta("E1", FonteDado.EONET)],
    )

    relatorio = executar_ingestao([source1, source2])

    assert relatorio.total == 3


def test_excecao_nao_falha_coleta_propaga() -> None:
    class _FakeQuebraComTypeError(DataSource):
        @property
        def fonte(self) -> FonteDado:
            return FonteDado.CEMADEN

        def coletar(self) -> ResultadoColeta:
            raise TypeError("bug interno simulado")

    with pytest.raises(TypeError, match="bug interno simulado"):
        executar_ingestao([_FakeQuebraComTypeError()])


def test_duracao_segundos_eh_positiva_e_finita(db_temporario: object) -> None:
    source = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=[])

    relatorio = executar_ingestao([source])

    rf = relatorio.por_fonte[0]
    assert rf.duracao_segundos >= 0
    assert math.isfinite(rf.duracao_segundos)


def test_coletado_em_propagado_de_resultado_coleta(db_temporario: object) -> None:
    momento_coleta = datetime(2026, 3, 10, 8, 30, tzinfo=UTC)
    source = FakeDataSource(
        fonte=FonteDado.CEMADEN,
        alertas=[],
        coletado_em=momento_coleta,
    )

    relatorio = executar_ingestao([source])

    assert relatorio.por_fonte[0].coletado_em == momento_coleta


def test_falha_coleta_zera_coletado_em() -> None:
    source = FakeDataSource(fonte=FonteDado.CEMADEN, falhar=True)

    relatorio = executar_ingestao([source])

    assert relatorio.por_fonte[0].coletado_em is None


def test_isolamento_de_persistencia(db_temporario: object) -> None:
    alertas_cemaden = [
        _alerta("C1", FonteDado.CEMADEN),
        _alerta("C2", FonteDado.CEMADEN),
    ]
    alertas_eonet = [_alerta("E1", FonteDado.EONET)]
    source1 = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=alertas_cemaden)
    source2 = FakeDataSource(fonte=FonteDado.EONET, alertas=alertas_eonet)

    relatorio = executar_ingestao([source1, source2])

    with sqlite3.connect(db_temporario) as conn:
        rows_cemaden = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE fonte = 'CEMADEN'"
        ).fetchone()[0]
        rows_eonet = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE fonte = 'EONET'"
        ).fetchone()[0]

    assert rows_cemaden == relatorio.por_fonte[0].novos == 2
    assert rows_eonet == relatorio.por_fonte[1].novos == 1


def test_rodada_sem_fontes() -> None:
    relatorio = executar_ingestao([])
    assert relatorio.por_fonte == ()
    assert relatorio.total == 0
