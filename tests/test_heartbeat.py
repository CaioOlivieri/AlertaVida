"""Testes de deploy/heartbeat.py (issue #141)."""

import contextlib
import importlib.util
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "heartbeat", Path(__file__).resolve().parent.parent / "deploy" / "heartbeat.py"
)
assert _SPEC is not None and _SPEC.loader is not None
heartbeat = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(heartbeat)

AGORA = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)


class TestAvaliar:
    def test_rodada_recente_e_saudavel(self):
        saudavel, msg = heartbeat.avaliar(AGORA - timedelta(minutes=4), AGORA)
        assert saudavel
        assert "4.0 min" in msg

    def test_exatamente_no_limite_ainda_e_saudavel(self):
        assert heartbeat.avaliar(AGORA - timedelta(minutes=15), AGORA)[0]

    def test_rodada_antiga_falha(self):
        saudavel, msg = heartbeat.avaliar(AGORA - timedelta(minutes=16), AGORA)
        assert not saudavel
        assert "limite 15 min" in msg

    def test_sem_rodada_registrada_falha(self):
        assert heartbeat.avaliar(None, AGORA) == (
            False,
            "nenhuma rodada registrada (tabela alertas vazia)",
        )


class TestUrlDoPing:
    def test_saudavel_usa_a_url_base(self):
        assert heartbeat.url_do_ping("https://hc-ping.com/abc/", True) == "https://hc-ping.com/abc"

    def test_falha_usa_o_sufixo_fail(self):
        assert heartbeat.url_do_ping("https://hc-ping.com/abc", False) == "https://hc-ping.com/abc/fail"

    def test_recusa_url_sem_https(self):
        with pytest.raises(ValueError):
            heartbeat.url_do_ping("http://hc-ping.com/abc", True)


class TestUltimaRodada:
    def _banco(self, caminho: Path, valores: list[str]) -> None:
        with contextlib.closing(sqlite3.connect(caminho)) as conexao:
            conexao.execute("CREATE TABLE alertas (visto_ultima_vez TEXT)")
            conexao.executemany("INSERT INTO alertas VALUES (?)", [(v,) for v in valores])
            conexao.commit()

    def test_le_o_maior_carimbo(self, tmp_path):
        caminho = tmp_path / "a.db"
        self._banco(caminho, ["2026-11-22T17:50:00+00:00", "2026-11-22T17:55:00+00:00"])
        assert heartbeat.ultima_rodada(caminho) == datetime(
            2026, 11, 22, 17, 55, tzinfo=timezone.utc
        )

    def test_tabela_vazia_devolve_none(self, tmp_path):
        caminho = tmp_path / "a.db"
        self._banco(caminho, [])
        assert heartbeat.ultima_rodada(caminho) is None


class TestMain:
    def test_sem_url_configurada_sai_com_erro(self, monkeypatch, capsys):
        monkeypatch.delenv("HEARTBEAT_URL", raising=False)
        assert heartbeat.main() == 1
        assert "HEARTBEAT_URL ausente" in capsys.readouterr().err

    def test_banco_ilegivel_envia_fail(self, tmp_path, monkeypatch):
        enviados = []
        monkeypatch.setenv("HEARTBEAT_URL", "https://hc-ping.com/abc")
        monkeypatch.setenv("ALERTAVIDA_DB_PATH", str(tmp_path / "nao-existe.db"))
        monkeypatch.setattr(heartbeat, "enviar", lambda url, msg: enviados.append((url, msg)))
        assert heartbeat.main() == 1
        assert enviados[0][0] == "https://hc-ping.com/abc/fail"
        assert "banco ilegivel" in enviados[0][1]

    def test_banco_saudavel_envia_ping(self, tmp_path, monkeypatch, capsys):
        caminho = tmp_path / "a.db"
        recente = datetime.now(timezone.utc) - timedelta(minutes=2)
        self_banco = TestUltimaRodada()._banco
        self_banco(caminho, [recente.isoformat()])
        enviados = []
        monkeypatch.setenv("HEARTBEAT_URL", "https://hc-ping.com/abc")
        monkeypatch.setenv("ALERTAVIDA_DB_PATH", str(caminho))
        monkeypatch.setattr(heartbeat, "enviar", lambda url, msg: enviados.append((url, msg)))
        assert heartbeat.main() == 0
        assert enviados[0][0] == "https://hc-ping.com/abc"
        assert "HEARTBEAT OK" in capsys.readouterr().out
