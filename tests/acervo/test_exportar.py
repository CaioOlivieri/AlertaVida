"""Exportação do acervo a partir de um backup (issue #158)."""

import contextlib
import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alertavida import database as db_module
from alertavida.acervo.exportar import (
    ALERTAS,
    COBERTURA,
    TABELAS,
    Coleta,
    calcular_cobertura,
    escolher_backup,
    exportar,
    gerar_dicionario,
    instante_do_backup,
)
from alertavida.domain.aviso import AvisoMeteorologico, SeveridadeAviso

RJ, SP = 3304557, 3550308
NOME_BACKUP = "alertavida-20261124T000500Z.db"


def _utc(texto: str) -> datetime:
    return datetime.fromisoformat(texto).astimezone(UTC)


def _inserir_alerta(conexao, id_, cod, codibge, inicio, status="ATIVO"):
    conexao.execute(
        """
        INSERT INTO alertas (
            id, fonte, cod_alerta, municipio, uf, evento, nivel, datahoracriacao,
            detectado_em, codibge, latitude, longitude, escopo_geografico,
            ult_atualizacao, status_interno, visto_ultima_vez, cobrade_codigo,
            fonte_classificacao
        ) VALUES (?, 'CEMADEN', ?, 'M', 'RJ', 'HIDROLOGICO', 'MODERADO', ?, ?, ?,
                  -22.9, -43.4, 'BRASIL', ?, ?, ?, '1.2.0.0.0', 'MAPEADA_POR_NOME')
        """,
        (id_, cod, inicio, inicio, codibge, inicio, status, inicio),
    )


@pytest.fixture
def backup(tmp_path, monkeypatch) -> Path:
    """Um banco com o schema real, dois alertas, um aviso e duas rodadas,
    salvo com o nome que deploy/backup.py usa."""
    caminho = tmp_path / "backups" / NOME_BACKUP
    caminho.parent.mkdir()
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(caminho))
    db_module.criar_banco()
    db_module.registrar_avisos(
        [
            AvisoMeteorologico(
                codigo_cap="urn:oid:2.49.0.0.76.0.2026.1.1",
                id_aviso=1,
                id_sequencia=1,
                evento="Tempestade",
                severidade=SeveridadeAviso.PERIGO,
                inicio=_utc("2026-11-23T12:00:00+00:00"),
                fim=_utc("2026-11-24T02:59:00+00:00"),
                codigos_ibge=frozenset({RJ, SP}),
                encerrado=False,
            )
        ],
        "2026-11-23T13:46:19.807354+00:00",
    )
    with contextlib.closing(sqlite3.connect(caminho)) as conexao:
        _inserir_alerta(conexao, 1, "A1", RJ, "2026-11-23T15:00:00.730000+00:00")
        _inserir_alerta(conexao, 2, "A2", SP, "2026-11-22T10:00:00+00:00", "RESOLVIDO")
        conexao.execute(
            "INSERT INTO eventos (tipo, agregado_id, payload, criado_em) "
            "VALUES ('AlertaResolvido', 2, '{}', '2026-11-22T11:00:00+00:00')"
        )
        conexao.commit()
    db_module.registrar_rodada(
        "2026-11-23T23:56:17.000001+00:00",
        "2026-11-23T23:56:18+00:00",
        [("CEMADEN", 30), ("EONET", None)],
    )
    db_module.registrar_rodada(
        "2026-11-24T00:01:17+00:00", "2026-11-24T00:01:18+00:00", [("CEMADEN", None)]
    )
    return caminho


def _ler(diretorio: Path, arquivo: str) -> list[dict[str, str]]:
    with (diretorio / arquivo).open(encoding="utf-8", newline="") as entrada:
        return list(csv.DictReader(entrada))


class TestExportar:
    def test_alertas_em_utc_com_resolucao(self, backup, tmp_path):
        saida = tmp_path / "export"
        exportar(backup, saida, [])
        alertas = _ler(saida, ALERTAS.arquivo)
        assert [a["cod_alerta"] for a in alertas] == ["A2", "A1"]  # ordem de início
        assert alertas[1]["inicio_utc"] == "2026-11-23T15:00:00Z"
        assert alertas[0]["resolucao_detectada_utc"] == "2026-11-22T11:00:00Z"
        assert alertas[1]["resolucao_detectada_utc"] == ""

    def test_anotacao_usa_a_regra_de_avisos_vigentes(self, backup, tmp_path):
        saida = tmp_path / "export"
        exportar(backup, saida, [])
        # A1 começou dentro da validade do aviso; A2, antes dela.
        assert _ler(saida, "alerta_avisos.csv") == [
            {
                "cod_alerta": "A1",
                "codigo_cap": "urn:oid:2.49.0.0.76.0.2026.1.1",
                "evento": "Tempestade",
                "severidade": "PERIGO",
            }
        ]
        assert len(_ler(saida, "aviso_municipios.csv")) == 2
        assert _ler(saida, "avisos_inmet.csv")[0]["municipios"] == "2"

    def test_mesmo_backup_mesmos_bytes(self, backup, tmp_path):
        exportar(backup, tmp_path / "a", [])
        exportar(backup, tmp_path / "b", [])
        arquivos = sorted(p.name for p in (tmp_path / "a").iterdir())
        assert arquivos == sorted(p.name for p in (tmp_path / "b").iterdir())
        for nome in arquivos:
            assert (tmp_path / "a" / nome).read_bytes() == (tmp_path / "b" / nome).read_bytes()

    def test_nao_altera_o_backup(self, backup, tmp_path):
        antes = backup.read_bytes()
        exportar(backup, tmp_path / "export", [])
        assert backup.read_bytes() == antes
        assert sorted(p.name for p in backup.parent.iterdir()) == [NOME_BACKUP]

    def test_metadados_identificam_o_backup(self, backup, tmp_path):
        metadados = exportar(backup, tmp_path / "export", [])
        gravado = json.loads((tmp_path / "export" / "metadados.json").read_text("utf-8"))
        assert gravado == metadados
        assert gravado["backup"] == NOME_BACKUP
        assert gravado["linhas"][ALERTAS.arquivo] == 2

    def test_saida_anterior_e_substituida(self, backup, tmp_path):
        saida = tmp_path / "export"
        saida.mkdir()
        (saida / "velho.csv").write_text("x", encoding="utf-8")
        exportar(backup, saida, [])
        assert not (saida / "velho.csv").exists()
        assert not (tmp_path / "export.tmp").exists()

    def test_cobertura_junta_journal_e_tabela(self, backup, tmp_path):
        historico = tmp_path / "rodadas-journal-x.csv"
        historico.write_text(
            "instante_utc,fonte,coletados,falha\n2026-11-23T23:51:17Z,CEMADEN,30,0\n",
            encoding="utf-8",
        )
        saida = tmp_path / "export"
        exportar(backup, saida, [historico])
        cobertura = {(c["dia"], c["fonte"]): c for c in _ler(saida, COBERTURA.arquivo)}
        dia23 = cobertura[("2026-11-23", "CEMADEN")]
        # Período conhecido começa em 23:50 → janelas 23:50 e 23:55, ambas com coleta.
        assert (dia23["janelas_possiveis"], dia23["janelas_com_coleta"]) == ("2", "2")
        dia24 = cobertura[("2026-11-24", "CEMADEN")]
        # 00:00–00:05 terminou às 00:05 (instante do backup) e só teve falha.
        assert (dia24["janelas_possiveis"], dia24["janelas_com_coleta"]) == ("1", "0")
        assert dia24["coletas_com_falha"] == "1"

    def test_backup_sem_tabela_rodadas(self, backup, tmp_path):
        with contextlib.closing(sqlite3.connect(backup)) as conexao:
            conexao.execute("DROP TABLE rodadas")
            conexao.commit()
        exportar(backup, tmp_path / "export", [])
        assert _ler(tmp_path / "export", COBERTURA.arquivo) == []


class TestCobertura:
    def test_janela_em_curso_nao_conta(self):
        coletas = [Coleta(_utc("2026-11-24T00:11:00+00:00"), "INMET", False)]
        # Às 00:20 a janela 00:00–00:30 ainda não terminou: nada a medir.
        assert list(calcular_cobertura(coletas, _utc("2026-11-24T00:20:00+00:00"))) == []

    def test_duas_coletas_na_mesma_janela_contam_uma(self):
        coletas = [
            Coleta(_utc("2026-11-24T00:00:10+00:00"), "CEMADEN", False),
            Coleta(_utc("2026-11-24T00:04:50+00:00"), "CEMADEN", False),
        ]
        linhas = list(calcular_cobertura(coletas, _utc("2026-11-24T00:10:00+00:00")))
        assert linhas == [["2026-11-24", "CEMADEN", 2, 1, "0.5000", 0]]

    def test_fonte_sem_janela_definida_e_ignorada(self):
        coletas = [Coleta(_utc("2026-11-24T00:00:10+00:00"), "EONET", False)]
        assert list(calcular_cobertura(coletas, _utc("2026-11-25T00:00:00+00:00"))) == []


class TestBackup:
    def test_instante_vem_do_nome(self):
        assert instante_do_backup(Path(NOME_BACKUP)) == _utc("2026-11-24T00:05:00+00:00")

    def test_nome_fora_do_padrao_e_recusado(self):
        with pytest.raises(ValueError):
            instante_do_backup(Path("copia.db"))

    def test_diretorio_escolhe_o_mais_recente(self, tmp_path):
        for nome in ("alertavida-20261122T171551Z.db", NOME_BACKUP, "outro.db"):
            (tmp_path / nome).write_bytes(b"")
        assert escolher_backup(tmp_path).name == NOME_BACKUP

    def test_diretorio_sem_backup(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            escolher_backup(tmp_path)


def test_dicionario_documenta_toda_coluna():
    dicionario = gerar_dicionario()
    for tabela in TABELAS:
        assert f"## `{tabela.arquivo}`" in dicionario
        for coluna in tabela.colunas:
            assert f"| `{coluna.nome}` |" in dicionario
    assert "não é um canal oficial de alerta" in dicionario
