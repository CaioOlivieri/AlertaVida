"""Testes de scripts/analise_coordenada_cemaden.py (issue #136)."""

import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

from alertavida import database as db_module
from scripts.analise_coordenada_cemaden import (
    AlertaCoordenada,
    analisar_capturas,
    carregar_alertas_banco,
    classificar_municipios,
    main,
)


def _alerta(codibge: int, cod: str, lat: float, lon: float) -> AlertaCoordenada:
    return AlertaCoordenada(codibge, "M", "SP", cod, lat, lon)


class TestClassificarMunicipios:
    def test_municipio_com_um_alerta_nao_discrimina(self):
        assert classificar_municipios([_alerta(1, "a", -23.0, -46.0)]) == []

    def test_coordenadas_identicas(self):
        (r,) = classificar_municipios(
            [_alerta(1, "a", -23.0, -46.0), _alerta(1, "b", -23.0, -46.0)]
        )
        assert r.identicas
        assert r.pontos_distintos == 1
        assert r.espalhamento_km == 0.0

    def test_ruido_alem_da_nona_casa_conta_como_identico(self):
        (r,) = classificar_municipios(
            [_alerta(1, "a", -23.123456789001, -46.0), _alerta(1, "b", -23.123456789004, -46.0)]
        )
        assert r.identicas

    def test_coordenadas_variando_medem_o_espalhamento(self):
        (r,) = classificar_municipios(
            [_alerta(1, "a", -8.0, -34.88), _alerta(1, "b", -8.2, -34.88)]
        )
        assert not r.identicas
        assert r.espalhamento_km == pytest.approx(22.2, abs=0.1)

    def test_municipios_sao_separados_pelo_codigo(self):
        resultados = classificar_municipios(
            [
                _alerta(1, "a", -23.0, -46.0),
                _alerta(1, "b", -23.0, -46.0),
                _alerta(2, "c", -22.0, -43.0),
                _alerta(2, "d", -22.1, -43.0),
            ]
        )
        assert {(r.codibge, r.identicas) for r in resultados} == {(1, True), (2, False)}


class TestAnalisarCapturas:
    def _gravar(self, diretorio: Path, nome: str, itens: object) -> None:
        (diretorio / nome).write_text(json.dumps({"alertas": itens}), encoding="utf-8")

    def test_coordenada_estavel_e_alterada(self, tmp_path):
        self._gravar(tmp_path, "cemaden_raw_1.json", [
            {"cod_alerta": 1, "latitude": -23.0, "longitude": -46.0},
            {"cod_alerta": 2, "latitude": -22.0, "longitude": -43.0},
        ])
        self._gravar(tmp_path, "cemaden_raw_2.json", [
            {"cod_alerta": 1, "latitude": -23.0, "longitude": -46.0},
            {"cod_alerta": 2, "latitude": -22.5, "longitude": -43.0},
        ])
        r = analisar_capturas(tmp_path)
        assert (r.observacoes, r.alertas, r.alertas_com_coordenada_alterada) == (4, 2, 1)

    def test_arquivo_corrompido_ou_fora_do_formato_e_pulado(self, tmp_path):
        (tmp_path / "cemaden_raw_ruim.json").write_text("{", encoding="utf-8")
        self._gravar(tmp_path, "cemaden_raw_lista.json", "nao-e-lista")
        self._gravar(tmp_path, "cemaden_raw_ok.json", [
            {"cod_alerta": 1, "latitude": -23.0, "longitude": -46.0},
            {"cod_alerta": 2},  # item sem coordenada
        ])
        r = analisar_capturas(tmp_path)
        assert (r.observacoes, r.alertas) == (1, 1)


def _banco_com_alertas(caminho: Path, monkeypatch) -> None:
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(caminho))
    db_module.criar_banco()
    with contextlib.closing(sqlite3.connect(caminho)) as conexao:
        conexao.executemany(
            """
            INSERT INTO alertas (fonte, cod_alerta, municipio, uf, codibge,
                                 latitude, longitude, detectado_em)
            VALUES (?, ?, 'X', 'SP', ?, ?, ?, '2026-11-16T00:00:00+00:00')
            """,
            [
                ("CEMADEN", "1", 3550308, -23.65, -46.64),
                ("CEMADEN", "2", 3550308, -23.65, -46.64),
                ("CEMADEN", "3", None, -23.0, -46.0),  # sem município: fora
                ("EONET", "E1", None, -23.65, -46.64),  # outra fonte: fora
            ],
        )
        conexao.commit()


def test_carregar_alertas_banco_so_cemaden_com_municipio(tmp_path, monkeypatch):
    caminho = tmp_path / "copia.db"
    _banco_com_alertas(caminho, monkeypatch)
    assert sorted(a.cod_alerta for a in carregar_alertas_banco(caminho)) == ["1", "2"]


def test_main_imprime_o_relatorio(tmp_path, monkeypatch, capsys):
    caminho = tmp_path / "copia.db"
    _banco_com_alertas(caminho, monkeypatch)
    assert main(["--banco", str(caminho)]) == 0
    saida = capsys.readouterr().out
    assert "todas as coordenadas idênticas: 1" in saida
    assert "coordenadas variando: 0" in saida


def test_main_banco_ausente_falha(tmp_path, capsys):
    assert main(["--banco", str(tmp_path / "nao-existe.db")]) == 1
