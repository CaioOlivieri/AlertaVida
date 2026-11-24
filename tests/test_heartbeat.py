"""Testes de deploy/heartbeat.py (issues #141, #166)."""

import contextlib
import importlib.util
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from alertavida import database as db_module

_SPEC = importlib.util.spec_from_file_location(
    "heartbeat", Path(__file__).resolve().parent.parent / "deploy" / "heartbeat.py"
)
assert _SPEC is not None and _SPEC.loader is not None
heartbeat = importlib.util.module_from_spec(_SPEC)
# dataclasses resolve annotations through sys.modules[cls.__module__].
sys.modules["heartbeat"] = heartbeat
_SPEC.loader.exec_module(heartbeat)

AGORA = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
URL = "https://hc-ping.com/coletor"
URL_CEMADEN = "https://hc-ping.com/cemaden"


def _ha(minutos: float) -> datetime:
    return AGORA - timedelta(minutes=minutos)


class TestAvaliarColetor:
    def test_rodada_recente_e_saudavel(self):
        saudavel, msg = heartbeat.avaliar_coletor(_ha(14), AGORA)
        assert saudavel and "14.0 min" in msg

    def test_exatamente_no_limite_ainda_e_saudavel(self):
        assert heartbeat.avaliar_coletor(_ha(15), AGORA)[0]

    def test_rodada_antiga_falha(self):
        saudavel, msg = heartbeat.avaliar_coletor(_ha(16), AGORA)
        assert not saudavel and "limite 15 min" in msg

    def test_sem_rodada_registrada_falha(self):
        assert heartbeat.avaliar_coletor(None, AGORA) == (
            False,
            "nenhuma rodada registrada (tabela rodadas vazia)",
        )


class TestAvaliarCemaden:
    def test_coleta_recente_e_saudavel(self):
        saudavel, msg = heartbeat.avaliar_cemaden(_ha(59), _ha(1), AGORA)
        assert saudavel and "59.0 min" in msg

    def test_falhando_com_coletor_vivo_diz_que_e_do_cemaden(self):
        saudavel, msg = heartbeat.avaliar_cemaden(_ha(61), _ha(2), AGORA)
        assert not saudavel
        assert "CEMADEN falhando desde 2026-11-24T16:59Z" in msg
        assert "o coletor esta rodando" in msg

    def test_sem_rodadas_aponta_para_o_check_do_coletor(self):
        saudavel, msg = heartbeat.avaliar_cemaden(_ha(90), _ha(90), AGORA)
        assert not saudavel and msg.startswith("sem rodadas — ver o check do coletor")

    def test_nunca_coletou(self):
        saudavel, msg = heartbeat.avaliar_cemaden(None, _ha(1), AGORA)
        assert not saudavel and "sem coleta bem-sucedida registrada" in msg


class TestUrlDoPing:
    def test_saudavel_usa_a_url_base(self):
        assert heartbeat.url_do_ping("https://hc-ping.com/abc/", True) == "https://hc-ping.com/abc"

    def test_falha_usa_o_sufixo_fail(self):
        assert heartbeat.url_do_ping("https://hc-ping.com/abc", False) == "https://hc-ping.com/abc/fail"

    def test_recusa_url_sem_https(self):
        with pytest.raises(ValueError):
            heartbeat.url_do_ping("http://hc-ping.com/abc", True)


@pytest.fixture
def banco(tmp_path, monkeypatch) -> Path:
    """O schema real (criar_banco), para o heartbeat ler o mesmo `rodadas`."""
    caminho = tmp_path / "a.db"
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(caminho))
    db_module.criar_banco()
    return caminho


def _rodada(instante: datetime, cemaden: int | None, eonet: int | None = 80) -> None:
    db_module.registrar_rodada(
        instante.isoformat(), instante.isoformat(), [("CEMADEN", cemaden), ("EONET", eonet)]
    )


class TestLerInstantes:
    def test_rodada_mais_recente_e_ultima_coleta_ok_do_cemaden(self, banco):
        _rodada(_ha(30), 20)
        _rodada(_ha(10), None)  # CEMADEN falhou, EONET ok
        _rodada(_ha(5).replace(microsecond=0), None)
        instantes = heartbeat.ler_instantes(banco)
        assert instantes.ultima_rodada == _ha(5).replace(microsecond=0)
        assert instantes.ultima_coleta_cemaden == _ha(30)

    def test_segundo_sem_fracao_ordena_antes_do_mesmo_segundo_com_fracao(self, banco):
        inteiro = _ha(5).replace(microsecond=0)
        _rodada(inteiro + timedelta(microseconds=1), 20)
        _rodada(inteiro, 20)
        assert heartbeat.ler_instantes(banco).ultima_rodada == inteiro + timedelta(microseconds=1)

    def test_tabela_vazia(self, banco):
        assert heartbeat.ler_instantes(banco) == heartbeat.Instantes(None, None)

    def test_sem_tabela_rodadas_levanta(self, tmp_path):
        caminho = tmp_path / "velho.db"
        with contextlib.closing(sqlite3.connect(caminho)) as conexao:
            conexao.execute("CREATE TABLE alertas (visto_ultima_vez TEXT)")
            conexao.commit()
        with pytest.raises(sqlite3.Error):
            heartbeat.ler_instantes(caminho)


class TestAvaliar:
    def test_erro_de_banco_derruba_os_dois(self):
        resultados = heartbeat.avaliar(None, "banco ilegivel em x", AGORA)
        assert [(r.nome, r.saudavel) for r in resultados] == [
            ("coletor", False),
            ("CEMADEN", False),
        ]

    def test_coletor_vivo_e_cemaden_fora(self):
        instantes = heartbeat.Instantes(ultima_rodada=_ha(2), ultima_coleta_cemaden=_ha(85))
        assert [(r.nome, r.saudavel) for r in heartbeat.avaliar(instantes, None, AGORA)] == [
            ("coletor", True),
            ("CEMADEN", False),
        ]


class TestMain:
    @pytest.fixture
    def enviados(self, monkeypatch, banco):
        lista: list[tuple[str, str]] = []
        monkeypatch.setenv("ALERTAVIDA_DB_PATH", str(banco))
        monkeypatch.setenv("HEARTBEAT_URL", URL)
        monkeypatch.setenv("HEARTBEAT_URL_CEMADEN", URL_CEMADEN)
        monkeypatch.setattr(heartbeat, "enviar", lambda url, msg: lista.append((url, msg)))
        return lista

    def test_sem_url_do_coletor_sai_com_erro(self, monkeypatch, capsys):
        monkeypatch.delenv("HEARTBEAT_URL", raising=False)
        assert heartbeat.main() == 1
        assert "HEARTBEAT_URL ausente" in capsys.readouterr().err

    def test_tudo_saudavel_pinga_as_duas_urls(self, enviados, capsys):
        _rodada(datetime.now(timezone.utc) - timedelta(minutes=2), 20)
        assert heartbeat.main() == 0
        assert [url for url, _ in enviados] == [URL, URL_CEMADEN]
        saida = capsys.readouterr().out
        assert "HEARTBEAT coletor OK" in saida and "HEARTBEAT CEMADEN OK" in saida

    def test_cemaden_fora_falha_so_o_check_dele(self, enviados):
        agora = datetime.now(timezone.utc)
        _rodada(agora - timedelta(minutes=90), 20)
        _rodada(agora - timedelta(minutes=2), None)
        assert heartbeat.main() == 1
        assert [url for url, _ in enviados] == [URL, URL_CEMADEN + "/fail"]

    def test_sem_url_do_cemaden_pula_o_check(self, enviados, monkeypatch, capsys):
        monkeypatch.delenv("HEARTBEAT_URL_CEMADEN")
        _rodada(datetime.now(timezone.utc) - timedelta(minutes=2), None)
        assert heartbeat.main() == 0  # CEMADEN fora, mas o check dele não existe
        assert [url for url, _ in enviados] == [URL]
        assert "HEARTBEAT CEMADEN PULADO" in capsys.readouterr().out

    def test_um_ping_que_falha_nao_impede_o_outro(self, enviados, monkeypatch, capsys):
        _rodada(datetime.now(timezone.utc) - timedelta(minutes=2), 20)

        def enviar(url, msg):
            if url == URL:
                raise OSError("rede")
            enviados.append((url, msg))

        monkeypatch.setattr(heartbeat, "enviar", enviar)
        assert heartbeat.main() == 1
        assert [url for url, _ in enviados] == [URL_CEMADEN]
        assert "ping coletor falhou: rede" in capsys.readouterr().err

    def test_banco_ilegivel_envia_fail_nos_dois(self, enviados, monkeypatch, tmp_path):
        monkeypatch.setenv("ALERTAVIDA_DB_PATH", str(tmp_path / "nao-existe.db"))
        assert heartbeat.main() == 1
        assert [url for url, _ in enviados] == [URL + "/fail", URL_CEMADEN + "/fail"]
        assert "banco ilegivel" in enviados[0][1]
