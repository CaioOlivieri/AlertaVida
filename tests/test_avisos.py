"""Persistência, consulta e coleta de avisos meteorológicos (issue #153)."""

from datetime import datetime, timezone
from unittest.mock import Mock

from alertavida import database as db_module
from alertavida.domain.aviso import AvisoMeteorologico, SeveridadeAviso
from alertavida.domain.enums import FonteDado
from alertavida.ingestion.avisos import executar_coleta_avisos, formatar_relatorio_avisos
from alertavida.sources.base import FalhaDeColeta

SP, RJ = 3550308, 3304557


def _aviso(id_aviso=1, seq=1, inicio=(23, 3), fim=(24, 2), codigos=(SP,), encerrado=False):
    return AvisoMeteorologico(
        codigo_cap=f"urn:oid:2.49.0.0.76.0.2026.{id_aviso}.{seq}",
        id_aviso=id_aviso,
        id_sequencia=seq,
        evento="Tempestade",
        severidade=SeveridadeAviso.PERIGO,
        inicio=datetime(2026, 11, inicio[0], inicio[1], tzinfo=timezone.utc),
        fim=datetime(2026, 11, fim[0], fim[1], 59, tzinfo=timezone.utc),
        codigos_ibge=frozenset(codigos),
        encerrado=encerrado,
    )


def _vigentes(codibge, instante):
    return [a.codigo_cap for a in db_module.avisos_vigentes(codibge, instante)]


class TestRegistrarAvisos:
    def test_idempotente_por_codigo_cap(self, db_temporario):
        assert db_module.registrar_avisos([_aviso(), _aviso(2)], "t1").novos == 2
        segunda = db_module.registrar_avisos([_aviso(), _aviso(2)], "t2")
        assert (segunda.novos, segunda.ja_conhecidos) == (0, 2)

    def test_encerramento_posterior_e_registrado(self, db_temporario):
        db_module.registrar_avisos([_aviso()], "t1")
        db_module.registrar_avisos([_aviso(encerrado=True)], "t2")
        assert _vigentes(SP, "2026-11-23T12:00:00+00:00") == []


class TestAvisosVigentes:
    def test_dentro_da_janela_e_do_municipio(self, db_temporario):
        db_module.registrar_avisos([_aviso(codigos=(SP, RJ))], "t")
        esperado = ["urn:oid:2.49.0.0.76.0.2026.1.1"]
        assert _vigentes(SP, "2026-11-23T12:00:00.137000+00:00") == esperado
        assert _vigentes(RJ, "2026-11-23T12:00:00+00:00") == esperado

    def test_fora_da_janela(self, db_temporario):
        db_module.registrar_avisos([_aviso()], "t")
        assert _vigentes(SP, "2026-11-23T02:59:59+00:00") == []
        assert _vigentes(SP, "2026-11-25T00:00:00+00:00") == []

    def test_bordas_inclusivas_com_fracoes_de_segundo(self, db_temporario):
        """Início e fim contam (janela fechada). Como string, `03:00:00.000000`
        seria "maior" que `03:00:00+` por causa do `.`; julianday compara o
        instante. O fim é 02:59:00 UTC = 23:59 de Brasília, como o INMET publica."""
        db_module.registrar_avisos([_aviso()], "t")
        assert _vigentes(SP, "2026-11-23T03:00:00.000000+00:00") != []
        assert _vigentes(SP, "2026-11-24T02:59:00.000000+00:00") != []
        assert _vigentes(SP, "2026-11-24T02:59:01+00:00") == []

    def test_outro_municipio_nao_recebe(self, db_temporario):
        db_module.registrar_avisos([_aviso(codigos=(SP,))], "t")
        assert _vigentes(RJ, "2026-11-23T12:00:00+00:00") == []

    def test_sequencia_nova_substitui_a_anterior(self, db_temporario):
        """A seq 2 encurta a janela: às 20h só a seq 1 cobriria — e não conta mais."""
        db_module.registrar_avisos([_aviso(seq=1, fim=(24, 2))], "t1")
        db_module.registrar_avisos([_aviso(seq=2, fim=(23, 15))], "t2")
        assert _vigentes(SP, "2026-11-23T10:00:00+00:00") == ["urn:oid:2.49.0.0.76.0.2026.1.2"]
        assert _vigentes(SP, "2026-11-23T20:00:00+00:00") == []

    def test_instante_em_outro_fuso_e_comparado_corretamente(self, db_temporario):
        db_module.registrar_avisos([_aviso()], "t")
        # 00:30 de Brasília = 03:30 UTC, dentro da janela que começa 03:00 UTC.
        assert _vigentes(SP, "2026-11-23T00:30:00-03:00") != []
        # 23:59 de 22/11 em Brasília = 02:59 UTC, antes da janela.
        assert _vigentes(SP, "2026-11-22T23:59:00-03:00") == []


class TestColetaAvisos:
    def test_coleta_grava_e_reporta(self, db_temporario):
        source = Mock()
        source.coletar.return_value = ([_aviso(), _aviso(2)], 1)
        relatorio = executar_coleta_avisos(source)
        assert (relatorio.coletados, relatorio.novos, relatorio.descartados) == (2, 2, 1)
        texto = formatar_relatorio_avisos(relatorio)
        assert "2 vigentes ou futuros (2 novos, 1 descartados)" in texto

    def test_falha_de_coleta_nao_propaga(self, db_temporario):
        source = Mock()
        source.coletar.side_effect = FalhaDeColeta(fonte=FonteDado.INMET, causa="rede")
        relatorio = executar_coleta_avisos(source)
        assert relatorio.falha_coleta
        assert "FALHA de coleta" in formatar_relatorio_avisos(relatorio)
