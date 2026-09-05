"""Testes de scripts/weathernext_surge_watch.py — issue #70.

subprocess.run (bq) e o relógio são sempre mockados aqui — CI não tem
credencial GCP e não deve ter (regra da issue); suíte fica abaixo de 1s.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from scripts import weathernext_surge_watch as sw

# ============================================================
# artifact_path — mesma convenção de database.db_path()
# ============================================================


class TestArtifactPath:
    def test_default_quando_env_ausente(self, monkeypatch):
        monkeypatch.delenv(sw.ENV_ARTIFACT_PATH, raising=False)
        assert sw.artifact_path() == sw.ARTIFACT_PATH_DEFAULT

    def test_default_quando_env_em_branco(self, monkeypatch):
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, "   ")
        assert sw.artifact_path() == sw.ARTIFACT_PATH_DEFAULT

    def test_env_sobrepoe_default(self, monkeypatch, tmp_path):
        alvo = tmp_path / "custom.json"
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(alvo))
        assert sw.artifact_path() == alvo


# ============================================================
# ultimo_init_time_disponivel
# ============================================================


class TestUltimoInitTimeDisponivel:
    def test_escolhe_rodada_mais_recente_ja_publicada(self):
        # 2026-08-02 10:00 UTC: rodada 00z de hoje (00:00 + 7h30 = 07:30) já
        # publicou; 06z (06:00 + 7h30 = 13:30) ainda não.
        agora = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
        assert sw.ultimo_init_time_disponivel(agora) == datetime(
            2026, 8, 2, 0, 0, tzinfo=timezone.utc
        )

    def test_logo_apos_meia_noite_cai_na_rodada_12z_de_ontem(self):
        # 2026-08-02 00:10 UTC: nem 00z de hoje (00:00+7h30=07:30) nem 18z de
        # ontem (18:00+7h30=01:30 do dia seguinte) publicaram ainda; a última
        # disponível é 12z de ontem (12:00+7h30=19:30 de ontem).
        agora = datetime(2026, 8, 2, 0, 10, tzinfo=timezone.utc)
        assert sw.ultimo_init_time_disponivel(agora) == datetime(
            2026, 8, 1, 12, 0, tzinfo=timezone.utc
        )

    def test_exatamente_no_limite_de_publicacao_conta_como_disponivel(self):
        # candidato + 7h30 == agora -> "<=", inclusivo.
        agora = datetime(2026, 8, 2, 7, 30, tzinfo=timezone.utc)
        assert sw.ultimo_init_time_disponivel(agora) == datetime(
            2026, 8, 2, 0, 0, tzinfo=timezone.utc
        )

    def test_um_segundo_antes_do_limite_ainda_nao_conta(self):
        agora = datetime(2026, 8, 2, 7, 29, 59, tzinfo=timezone.utc)
        assert sw.ultimo_init_time_disponivel(agora) == datetime(
            2026, 8, 1, 18, 0, tzinfo=timezone.utc
        )


# ============================================================
# montar_query
# ============================================================


class TestMontarQuery:
    def test_query_contem_tabela_bbox_e_janela(self):
        init_time = datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)
        inicio = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
        fim = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
        sql = sw.montar_query(init_time, inicio, fim)

        assert f"`{sw.PROJECT}.{sw.DATASET}.{sw.TABLE}`" in sql
        assert 'init_time = TIMESTAMP("2026-08-02 00:00:00")' in sql
        assert "ST_INTERSECTSBOX(geography," in sql
        assert 'f.time >= TIMESTAMP("2026-08-02 10:00:00")' in sql
        assert 'f.time <  TIMESTAMP("2026-08-04 10:00:00")' in sql


# ============================================================
# executar_query_bq — distingue guarda de custo de falha real
# ============================================================


class TestExecutarQueryBq:
    def test_sucesso_retorna_linhas_parseadas(self):
        linhas_json = json.dumps(
            [{"geography": "POINT(-43.0 -22.0)", "valid_time": "x", "precip_6hr": "0.01"}]
        )
        fake = Mock(returncode=0, stdout=linhas_json, stderr="")
        with patch("subprocess.run", return_value=fake) as mock_run:
            resultado = sw.executar_query_bq("SELECT 1")

        esperado = [{"geography": "POINT(-43.0 -22.0)", "valid_time": "x", "precip_6hr": "0.01"}]
        assert resultado == esperado
        args = mock_run.call_args.args[0]
        assert args[0:2] == ["bq", "query"]
        assert f"--maximum_bytes_billed={sw.MAXIMUM_BYTES_BILLED}" in args
        assert f"--max_rows={sw.MAX_ROWS}" in args

    def test_perto_do_teto_de_max_rows_loga_aviso(self, monkeypatch, caplog):
        # bq --max_rows trunca em silêncio; este teste garante que ficar perto
        # do teto deixa um sinal (log), não apenas um retorno "normal" menor.
        # MAX_ROWS reduzido só neste teste (razão real preservada) para não
        # serializar/parsear uma lista de centenas de milhares de itens.
        monkeypatch.setattr(sw, "MAX_ROWS", 10)
        linha = {"geography": "POINT(0 0)", "valid_time": "x", "precip_6hr": "0.0"}
        quase_no_teto = int(sw.MAX_ROWS * sw.MAX_ROWS_WARNING_RATIO)
        linhas_json = json.dumps([linha] * quase_no_teto)
        fake = Mock(returncode=0, stdout=linhas_json, stderr="")

        with patch("subprocess.run", return_value=fake):
            with caplog.at_level("WARNING"):
                resultado = sw.executar_query_bq("SELECT 1")

        assert len(resultado) == quase_no_teto
        assert any("truncamento" in registro.message for registro in caplog.records)

    def test_bem_abaixo_do_teto_nao_loga_aviso(self, caplog):
        linhas_json = json.dumps([{"geography": "POINT(0 0)", "precip_6hr": "0.0"}])
        fake = Mock(returncode=0, stdout=linhas_json, stderr="")

        with patch("subprocess.run", return_value=fake):
            with caplog.at_level("WARNING"):
                sw.executar_query_bq("SELECT 1")

        assert not any("truncamento" in registro.message for registro in caplog.records)

    def test_sucesso_sem_linhas_retorna_lista_vazia(self):
        fake = Mock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=fake):
            assert sw.executar_query_bq("SELECT 1") == []

    def test_guarda_de_custo_disparado_levanta_orcamento_excedido(self):
        # Texto verificado empiricamente contra bq real em 2026-09-05 (ver
        # docstring de OrcamentoExcedidoError) — não é um mock inventado.
        stderr_real = (
            "BigQuery error in query operation: Error processing job "
            "'weathernexttest-506315:bqjob_xxx': Query exceeded limit for "
            "bytes billed: 100. 33554432 or higher required."
        )
        fake = Mock(returncode=1, stdout="", stderr=stderr_real)
        with patch("subprocess.run", return_value=fake):
            with pytest.raises(sw.OrcamentoExcedidoError):
                sw.executar_query_bq("SELECT 1")

    def test_falha_de_autenticacao_propaga_como_called_process_error(self):
        fake = Mock(
            returncode=1,
            stdout="",
            stderr="BigQuery error: authentication error, please run `gcloud auth login`.",
        )
        with patch("subprocess.run", return_value=fake):
            with pytest.raises(subprocess.CalledProcessError):
                sw.executar_query_bq("SELECT 1")


# ============================================================
# indicador_por_regiao — soma m -> mm por célula
# ============================================================


class TestIndicadorPorRegiao:
    def test_soma_passos_da_mesma_celula_e_converte_para_mm(self):
        linhas = [
            {"geography": "POINT(-43.0 -22.0)", "precip_6hr": "0.010"},
            {"geography": "POINT(-43.0 -22.0)", "precip_6hr": "0.005"},
            {"geography": "POINT(-40.0 -20.0)", "precip_6hr": "0.001"},
        ]
        indicador = sw.indicador_por_regiao(linhas)
        assert indicador["POINT(-43.0 -22.0)"] == pytest.approx(15.0)
        assert indicador["POINT(-40.0 -20.0)"] == pytest.approx(1.0)

    def test_lista_vazia_retorna_dict_vazio(self):
        assert sw.indicador_por_regiao([]) == {}


# ============================================================
# montar_artefato — limiar, watch_mode, atribuição
# ============================================================


class TestMontarArtefato:
    def _artefato(self, indicador):
        return sw.montar_artefato(
            init_time=datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc),
            gerado_em=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
            indicador=indicador,
        )

    def test_watch_mode_falso_quando_nada_cruza_limiar(self):
        artefato = self._artefato({"POINT(-43.0 -22.0)": sw.SURGE_WATCH_THRESHOLD_MM_48H - 0.01})
        assert artefato["watch_mode"] is False
        assert artefato["regions_at_risk"] == {}

    def test_watch_mode_verdadeiro_quando_uma_celula_cruza_limiar(self):
        artefato = self._artefato({"POINT(-43.0 -22.0)": sw.SURGE_WATCH_THRESHOLD_MM_48H + 0.01})
        assert artefato["watch_mode"] is True
        assert "POINT(-43.0 -22.0)" in artefato["regions_at_risk"]

    def test_limiar_exato_conta_como_em_risco(self):
        artefato = self._artefato({"POINT(-43.0 -22.0)": sw.SURGE_WATCH_THRESHOLD_MM_48H})
        assert artefato["watch_mode"] is True

    def test_atribuicao_e_aviso_experimental_embutidos(self):
        artefato = self._artefato({})
        assert "experimental" in artefato["attribution"].lower()
        assert "CC BY" in artefato["attribution"]
        assert artefato["threshold_is_provisional"] is True

    def test_regions_evaluated_conta_todas_nao_so_as_em_risco(self):
        artefato = self._artefato(
            {"POINT(-43.0 -22.0)": 1.0, "POINT(-40.0 -20.0)": sw.SURGE_WATCH_THRESHOLD_MM_48H + 1}
        )
        assert artefato["regions_evaluated"] == 2
        assert len(artefato["regions_at_risk"]) == 1


# ============================================================
# main — fim a fim, com bq e artefato mockados
# ============================================================


class TestMain:
    def test_escreve_artefato_em_execucao_bem_sucedida(self, monkeypatch, tmp_path):
        destino = tmp_path / "artefato.json"
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(destino))

        linhas_json = json.dumps(
            [{"geography": "POINT(-43.0 -22.0)", "valid_time": "x", "precip_6hr": "0.001"}]
        )
        fake = Mock(returncode=0, stdout=linhas_json, stderr="")

        with patch("subprocess.run", return_value=fake):
            codigo = sw.main()

        assert codigo == 0
        assert destino.exists()
        artefato = json.loads(destino.read_text(encoding="utf-8"))
        assert artefato["watch_mode"] is False
        assert artefato["regions_evaluated"] == 1

    def test_guarda_de_custo_nao_falha_o_processo_e_nao_toca_artefato(self, monkeypatch, tmp_path):
        destino = tmp_path / "artefato.json"
        destino.write_text('{"marca": "artefato anterior"}', encoding="utf-8")
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(destino))

        fake = Mock(
            returncode=1,
            stdout="",
            stderr="Query exceeded limit for bytes billed: 1. 2 or higher required.",
        )
        with patch("subprocess.run", return_value=fake):
            codigo = sw.main()

        assert codigo == 0
        assert json.loads(destino.read_text(encoding="utf-8")) == {"marca": "artefato anterior"}

    def test_falha_real_do_bq_retorna_codigo_de_erro(self, monkeypatch, tmp_path):
        monkeypatch.setenv(sw.ENV_ARTIFACT_PATH, str(tmp_path / "artefato.json"))
        fake = Mock(returncode=1, stdout="", stderr="authentication error")
        with patch("subprocess.run", return_value=fake):
            codigo = sw.main()
        assert codigo == 1
