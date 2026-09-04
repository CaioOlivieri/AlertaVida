"""Testes do orquestrador de ingestão multi-fonte (Camada 4, Parte B.2.a)."""

import contextlib
import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alertavida.domain.alerta import Alerta
from alertavida.domain.coordenadas import Coordenadas
from alertavida.domain.enums import FonteClassificacao, FonteDado, NivelRisco, TipoEvento
from alertavida.domain.incidente import Incidente, MembroIncidente
from alertavida.domain.municipio import Municipio
from alertavida.ingestion import executar_ingestao
from alertavida.ingestion.orquestrador import RelatorioFonte, RelatorioIngestao
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
    tipo_evento: TipoEvento = TipoEvento.HIDROLOGICO,
    nivel_risco: NivelRisco = NivelRisco.ALTO,
    cobrade_codigo: str | None = None,
    codigo_ibge: int | None = None,
    data_criacao: datetime = _DATA_CRIACAO,
) -> Alerta:
    """Constrói um Alerta mínimo e válido para testes.

    Parâmetros adicionais (tipo_evento/cobrade_codigo/codigo_ibge/data_criacao)
    existem para os testes de correlação (issue #61) — controlam exatamente
    os campos que `domain/correlacao.py` usa para decidir VINCULA/REVISAO/
    NAO_VINCULA.
    """
    municipio = (
        Municipio(nome="Teste", uf="RS", codigo_ibge=codigo_ibge)
        if codigo_ibge is not None
        else None
    )
    return Alerta(
        cod_alerta=cod,
        fonte=fonte,
        tipo_evento=tipo_evento,
        nivel_risco=nivel_risco,
        coordenadas=Coordenadas(latitude=lat, longitude=lon),
        municipio=municipio,
        data_criacao=data_criacao,
        ult_atualizacao=ult_atualizacao,
        cobrade_codigo=cobrade_codigo,
        fonte_classificacao=(
            FonteClassificacao.DIRETA
            if cobrade_codigo is not None
            else FonteClassificacao.INDETERMINADA
        ),
    )


# ---------------------------------------------------------------------------
# Invariantes de RelatorioFonte / RelatorioIngestao
# ---------------------------------------------------------------------------


def test_relatorio_fonte_soma_incorreta_lanca() -> None:
    with pytest.raises(ValueError):
        RelatorioFonte(
            fonte=FonteDado.CEMADEN,
            coletados=5,
            novos=2,
            atualizados=1,
            inalterados=1,
            descartados=0,
            falha_coleta=False,
            coletado_em=datetime(2026, 1, 1, tzinfo=UTC),
            duracao_segundos=0.5,
        )


def test_relatorio_fonte_sucesso_sem_coletado_em_lanca() -> None:
    with pytest.raises(ValueError):
        RelatorioFonte(
            fonte=FonteDado.CEMADEN,
            coletados=0,
            novos=0,
            atualizados=0,
            inalterados=0,
            descartados=0,
            falha_coleta=False,
            coletado_em=None,
            duracao_segundos=0.5,
        )


def test_relatorio_fonte_falha_com_contador_nao_zero_lanca() -> None:
    with pytest.raises(ValueError):
        RelatorioFonte(
            fonte=FonteDado.CEMADEN,
            coletados=1,
            novos=0,
            atualizados=0,
            inalterados=0,
            descartados=0,
            falha_coleta=True,
            coletado_em=None,
            duracao_segundos=0.5,
        )


def test_relatorio_fonte_falha_com_coletado_em_nao_none_lanca() -> None:
    with pytest.raises(ValueError):
        RelatorioFonte(
            fonte=FonteDado.CEMADEN,
            coletados=0,
            novos=0,
            atualizados=0,
            inalterados=0,
            descartados=0,
            falha_coleta=True,
            coletado_em=datetime(2026, 1, 1, tzinfo=UTC),
            duracao_segundos=0.5,
        )


def test_relatorio_fonte_duracao_negativa_lanca() -> None:
    with pytest.raises(ValueError):
        RelatorioFonte(
            fonte=FonteDado.CEMADEN,
            coletados=0,
            novos=0,
            atualizados=0,
            inalterados=0,
            descartados=0,
            falha_coleta=False,
            coletado_em=datetime(2026, 1, 1, tzinfo=UTC),
            duracao_segundos=-0.1,
        )


def test_relatorio_ingestao_agora_naive_lanca() -> None:
    with pytest.raises(ValueError):
        RelatorioIngestao(
            por_fonte=(),
            agora=datetime(2026, 1, 1),  # sem tzinfo
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

    with contextlib.closing(sqlite3.connect(db_temporario)) as conn:
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

    with contextlib.closing(sqlite3.connect(db_temporario)) as conn:
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

    with contextlib.closing(sqlite3.connect(db_temporario)) as conn:
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

    with contextlib.closing(sqlite3.connect(db_temporario)) as conn:
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
    ) -> dict[str, int]:
        chamadas_persistencia.append(len(chamadas_persistencia))
        if len(chamadas_persistencia) == 2:
            raise sqlite3.OperationalError("falha simulada na 2a fonte")
        return _real(resultado, alertas_por_codigo, agora)

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

    with contextlib.closing(sqlite3.connect(db_temporario)) as conn:
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


# ---------------------------------------------------------------------------
# Correlação de incidentes (issue #61) — wiring end-to-end via
# executar_ingestao. O núcleo de decisão (domain/correlacao.py, #58) e o
# blocking (database.avaliar_candidatos_correlacao, #60) já têm sua própria
# cobertura extensa; os testes abaixo verificam só a AÇÃO tomada sobre o
# resultado (criar/juntar/fundir/resolver/reativar Incidente), não
# recalculam o score.
# ---------------------------------------------------------------------------


def _contar_eventos(db_path: Path, tipo: str) -> int:
    with contextlib.closing(sqlite3.connect(db_path)) as conexao:
        return conexao.execute(
            "SELECT COUNT(*) FROM eventos WHERE tipo = ?", (tipo,)
        ).fetchone()[0]


def test_correlacao_duas_fontes_mesmo_evento_forma_incidente_severidade_maxima(
    db_temporario: Path,
) -> None:
    """Round 1 Q3: severidade do Incidente = máximo entre membros conhecidos.

    Dois alertas de fontes diferentes, mesma posição/onset/cobrade — o par
    ideal para VINCULA (score 1.0). CEMADEN chega primeiro e abre o
    Incidente; EONET se junta a ele.
    """
    onset = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    alerta_cemaden = _alerta(
        "A1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        nivel_risco=NivelRisco.ALTO,
        data_criacao=onset,
    )
    alerta_eonet = _alerta(
        "B1",
        FonteDado.EONET,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        nivel_risco=NivelRisco.MUITO_ALTO,
        data_criacao=onset,
    )
    source_cemaden = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=[alerta_cemaden])
    source_eonet = FakeDataSource(fonte=FonteDado.EONET, alertas=[alerta_eonet])

    relatorio = executar_ingestao([source_cemaden, source_eonet])

    assert relatorio.por_fonte[0].incidentes_criados == 1
    assert relatorio.por_fonte[1].incidentes_juntados == 1

    with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
        incidente_ids = conexao.execute(
            "SELECT DISTINCT incidente_id FROM incidente_membros"
        ).fetchall()
        assert len(incidente_ids) == 1
        membros_rows = conexao.execute(
            "SELECT a.fonte, a.cod_alerta, a.nivel FROM incidente_membros im "
            "JOIN alertas a ON a.id = im.alerta_id "
            "WHERE im.incidente_id = ?",
            (incidente_ids[0][0],),
        ).fetchall()

    assert len(membros_rows) == 2
    incidente = Incidente(
        membros=tuple(
            MembroIncidente(
                fonte=FonteDado.from_string(fonte),
                cod_alerta=cod,
                nivel_risco=NivelRisco.from_string(nivel),
            )
            for fonte, cod, nivel in membros_rows
        ),
        criado_em=onset,
        atualizado_em=onset,
    )
    assert incidente.severidade == NivelRisco.MUITO_ALTO


def test_correlacao_tipos_incompativeis_gera_dois_incidentes(
    db_temporario: Path,
) -> None:
    """Portão estrutural: tipos INCOMPATIVEL nunca VINCULA (#58), então dois
    alertas da mesma posição/onset mas grupos COBRADE diferentes abrem dois
    Incidentes distintos."""
    onset = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    hidrologico = _alerta(
        "A1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",  # grupo 1.2 (hidrológico)
        data_criacao=onset,
    )
    geologico = _alerta(
        "A2",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.1.1.0.0",  # grupo 1.1 (geológico) — grupo diferente
        data_criacao=onset,
    )
    source = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=[hidrologico, geologico])

    relatorio = executar_ingestao([source])

    assert relatorio.por_fonte[0].incidentes_criados == 2
    assert relatorio.por_fonte[0].incidentes_juntados == 0
    with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
        incidente_ids = conexao.execute(
            "SELECT DISTINCT incidente_id FROM incidente_membros"
        ).fetchall()
    assert len(incidente_ids) == 2


def test_correlacao_banda_revisao_alerta_fica_separado_e_observacao_flagada(
    db_temporario: Path,
) -> None:
    """Round 2 — bias para separar: REVISAO nunca auto-vincula. Segundo
    alerta com `tipo_evento=INDETERMINADO` (sem cobrade) contra um
    Incidente compatível o suficiente para cair na banda de revisão
    (LIMIAR_REVISAO <= score < LIMIAR_VINCULA) abre seu PRÓPRIO Incidente
    e grava uma observação REVISAO — nunca junta automaticamente."""
    onset = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    fundador = _alerta(
        "A1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        data_criacao=onset,
    )
    indeterminado = _alerta(
        "B1",
        FonteDado.EONET,
        lat=-29.84,
        lon=-56.73,
        tipo_evento=TipoEvento.INDETERMINADO,  # sem cobrade -> INDETERMINADA
        data_criacao=onset,
    )
    source_cemaden = FakeDataSource(fonte=FonteDado.CEMADEN, alertas=[fundador])
    source_eonet = FakeDataSource(fonte=FonteDado.EONET, alertas=[indeterminado])

    relatorio = executar_ingestao([source_cemaden, source_eonet])

    assert relatorio.por_fonte[0].incidentes_criados == 1
    rf_eonet = relatorio.por_fonte[1]
    assert rf_eonet.incidentes_criados == 1
    assert rf_eonet.incidentes_juntados == 0
    assert rf_eonet.incidentes_revisao == 1

    with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
        incidente_ids = conexao.execute(
            "SELECT DISTINCT incidente_id FROM incidente_membros"
        ).fetchall()
        observacao_revisao = conexao.execute(
            "SELECT decisao, motivo FROM correlacao_observacoes WHERE decisao = 'REVISAO'"
        ).fetchall()
    assert len(incidente_ids) == 2
    assert len(observacao_revisao) == 1
    assert observacao_revisao[0][1] == "tipo_indeterminado_evidencia_forte"


def test_correlacao_resolve_incidente_so_quando_ultimo_membro_resolve(
    db_temporario: Path,
) -> None:
    """Round 1 Q5: Incidente resolve quando o ÚLTIMO membro não-resolvido
    resolve, nunca quando qualquer um resolve.

    C1 (CEMADEN) desaparece a partir da rodada 2 e resolve na rodada 4 (3ª
    ausência); E1 (EONET) continua presente até a rodada 4, some a partir
    da 5 e resolve na rodada 7. O Incidente (1 só, os dois se juntam na
    rodada 1) só deve resolver depois da rodada 7.
    """
    onset = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    alerta_cemaden = _alerta(
        "C1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        data_criacao=onset,
        ult_atualizacao=onset,
    )
    alerta_eonet = _alerta(
        "E1",
        FonteDado.EONET,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        data_criacao=onset,
        ult_atualizacao=onset,
    )
    source_cemaden = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[[alerta_cemaden], [], [], [], [], [], []],
    )
    source_eonet = FakeDataSource.com_rodadas(
        fonte=FonteDado.EONET,
        rodadas=[
            [alerta_eonet],
            [alerta_eonet],
            [alerta_eonet],
            [alerta_eonet],
            [],
            [],
            [],
        ],
    )

    for _ in range(4):
        executar_ingestao([source_cemaden, source_eonet])
    assert _contar_eventos(db_temporario, "IncidenteResolvido") == 0

    for _ in range(3):
        executar_ingestao([source_cemaden, source_eonet])
    assert _contar_eventos(db_temporario, "IncidenteResolvido") == 1


def test_correlacao_dois_membros_mesma_rodada_emite_um_incidente_resolvido(
    db_temporario: Path,
) -> None:
    """Regressão da issue #85: dois membros do mesmo Incidente resolvendo na
    mesma rodada emitem exatamente UM `IncidenteResolvido`, não um por
    membro.

    C1 e C2 (mesma fonte, mesma posição/onset/cobrade) VINCULAM no mesmo
    Incidente na rodada 1. Ambos somem juntos a partir da rodada 2 e
    completam RODADAS_PARA_RESOLVER=3 ausências simultaneamente na rodada 4
    — reprodução exata do bug: os dois eventos RESOLVIDO da mesma fonte
    chegam na mesma chamada de `_correlacionar_rodada`, e por já estarem
    ambos `RESOLVIDO` no banco quando o segundo é visitado,
    `todos_membros_resolvidos` retornava True nas duas visitas antes da
    guarda de status.
    """
    onset = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    alerta_c1 = _alerta(
        "C1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        data_criacao=onset,
        ult_atualizacao=onset,
    )
    alerta_c2 = _alerta(
        "C2",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        data_criacao=onset,
        ult_atualizacao=onset,
    )
    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[
            [alerta_c1, alerta_c2],  # rodada 1 — ambos presentes, mesmo Incidente
            [],  # rodada 2 — ausentes (1ª)
            [],  # rodada 3 — ausentes (2ª)
            [],  # rodada 4 — ausentes (3ª, ambos resolvem juntos)
        ],
    )

    relatorio_1 = executar_ingestao([source])
    assert relatorio_1.por_fonte[0].incidentes_criados == 1
    assert relatorio_1.por_fonte[0].incidentes_juntados == 1

    for _ in range(3):
        executar_ingestao([source])

    assert _contar_eventos(db_temporario, "IncidenteResolvido") == 1, (
        "Esperado exatamente 1 IncidenteResolvido quando dois membros do "
        "mesmo Incidente resolvem na mesma rodada"
    )

    with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
        status = conexao.execute("SELECT status FROM incidentes").fetchall()
    assert status == [("RESOLVIDO",)]


def test_correlacao_reativacao_de_membro_reativa_incidente(
    db_temporario: Path,
) -> None:
    """Round 1 Q5: reativação de um membro reativa o Incidente. Incidente de
    membro único resolve junto com seu único Alerta (rodada 4, 3ª ausência)
    e reativa quando o Alerta reaparece (rodada 5)."""
    onset = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    alerta = _alerta(
        "C1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        data_criacao=onset,
        ult_atualizacao=onset,
    )
    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[[alerta], [], [], [], [alerta]],
    )

    for _ in range(4):
        executar_ingestao([source])
    assert _contar_eventos(db_temporario, "IncidenteResolvido") == 1
    assert _contar_eventos(db_temporario, "IncidenteReativado") == 0

    executar_ingestao([source])
    assert _contar_eventos(db_temporario, "IncidenteReativado") == 1


def test_correlacao_funde_dois_incidentes_com_redirect_intacto(
    db_temporario: Path,
) -> None:
    """Round 1 Q6: um alerta que VINCULA com dois Incidentes abertos
    distintos ao mesmo tempo prova que os dois descrevem o mesmo evento —
    dispara fusão (append-only redirect, nunca delete).

    A (t=0) e B (t=+8h) mesma posição/ibge/cobrade, mas separados por mais
    que a janela de 6h — B não vê A como candidato ao nascer, cada um abre
    seu próprio Incidente. C (t=+4h) fica dentro da janela de AMBOS e
    VINCULA com os dois -> funde, sobrevivendo o mais antigo (A).
    """
    t0 = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    alerta_a = _alerta(
        "A1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        codigo_ibge=4322400,
        data_criacao=t0,
    )
    alerta_b = _alerta(
        "B1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        codigo_ibge=4322400,
        data_criacao=t0 + timedelta(hours=8),
    )
    alerta_c = _alerta(
        "C1",
        FonteDado.CEMADEN,
        lat=-29.84,
        lon=-56.73,
        cobrade_codigo="1.2.1.0.0",
        codigo_ibge=4322400,
        data_criacao=t0 + timedelta(hours=4),
    )
    source = FakeDataSource.com_rodadas(
        fonte=FonteDado.CEMADEN,
        rodadas=[[alerta_a], [alerta_b], [alerta_c]],
    )

    relatorio_1 = executar_ingestao([source])
    assert relatorio_1.por_fonte[0].incidentes_criados == 1

    relatorio_2 = executar_ingestao([source])
    assert relatorio_2.por_fonte[0].incidentes_criados == 1  # B não viu A (fora da janela)

    relatorio_3 = executar_ingestao([source])
    assert relatorio_3.por_fonte[0].incidentes_fundidos == 1

    with contextlib.closing(sqlite3.connect(db_temporario)) as conexao:
        incidente_ids = conexao.execute(
            "SELECT id FROM incidentes ORDER BY id"
        ).fetchall()
        assert len(incidente_ids) == 2  # ambos os ids continuam resolvíveis
        sobrevivente_id, fundido_id = incidente_ids[0][0], incidente_ids[1][0]

        fundido_em = conexao.execute(
            "SELECT fundido_em FROM incidentes WHERE id = ?", (fundido_id,)
        ).fetchone()[0]
        assert fundido_em == sobrevivente_id

        incidente_do_c = conexao.execute(
            "SELECT im.incidente_id FROM incidente_membros im "
            "JOIN alertas a ON a.id = im.alerta_id WHERE a.cod_alerta = 'C1'"
        ).fetchone()[0]
        assert incidente_do_c == sobrevivente_id

        evento_fusao = conexao.execute(
            "SELECT agregado_incidente_id, payload FROM eventos "
            "WHERE tipo = 'IncidenteFundido'"
        ).fetchone()
    assert evento_fusao is not None
    assert evento_fusao[0] == fundido_id
    payload = json.loads(evento_fusao[1])
    assert payload["incidente_sobrevivente_id"] == sobrevivente_id
    assert payload["incidente_fundido_id"] == fundido_id
