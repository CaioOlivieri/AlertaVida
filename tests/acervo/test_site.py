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
        """Viewport declarado, conteúdo com largura máxima e tabela com rolagem
        própria — a página nunca rola na horizontal inteira."""
        for pagina in _paginas(site):
            html = pagina.read_text(encoding="utf-8")
            assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
            assert html.count("<table>") == html.count('<div class="tabela"><table>')
        css = (site / "estilo.css").read_text(encoding="utf-8")
        assert "max-width: 60rem" in css and "overflow-x: auto" in css
        assert "padding: 0 16px" in css

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
        ativos = index.split("<h2>Ativos em")[1].split("<h2>")[0]
        assert "Rio de Janeiro" in ativos and "São Paulo" not in ativos
        assert "Tempestade (Perigo)" in ativos
        assert "23/11/2026 12:00" in ativos  # 15:00 UTC em Brasília

    def test_pagina_do_municipio_mostra_encerramento(self, site):
        html = (site / "municipio" / f"{SP}.html").read_text(encoding="utf-8")
        assert "<h1>São Paulo — RJ</h1>" in html
        assert "Encerrado (saída detectada em 22/11/2026 08:00)" in html

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
    assert em_brasilia("2026-11-23T22:40:48Z") == "23/11/2026 19:40"
    assert em_brasilia("2026-11-24T01:00:00Z") == "23/11/2026 22:00"
    assert em_brasilia("") == ""
