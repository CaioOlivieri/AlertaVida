"""Testes do orquestrador de ingestão multi-fonte (Camada 4, Parte B.2.a)."""

import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import FonteDado, NivelRisco, TipoEvento
from alertavida.ingestion import executar_ingestao
from alertavida.sources.base import DataSource, ResultadoColeta
from tests.fixtures.sources_fake import FakeDataSource

_DATA_CRIACAO = datetime(2026, 1, 1, tzinfo=UTC)


def _alerta(
    cod: str,
    fonte: FonteDado,
    lat: float = -23.5,
    lon: float = -46.6,
    *,
    ult_atualizacao: datetime | None = None,
) -> Alerta:
    """Constrói um Alerta mínimo e válido para testes."""
    return Alerta(
        cod_alerta=cod,
        fonte=fonte,
        tipo_evento=TipoEvento.HIDROLOGICO,
        nivel_risco=NivelRisco.ALTO,
        coordenadas=Coordenadas(latitude=lat, longitude=lon),
        data_criacao=_DATA_CRIACAO,
        ult_atualizacao=ult_atualizacao,
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


def test_persistencia_separada_por_fonte(db_temporario: object) -> None:
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


# ---------------------------------------------------------------------------
# Hardening-2 — ciclos multi-rodada e isolamento sob falha
# ---------------------------------------------------------------------------


def test_segunda_rodada_com_mesmo_ult_atualizacao_conta_inalterados(
    db_temporario: Path,
) -> None:
    """Alerta com mesmo ult_atualizacao em 2 rodadas conta como inalterado."""
    cod = "C1"
    ult_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    rodada_1 = [_alerta(cod, FonteDado.CEMADEN, ult_atualizacao=ult_at)]
    rodada_2 = [_alerta(cod, FonteDado.CEMADEN, ult_atualizacao=ult_at)]

    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[rodada_1, rodada_2],
    )

    relatorio_1 = executar_ingestao([source])
    assert relatorio_1.por_fonte[0].novos == 1
    assert relatorio_1.por_fonte[0].atualizados == 0
    assert relatorio_1.por_fonte[0].inalterados == 0

    relatorio_2 = executar_ingestao([source])
    assert relatorio_2.por_fonte[0].novos == 0
    assert relatorio_2.por_fonte[0].atualizados == 0
    assert relatorio_2.por_fonte[0].inalterados == 1


def test_segunda_rodada_com_ult_atualizacao_diferente_conta_atualizado(
    db_temporario: Path,
) -> None:
    """Mesmo cod_alerta com ult_atualizacao diferente conta como atualizado."""
    cod = "C1"
    ult_at_v1 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    ult_at_v2 = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)

    rodada_1 = [_alerta(cod, FonteDado.CEMADEN, ult_atualizacao=ult_at_v1)]
    rodada_2 = [_alerta(cod, FonteDado.CEMADEN, ult_atualizacao=ult_at_v2)]

    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[rodada_1, rodada_2],
    )

    relatorio_1 = executar_ingestao([source])
    assert relatorio_1.por_fonte[0].novos == 1

    relatorio_2 = executar_ingestao([source])
    assert relatorio_2.por_fonte[0].novos == 0
    assert relatorio_2.por_fonte[0].atualizados == 1
    assert relatorio_2.por_fonte[0].inalterados == 0


def test_alerta_ausente_por_tres_rodadas_emite_resolvido_no_outbox(
    db_temporario: Path,
) -> None:
    """Alerta ausente por 3 rodadas consecutivas emite AlertaResolvido no outbox.

    Verifica via query direta na tabela `eventos` (banco é fonte de verdade
    para resolvidos — RelatorioFonte não contém esse contador, decisão
    arquitetural: resolvidos são fenômeno derivado de ausência, não do
    batch coletado).
    """
    cod = "C1"
    ult_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    alerta = _alerta(cod, FonteDado.CEMADEN, ult_atualizacao=ult_at)

    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[
            [alerta],  # rodada 1 — alerta presente
            [],        # rodada 2 — ausente (1ª)
            [],        # rodada 3 — ausente (2ª)
            [],        # rodada 4 — ausente (3ª, dispara AlertaResolvido)
        ],
    )

    for _ in range(4):
        executar_ingestao([source])

    with sqlite3.connect(db_temporario) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM eventos "
            "WHERE tipo = 'AlertaResolvido' "
            "AND json_extract(payload, '$.fonte') = 'CEMADEN' "
            "AND json_extract(payload, '$.cod_alerta') = ?",
            (cod,),
        ).fetchone()[0]

    assert rows == 1, (
        f"Esperado exatamente 1 AlertaResolvido no outbox após 3 rodadas "
        f"ausentes consecutivas; encontrei {rows}."
    )


def test_deduplica_cod_alerta_repetido_no_mesmo_batch(db_temporario: Path) -> None:
    """cod_alerta duplicado no mesmo batch: 1 alerta, 1 descartado, sem crash."""
    alerta = _alerta("D1", FonteDado.CEMADEN)
    source = FakeDataSource(
        fonte=FonteDado.CEMADEN,
        alertas=[alerta, alerta],
        descartados=0,
    )
    relatorio = executar_ingestao([source])

    rf = relatorio.por_fonte[0]
    assert rf.coletados == 2
    assert rf.novos == 1
    assert rf.descartados == 1

    with sqlite3.connect(db_temporario) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE cod_alerta = 'D1' AND fonte = 'CEMADEN'"
        ).fetchone()[0]
    assert rows == 1


def test_alerta_resolvido_que_reaparece_reativa_sem_crash(
    db_temporario: Path,
) -> None:
    """Alerta resolvido que reaparece no feed emite AlertaReativado e reativa o row.

    Reprodução do Bug 1: alerta presente na rodada 1, ausente nas rodadas 2-4
    (vira RESOLVIDO), presente de novo na rodada 5.
    Antes da correção: IntegrityError (UNIQUE constraint) abortava a rodada.
    """
    cod = "C1"
    ult_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    alerta = _alerta(cod, FonteDado.CEMADEN, ult_atualizacao=ult_at)

    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[
            [alerta],  # rodada 1 — presente (CRIADO)
            [],        # rodada 2 — ausente (1ª)
            [],        # rodada 3 — ausente (2ª)
            [],        # rodada 4 — ausente (3ª, RESOLVIDO)
            [alerta],  # rodada 5 — reaparece (REATIVADO)
        ],
    )

    relatorios = []
    for _ in range(5):
        relatorio = executar_ingestao([source])
        relatorios.append(relatorio)

    relatorio_5 = relatorios[-1]

    assert relatorio_5.por_fonte[0].novos == 0
    assert relatorio_5.por_fonte[0].reativados == 1

    with sqlite3.connect(db_temporario) as conn:
        row = conn.execute(
            "SELECT status_interno, rodadas_ausente FROM alertas "
            "WHERE cod_alerta = ? AND fonte = 'CEMADEN'",
            (cod,),
        ).fetchone()
        reativados_count = conn.execute(
            "SELECT COUNT(*) FROM eventos WHERE tipo = 'AlertaReativado'"
        ).fetchone()[0]

    assert row[0] == "ATIVO", "Alerta reativado deve ter status_interno ATIVO"
    assert row[1] == 0, "Alerta reativado deve ter rodadas_ausente zerado"
    assert reativados_count == 1, (
        f"Esperado exatamente 1 AlertaReativado no outbox; encontrei {reativados_count}."
    )


def test_persistencia_de_fontes_anteriores_sobrevive_a_falha_posterior(
    db_temporario: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fonte que persistiu commit antes de outra fonte falhar sobrevive à falha.

    Cenário: 3 sources. Source A commita. Source B levanta
    sqlite3.OperationalError na persistência. Source C nunca roda porque
    a exceção propaga. Verificação: source A continua no banco, source
    B não. Prova durabilidade do commit por fonte.
    """
    from alertavida.database import aplicar_resultado_deteccao as _real
    from alertavida.domain.detector import ResultadoDeteccao

    chamadas_persistencia: list[int] = []

    def aplicar_com_falha_na_segunda(
        resultado: ResultadoDeteccao,
        alertas_por_codigo: dict[str, Alerta],
        agora: str,
    ) -> None:
        chamadas_persistencia.append(len(chamadas_persistencia))
        if len(chamadas_persistencia) == 2:
            raise sqlite3.OperationalError("falha simulada na 2a fonte")
        _real(resultado, alertas_por_codigo, agora)

    monkeypatch.setattr(
        "alertavida.ingestion.orquestrador.aplicar_resultado_deteccao",
        aplicar_com_falha_na_segunda,
    )

    source_a = FakeDataSource(
        fonte=FonteDado.CEMADEN,
        alertas=[_alerta("A1", FonteDado.CEMADEN), _alerta("A2", FonteDado.CEMADEN)],
    )
    source_b = FakeDataSource(
        fonte=FonteDado.EONET,
        alertas=[_alerta("B1", FonteDado.EONET)],
    )
    source_c = FakeDataSource(
        fonte=FonteDado.INMET,
        alertas=[_alerta("C1", FonteDado.INMET)],
    )

    with pytest.raises(sqlite3.OperationalError, match="falha simulada"):
        executar_ingestao([source_a, source_b, source_c])

    with sqlite3.connect(db_temporario) as conn:
        rows_a = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE fonte = 'CEMADEN'"
        ).fetchone()[0]
        rows_b = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE fonte = 'EONET'"
        ).fetchone()[0]
        rows_c = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE fonte = 'INMET'"
        ).fetchone()[0]

    assert rows_a == 2, "Source A devia ter persistido antes da falha em B"
    assert rows_b == 0, "Source B levantou na persistência — nada deve estar lá"
    assert rows_c == 0, "Source C nunca rodou — nada deve estar lá"
    assert len(chamadas_persistencia) == 2, (
        "Esperado exatamente 2 chamadas à aplicar_resultado_deteccao "
        "(A e B); C nunca chega por causa da exceção em B"
    )
