"""Testes de scripts/weathernext_cemaden_capture.py — issue #70.

Rede sempre mockada (mesmo padrão de tests/sources/test_cemaden.py) — CI não
tem credencial/rede e não deve ter; suíte fica abaixo de 1s.
"""

from __future__ import annotations

import json
import os
import time
from unittest.mock import Mock, patch
from urllib.error import URLError

from alertavida.domain.enums import FonteDado
from alertavida.sources import FalhaDeColeta
from scripts import weathernext_cemaden_capture as cap
from scripts import weathernext_surge_watch as sw


def _opener_de_payload(payload_bytes: bytes):
    """Mesmo helper de tests/sources/test_cemaden.py."""
    response = Mock()
    response.read.return_value = payload_bytes
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    return Mock(return_value=context)


# ============================================================
# capture_dir — mesma convenção de database.db_path()
# ============================================================


class TestCaptureDir:
    def test_default_quando_env_ausente(self, monkeypatch):
        monkeypatch.delenv(cap.ENV_CAPTURE_DIR, raising=False)
        assert cap.capture_dir() == cap.CAPTURE_DIR_DEFAULT

    def test_env_sobrepoe_default(self, monkeypatch, tmp_path):
        alvo = tmp_path / "custom_captures"
        monkeypatch.setenv(cap.ENV_CAPTURE_DIR, str(alvo))
        assert cap.capture_dir() == alvo


# ============================================================
# em_modo_vigilancia
# ============================================================


class TestEmModoVigilancia:
    def test_artefato_ausente_retorna_falso(self, monkeypatch, tmp_path):
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(tmp_path / "nao_existe.json"))
        assert cap.em_modo_vigilancia() is False

    def test_artefato_ilegivel_retorna_falso(self, monkeypatch, tmp_path):
        caminho = tmp_path / "artefato.json"
        caminho.write_text("isso nao e json {{{", encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(caminho))
        assert cap.em_modo_vigilancia() is False

    def test_watch_mode_true_no_artefato(self, monkeypatch, tmp_path):
        caminho = tmp_path / "artefato.json"
        caminho.write_text(json.dumps({"watch_mode": True}), encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(caminho))
        assert cap.em_modo_vigilancia() is True

    def test_watch_mode_false_no_artefato(self, monkeypatch, tmp_path):
        caminho = tmp_path / "artefato.json"
        caminho.write_text(json.dumps({"watch_mode": False}), encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(caminho))
        assert cap.em_modo_vigilancia() is False

    def test_chave_ausente_retorna_falso(self, monkeypatch, tmp_path):
        caminho = tmp_path / "artefato.json"
        caminho.write_text(json.dumps({}), encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(caminho))
        assert cap.em_modo_vigilancia() is False


# ============================================================
# capturar_payload_bruto — transporte via fetch_com_retry, sem _montar_alerta
# ============================================================


class TestCapturarPayloadBruto:
    def test_grava_payload_cru_com_timestamp(self, monkeypatch, tmp_path):
        monkeypatch.setenv(cap.ENV_CAPTURE_DIR, str(tmp_path))
        payload = [{"cod_alerta": "1", "evento": "Risco Hidrológico - Alto"}]
        opener = _opener_de_payload(json.dumps(payload).encode("utf-8"))

        with patch("scripts.weathernext_cemaden_capture.opener_padrao", opener):
            destino = cap.capturar_payload_bruto()

        assert destino.parent == tmp_path
        assert destino.name.startswith("cemaden_raw_")
        assert json.loads(destino.read_text(encoding="utf-8")) == payload

    def test_falha_de_transporte_propaga_falha_de_coleta(self, monkeypatch, tmp_path):
        monkeypatch.setenv(cap.ENV_CAPTURE_DIR, str(tmp_path))
        # Mesmo padrão de tests/sources/test_cemaden.py: sem isso, o backoff
        # real de fetch_com_retry (2s+4s+8s) estouraria o limite de <1s da suíte.
        monkeypatch.setattr("alertavida.sources._http.time.sleep", lambda _: None)
        opener_com_erro = Mock(side_effect=URLError("rede indisponível"))

        with patch("scripts.weathernext_cemaden_capture.opener_padrao", opener_com_erro):
            try:
                cap.capturar_payload_bruto()
                assert False, "deveria ter levantado FalhaDeColeta"
            except FalhaDeColeta:
                pass


# ============================================================
# podar_capturas_antigas
# ============================================================


class TestPodarCapturasAntigas:
    def test_remove_apenas_arquivos_mais_antigos_que_a_retencao(self, tmp_path):
        antigo = tmp_path / "cemaden_raw_20000101T000000Z.json"
        recente = tmp_path / "cemaden_raw_20260101T000000Z.json"
        antigo.write_text("{}", encoding="utf-8")
        recente.write_text("{}", encoding="utf-8")

        agora = time.time()
        os.utime(antigo, (agora - 40 * 86400, agora - 40 * 86400))
        os.utime(recente, (agora, agora))

        removidos = cap.podar_capturas_antigas(tmp_path, dias_retencao=30)

        assert removidos == [antigo]
        assert not antigo.exists()
        assert recente.exists()

    def test_ignora_arquivos_fora_do_padrao_de_nome(self, tmp_path):
        outro = tmp_path / "algo_nao_relacionado.json"
        outro.write_text("{}", encoding="utf-8")
        agora = time.time()
        os.utime(outro, (agora - 999 * 86400, agora - 999 * 86400))

        removidos = cap.podar_capturas_antigas(tmp_path, dias_retencao=30)

        assert removidos == []
        assert outro.exists()


# ============================================================
# main
# ============================================================


class TestMain:
    def test_fora_de_vigilancia_nao_chama_rede(self, monkeypatch, tmp_path):
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(tmp_path / "nao_existe.json"))
        with patch.object(cap, "capturar_payload_bruto") as mock_captura:
            codigo = cap.main()
        assert codigo == 0
        mock_captura.assert_not_called()

    def test_em_vigilancia_captura_e_retorna_zero(self, monkeypatch, tmp_path):
        artefato = tmp_path / "artefato.json"
        artefato.write_text(json.dumps({"watch_mode": True}), encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(artefato))
        monkeypatch.setenv(cap.ENV_CAPTURE_DIR, str(tmp_path / "captures"))

        with patch.object(
            cap, "capturar_payload_bruto", return_value=tmp_path / "x.json"
        ) as mock_captura:
            codigo = cap.main()

        assert codigo == 0
        mock_captura.assert_called_once()

    def test_falha_de_coleta_retorna_codigo_de_erro(self, monkeypatch, tmp_path):
        artefato = tmp_path / "artefato.json"
        artefato.write_text(json.dumps({"watch_mode": True}), encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(artefato))

        with patch.object(
            cap,
            "capturar_payload_bruto",
            side_effect=FalhaDeColeta(fonte=FonteDado.CEMADEN, causa="rede fora"),
        ):
            codigo = cap.main()

        assert codigo == 1
