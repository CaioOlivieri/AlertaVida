"""Site estático gerado da exportação (issue #158)."""

import re
from pathlib import Path

import pytest

from alertavida.acervo.exportar import TABELAS, exportar
from alertavida.acervo.site import em_brasilia, gerar_site, nome_proprio
from tests.acervo._banco import RJ, SP, criar_backup

_HREF = re.compile(r'(?:href|src)="([^"]+)"')


def _gerar(tmp_path, monkeypatch, municipio_a1="RIO DE JANEIRO") -> Path:
    backup = criar_backup(tmp_path / "backups", monkeypatch, municipio_a1)
    exportar(backup, tmp_path / "export", [])
    gerar_site(tmp_path / "export", tmp_path / "site")
    return tmp_path / "site"


def _paginas(site: Path) -> list[Path]:
    return sorted(site.rglob("*.html"))


@pytest.fixture
def site(tmp_path, monkeypatch) -> Path:
    return _gerar(tmp_path, monkeypatch)


class TestEstrutura:
    def test_uma_pagina_por_municipio_mais_index_e_dados(self, site):
        nomes = sorted(p.relative_to(site).as_posix() for p in _paginas(site))
        assert nomes == ["dados.html", "index.html", f"municipio/{RJ}.html", f"municipio/{SP}.html"]

    def test_todo_link_e_relativo_e_existe(self, site):
        for pagina in _paginas(site):
            for alvo in _HREF.findall(pagina.read_text(encoding="utf-8")):
                assert not alvo.startswith(("/", "http:", "https:")), (pagina, alvo)
                assert (pagina.parent / alvo).resolve().is_file(), (pagina, alvo)

    def test_toda_pagina_avisa_que_nao_e_canal_oficial(self, site):
        for pagina in _paginas(site):
            html = pagina.read_text(encoding="utf-8")
            assert "não é um canal oficial de alerta" in html, pagina
            assert "199" in html and "40199" in html, pagina

    def test_toda_pagina_cabe_no_celular(self, site):
        """Viewport declarado, coluna com largura máxima e margem de 16 px, e
        nenhuma tabela (os alertas são listas) — nada força rolagem lateral.
        A verificação visual em 360 px é feita num Chromium isolado (PR)."""
        for pagina in _paginas(site):
            html = pagina.read_text(encoding="utf-8")
            assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
            assert "<table" not in html, pagina
        css = (site / "estilo.css").read_text(encoding="utf-8")
        assert "max-width: var(--medida)" in css and "padding: 0 16px" in css

    def test_procedencia_tecnica_so_na_pagina_de_dados(self, site, tmp_path):
        """O visitante lê quando os dados foram atualizados; nome e SHA-256 do
        backup ficam em Dados, para quem precisa rastrear."""
        import json

        sha = json.loads((tmp_path / "export" / "metadados.json").read_text("utf-8"))[
            "backup_sha256"
        ]
        for pagina in _paginas(site):
            html = pagina.read_text(encoding="utf-8")
            assert "Dados atualizados em 23/11/2026, 21:05 (horário de Brasília)" in html
            assert (sha in html) == (pagina.name == "dados.html"), pagina

    def test_dados_sao_copia_da_exportacao(self, site, tmp_path):
        for arquivo in [*(t.arquivo for t in TABELAS), "DICIONARIO.md", "metadados.json"]:
            assert (site / "dados" / arquivo).read_bytes() == (
                tmp_path / "export" / arquivo
            ).read_bytes()

    def test_mesma_exportacao_mesmos_bytes(self, site, tmp_path):
        gerar_site(tmp_path / "export", tmp_path / "site2")
        for pagina in site.rglob("*"):
            if pagina.is_file():
                gemea = tmp_path / "site2" / pagina.relative_to(site)
                assert pagina.read_bytes() == gemea.read_bytes(), pagina


class TestConteudo:
    def test_ativo_no_index_com_aviso_do_inmet(self, site):
        index = (site / "index.html").read_text(encoding="utf-8")
        assert "<strong>1 alerta ativo</strong> em 1 município" in index
        ativos = index.split('<h2 id="t-ativos">')[1].split("<h2")[0]
        assert "Rio de Janeiro" in ativos and "São Paulo" not in ativos
        assert "Tempestade, perigo" in ativos
        assert "23/11/2026, 12:00" in ativos  # 15:00 UTC em Brasília
        assert 'class="nivel nivel-moderado">Moderado<' in ativos  # cor e texto

    def test_faixa_tem_30_dias_legiveis_por_leitor_de_tela(self, site):
        index = (site / "index.html").read_text(encoding="utf-8")
        faixa = index.split('<ol class="faixa"')[1].split("</ol>")[0]
        assert faixa.count("<li ") == 30
        assert '<span class="sr">23/11: 1 alerta; coletor ligado em 100% do dia</span>' in faixa
        assert '<span class="sr">22/11: 1 alerta; sem registro de coleta</span>' in faixa

    def test_pagina_do_municipio_mostra_saida_e_falta_de_avisos(self, site):
        html = (site / "municipio" / f"{SP}.html").read_text(encoding="utf-8")
        assert '<h1>São Paulo <span class="uf">RJ</span></h1>' in html
        assert "Saiu do painel em 22/11/2026, 08:00" in html
        # A2 começou antes da primeira coleta de avisos: não é "nenhum aviso".
        assert "Antes da coleta de avisos" in html
        assert "<h3>Novembro de 2026</h3>" in html

    def test_texto_da_fonte_e_escapado(self, tmp_path, monkeypatch):
        site = _gerar(tmp_path, monkeypatch, municipio_a1='<script>alert("x")</script>')
        for pagina in _paginas(site):
            assert "<script>" not in pagina.read_text(encoding="utf-8"), pagina
        assert "&lt;script&gt;" in (site / "municipio" / f"{RJ}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("JUIZ DE FORA", "Juiz de Fora"),
        ("MOGI DAS CRUZES", "Mogi das Cruzes"),
        ("SÃO JOSÉ DOS CAMPOS", "São José dos Campos"),
        ("ESPÍRITO SANTO DO PINHAL", "Espírito Santo do Pinhal"),
        ("DE PAULA", "De Paula"),
    ],
)
def test_nome_proprio(bruto, esperado):
    assert nome_proprio(bruto) == esperado


def test_em_brasilia():
    assert em_brasilia("2026-11-23T22:40:48Z") == "23/11/2026, 19:40"
    assert em_brasilia("2026-11-24T01:00:00Z") == "23/11/2026, 22:00"
    assert em_brasilia("") == ""
