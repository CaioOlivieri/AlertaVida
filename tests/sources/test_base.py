"""Testes da interface DataSource, ResultadoColeta e FalhaDeColeta."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from alertavida.domain.enums import FonteDado
from alertavida.sources import DataSource, FalhaDeColeta, ResultadoColeta


class TestDataSourceABC:
    """DataSource é abstrata; força implementação de fonte e coletar."""

    def test_nao_pode_instanciar_diretamente(self):
        with pytest.raises(TypeError, match="abstract"):
            DataSource()

    def test_subclasse_sem_fonte_nao_instancia(self):
        class IncompletaSemFonte(DataSource):
            def coletar(self) -> ResultadoColeta:
                return ResultadoColeta(
                    alertas=[],
                    descartados=0,
                    coletado_em=datetime.now(timezone.utc),
                )
        with pytest.raises(TypeError, match="abstract"):
            IncompletaSemFonte()

    def test_subclasse_sem_coletar_nao_instancia(self):
        class IncompletaSemColetar(DataSource):
            @property
            def fonte(self) -> FonteDado:
                return FonteDado.CEMADEN
        with pytest.raises(TypeError, match="abstract"):
            IncompletaSemColetar()

    def test_subclasse_completa_instancia(self):
        class Completa(DataSource):
            @property
            def fonte(self) -> FonteDado:
                return FonteDado.CEMADEN
            def coletar(self) -> ResultadoColeta:
                return ResultadoColeta(
                    alertas=[],
                    descartados=0,
                    coletado_em=datetime.now(timezone.utc),
                )
        instance = Completa()
        assert instance.fonte == FonteDado.CEMADEN
        resultado = instance.coletar()
        assert isinstance(resultado, ResultadoColeta)


class TestResultadoColetaFrozen:
    """ResultadoColeta é imutável após construção."""

    def test_atributos_basicos(self):
        agora = datetime(2026, 5, 14, tzinfo=timezone.utc)
        r = ResultadoColeta(alertas=[], descartados=0, coletado_em=agora)
        assert r.alertas == []
        assert r.descartados == 0
        assert r.coletado_em == agora

    def test_nao_permite_atribuicao(self):
        agora = datetime(2026, 5, 14, tzinfo=timezone.utc)
        r = ResultadoColeta(alertas=[], descartados=0, coletado_em=agora)
        with pytest.raises(FrozenInstanceError):
            r.descartados = 5

    def test_nao_permite_atribuicao_alertas(self):
        agora = datetime(2026, 5, 14, tzinfo=timezone.utc)
        r = ResultadoColeta(alertas=[], descartados=0, coletado_em=agora)
        with pytest.raises(FrozenInstanceError):
            r.alertas = []


class TestFalhaDeColeta:
    """Exceção tipada do domínio para falhas de rodada de DataSource."""

    def test_construtor_minimo(self):
        exc = FalhaDeColeta(fonte=FonteDado.CEMADEN, causa="rede esgotada")
        assert exc.fonte == FonteDado.CEMADEN
        assert exc.causa == "rede esgotada"
        assert exc.original is None

    def test_construtor_com_original(self):
        original = ValueError("payload corrompido")
        exc = FalhaDeColeta(
            fonte=FonteDado.EONET,
            causa="parse falhou",
            original=original,
        )
        assert exc.fonte == FonteDado.EONET
        assert exc.original is original

    def test_str_inclui_fonte_e_causa(self):
        exc = FalhaDeColeta(fonte=FonteDado.INMET, causa="timeout total")
        msg = str(exc)
        assert "INMET" in msg
        assert "timeout total" in msg

    def test_e_subclasse_de_exception(self):
        exc = FalhaDeColeta(fonte=FonteDado.INPE, causa="x")
        assert isinstance(exc, Exception)

    def test_preserva_chain_via_raise_from(self):
        """`raise FalhaDeColeta(...) from original` preserva __cause__."""
        original = RuntimeError("falha original")
        try:
            try:
                raise original
            except RuntimeError as exc:
                raise FalhaDeColeta(
                    fonte=FonteDado.CEMADEN,
                    causa="propaga",
                    original=exc,
                ) from exc
        except FalhaDeColeta as fc:
            assert fc.__cause__ is original
            assert fc.original is original

    def test_capturavel_como_exception(self):
        """pytest.raises(FalhaDeColeta) e pytest.raises(Exception) ambos funcionam."""
        with pytest.raises(FalhaDeColeta):
            raise FalhaDeColeta(fonte=FonteDado.CEMADEN, causa="x")
        with pytest.raises(Exception):
            raise FalhaDeColeta(fonte=FonteDado.CEMADEN, causa="x")
