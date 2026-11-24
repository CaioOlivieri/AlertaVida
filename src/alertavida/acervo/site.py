"""Gera o site estático do acervo a partir de uma exportação (issue #158).

Lê só os arquivos de `alertavida.acervo.exportar` — nunca o banco — e escreve
HTML + um CSS, sem JavaScript, com links relativos (abre por `file://` e
funciona em qualquer subcaminho de hospedagem):

- `index.html` — alertas ativos no backup, cobertura dos últimos 30 dias,
  municípios por UF;
- `municipio/<codibge>.html` — um por município com ao menos um alerta;
- `dados.html` + `dados/` — os CSVs, o dicionário e os metadados.

Todo texto vindo das fontes passa por `html.escape`. Horários na tela em
horário de Brasília (UTC−3, sem horário de verão desde 2019); os CSVs ficam em
UTC. Determinístico: a mesma exportação gera os mesmos bytes.

Uso:

    uv run python -m alertavida.acervo.site \\
        --export /var/lib/alertavida/export --saida /var/lib/alertavida/site
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

from alertavida.acervo.exportar import (
    ALERTA_AVISOS,
    ALERTAS,
    COBERTURA,
    TABELAS,
    preparar_temporario,
    trocar_diretorio,
)

BRASILIA = timezone(timedelta(hours=-3))
DIAS_RECENTES = 30

_NIVEIS = {"MODERADO": "Moderado", "ALTO": "Alto", "MUITO_ALTO": "Muito alto"}
_SEVERIDADES = {
    "PERIGO_POTENCIAL": "Perigo potencial",
    "PERIGO": "Perigo",
    "GRANDE_PERIGO": "Grande perigo",
}
# O que o CEMADEN chama de cada subgrupo COBRADE que ele publica.
_TIPOS_POR_COBRADE = {"1.2.0.0.0": "Risco hidrológico", "1.1.3.0.0": "Movimento de massa"}

ESTILO = """\
:root { color-scheme: light dark; --fundo: #fff; --texto: #1a1a1a; --suave: #555;
  --borda: #d0d0d0; --destaque: #fff4e0; --link: #0b57d0; }
@media (prefers-color-scheme: dark) { :root { --fundo: #141414; --texto: #eaeaea;
  --suave: #aaa; --borda: #3a3a3a; --destaque: #3a2c12; --link: #8ab4f8; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--fundo); color: var(--texto);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main, header, footer { max-width: 60rem; margin: 0 auto; padding: 0 16px; }
header { padding-top: 1rem; }
a { color: var(--link); }
h1 { font-size: 1.5rem; margin: 0.5rem 0; }
h2 { font-size: 1.2rem; margin-top: 2rem; }
.aviso { background: var(--destaque); border: 1px solid var(--borda); padding: 0.75rem 1rem;
  border-radius: 6px; }
.tabela { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.95rem; }
th, td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--borda);
  vertical-align: top; }
th { white-space: nowrap; }
.suave, footer { color: var(--suave); font-size: 0.9rem; }
footer { margin-top: 3rem; padding-bottom: 2rem; }
ul.municipios { columns: 14rem; padding-left: 1.2rem; }
"""

_AVISO_OFICIAL = (
    '<p class="aviso"><strong>Este acervo não é um canal oficial de alerta.</strong> '
    "Em situação de risco, siga a Defesa Civil do seu município. Emergência: "
    "<strong>199</strong> (Defesa Civil) ou <strong>193</strong> (Bombeiros). "
    "Para receber alertas oficiais por SMS, envie seu CEP para <strong>40199</strong>.</p>"
)


@dataclass(frozen=True)
class AlertaSite:
    cod_alerta: str
    codibge: str
    municipio: str
    uf: str
    cobrade_codigo: str
    tipo_evento: str
    nivel: str
    inicio_utc: str
    status: str
    resolucao_detectada_utc: str

    @property
    def tipo(self) -> str:
        return _TIPOS_POR_COBRADE.get(self.cobrade_codigo, self.tipo_evento.capitalize())

    @property
    def nivel_legivel(self) -> str:
        return _NIVEIS.get(self.nivel, self.nivel)


@dataclass(frozen=True)
class AvisoSite:
    evento: str
    severidade: str

    def __str__(self) -> str:
        return f"{self.evento} ({_SEVERIDADES.get(self.severidade, self.severidade)})"


_PARTICULAS = {"de", "da", "do", "das", "dos", "e", "d'"}


def nome_proprio(nome: str) -> str:
    """`JUIZ DE FORA` → `Juiz de Fora`: o CEMADEN publica em maiúsculas."""
    palavras = nome.lower().split()
    return " ".join(
        p if i > 0 and p in _PARTICULAS else p[:1].upper() + p[1:] for i, p in enumerate(palavras)
    )


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as entrada:
        return list(csv.DictReader(entrada))


def _instante(utc: str) -> datetime:
    return datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def em_brasilia(utc: str) -> str:
    if not utc:
        return ""
    return _instante(utc).astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M")


def _pagina(titulo: str, corpo: str, raiz: str, rodape: str) -> str:
    return (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(titulo)}</title>\n"
        f'<link rel="stylesheet" href="{raiz}estilo.css">\n</head>\n<body>\n'
        f'<header><p class="suave"><a href="{raiz}index.html">AlertaVida — acervo</a> · '
        f'<a href="{raiz}dados.html">Dados</a></p></header>\n'
        f"<main>\n{corpo}\n</main>\n<footer>{rodape}</footer>\n</body>\n</html>\n"
    )


def _tabela(cabecalho: Iterable[str], linhas: Iterable[Iterable[str]]) -> str:
    """Células já devem vir escapadas (algumas carregam links)."""
    th = "".join(f"<th>{c}</th>" for c in cabecalho)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>\n" for linha in linhas)
    return (
        f'<div class="tabela"><table>\n<thead><tr>{th}</tr></thead>\n'
        f"<tbody>\n{tr}</tbody>\n</table></div>"
    )


def _situacao(alerta: AlertaSite) -> str:
    if alerta.status == "ATIVO":
        return "<strong>Ativo</strong>"
    return f"Encerrado (saída detectada em {em_brasilia(alerta.resolucao_detectada_utc)})"


def _avisos(avisos: list[AvisoSite]) -> str:
    return "<br>".join(escape(str(a)) for a in avisos) or '<span class="suave">—</span>'


def _link_municipio(alerta: AlertaSite, raiz: str) -> str:
    return (
        f'<a href="{raiz}municipio/{escape(alerta.codibge)}.html">'
        f"{escape(nome_proprio(alerta.municipio))}</a> — {escape(alerta.uf)}"
    )


def gerar_index(
    alertas: list[AlertaSite],
    avisos_por_alerta: dict[str, list[AvisoSite]],
    cobertura: list[dict[str, str]],
    instante_backup: str,
    rodape: str,
) -> str:
    ativos = sorted(
        (a for a in alertas if a.status == "ATIVO"), key=lambda a: (a.inicio_utc, a.cod_alerta)
    )
    partes = [
        "<h1>Alertas do CEMADEN, com o contexto do INMET</h1>",
        _AVISO_OFICIAL,
        "<p>Histórico dos alertas publicados pelo CEMADEN, como o coletor do AlertaVida os "
        "viu, anotados com os avisos meteorológicos do INMET em vigor no município no "
        "início de cada alerta. Horários de Brasília.</p>",
        f"<h2>Ativos em {em_brasilia(instante_backup)}</h2>",
    ]
    if ativos:
        partes.append(
            _tabela(
                ["Início", "Município", "Tipo", "Nível", "Avisos do INMET no início"],
                (
                    [
                        em_brasilia(a.inicio_utc),
                        _link_municipio(a, ""),
                        escape(a.tipo),
                        escape(a.nivel_legivel),
                        _avisos(avisos_por_alerta.get(a.cod_alerta, [])),
                    ]
                    for a in ativos
                ),
            )
        )
    else:
        partes.append("<p>Nenhum alerta ativo.</p>")

    fim = _instante(instante_backup).date()
    recentes = [fim - timedelta(days=d) for d in range(DIAS_RECENTES)]
    novos_por_dia: dict[date, int] = defaultdict(int)
    for a in alertas:
        novos_por_dia[_instante(a.inicio_utc).date()] += 1
    cobertura_cemaden = {
        c["dia"]: float(c["cobertura"]) for c in cobertura if c["fonte"] == "CEMADEN"
    }
    partes += [
        f"<h2>Últimos {DIAS_RECENTES} dias</h2>",
        '<p class="suave">Cobertura: fração do dia (em UTC) em que o coletor estava ligado e '
        "consultou o CEMADEN. Num dia de cobertura baixa, um alerta pode não ter sido visto.</p>",
        _tabela(
            ["Dia (UTC)", "Alertas iniciados", "Cobertura da coleta"],
            (
                [
                    dia.strftime("%d/%m/%Y"),
                    str(novos_por_dia.get(dia, 0)),
                    f"{cobertura_cemaden[dia.isoformat()]:.0%}"
                    if dia.isoformat() in cobertura_cemaden
                    else '<span class="suave">sem registro</span>',
                ]
                for dia in recentes
            ),
        ),
    ]

    por_uf: dict[str, dict[str, tuple[str, int]]] = defaultdict(dict)
    for a in alertas:
        nome, total = por_uf[a.uf].get(a.codibge, (a.municipio, 0))
        por_uf[a.uf][a.codibge] = (nome, total + 1)
    partes.append(f"<h2>Municípios com alertas ({sum(len(m) for m in por_uf.values())})</h2>")
    for uf in sorted(por_uf):
        itens = sorted(por_uf[uf].items(), key=lambda item: (item[1][0], item[0]))
        partes.append(f'<h3>{escape(uf)}</h3>\n<ul class="municipios">')
        partes += [
            f'<li><a href="municipio/{escape(cod)}.html">{escape(nome_proprio(nome))}</a> '
            f'<span class="suave">({total})</span></li>'
            for cod, (nome, total) in itens
        ]
        partes.append("</ul>")
    return _pagina("AlertaVida — acervo de alertas", "\n".join(partes), "", rodape)


def gerar_municipio(
    alertas: list[AlertaSite], avisos_por_alerta: dict[str, list[AvisoSite]], rodape: str
) -> str:
    alertas = sorted(alertas, key=lambda a: (a.inicio_utc, a.cod_alerta), reverse=True)
    primeiro = alertas[-1]
    titulo = f"{nome_proprio(primeiro.municipio)} — {primeiro.uf}"
    corpo = "\n".join(
        [
            f"<h1>{escape(titulo)}</h1>",
            f'<p class="suave">Código IBGE {escape(primeiro.codibge)} · {len(alertas)} '
            f"alerta(s) do CEMADEN, de {em_brasilia(primeiro.inicio_utc)} a "
            f"{em_brasilia(alertas[0].inicio_utc)}. Horários de Brasília.</p>",
            _AVISO_OFICIAL,
            _tabela(
                ["Início", "Tipo", "Nível", "Situação", "Avisos do INMET no início"],
                (
                    [
                        em_brasilia(a.inicio_utc),
                        escape(a.tipo),
                        escape(a.nivel_legivel),
                        _situacao(a),
                        _avisos(avisos_por_alerta.get(a.cod_alerta, [])),
                    ]
                    for a in alertas
                ),
            ),
            '<p class="suave">"Saída detectada" é quando o coletor concluiu que o alerta '
            "saiu do painel do CEMADEN (três consultas seguidas sem ele); com o coletor "
            "desligado, a saída real pode ter sido antes. Avisos do INMET só existem para "
            'alertas a partir de 23/11/2026. Ver <a href="../dados.html">Dados</a>.</p>',
        ]
    )
    return _pagina(f"{titulo} — AlertaVida", corpo, "../", rodape)


def gerar_dados(metadados: dict[str, object], rodape: str) -> str:
    partes = [
        "<h1>Dados</h1>",
        _AVISO_OFICIAL,
        "<p>Tudo o que este site mostra sai destes arquivos (CSV em UTF-8, separado por "
        'vírgula, instantes em UTC). O <a href="dados/DICIONARIO.md">dicionário</a> descreve '
        'cada coluna; <a href="dados/metadados.json">metadados.json</a> identifica o backup '
        "de origem.</p>",
    ]
    linhas = metadados.get("linhas", {})
    assert isinstance(linhas, dict)
    for tabela in TABELAS:
        partes += [
            f'<h2><a href="dados/{escape(tabela.arquivo)}">{escape(tabela.arquivo)}</a></h2>',
            f'<p>{escape(tabela.descricao)} <span class="suave">'
            f"({linhas.get(tabela.arquivo, 0)} linhas)</span></p>",
        ]
    return _pagina("Dados — AlertaVida", "\n".join(partes), "", rodape)


def gerar_site(export: Path, saida: Path) -> int:
    """Escreve o site em `saida` (substituído por inteiro); devolve o nº de páginas."""
    metadados = json.loads((export / "metadados.json").read_text(encoding="utf-8"))
    campos = AlertaSite.__dataclass_fields__
    alertas = [
        AlertaSite(**{k: v for k, v in linha.items() if k in campos})
        for linha in _ler_csv(export / ALERTAS.arquivo)
    ]
    avisos_por_alerta: dict[str, list[AvisoSite]] = defaultdict(list)
    for linha in _ler_csv(export / ALERTA_AVISOS.arquivo):
        avisos_por_alerta[linha["cod_alerta"]].append(
            AvisoSite(linha["evento"], linha["severidade"])
        )
    cobertura = _ler_csv(export / COBERTURA.arquivo)
    rodape = (
        f"Gerado a partir de {escape(str(metadados['backup']))} "
        f"(SHA-256 {escape(str(metadados['backup_sha256']))[:12]}…). "
        "Fontes: CEMADEN (alertas) e INMET (avisos), coletados pelo AlertaVida."
    )

    temporario = preparar_temporario(saida)
    (temporario / "municipio").mkdir()
    (temporario / "dados").mkdir()
    (temporario / "estilo.css").write_text(ESTILO, encoding="utf-8")
    (temporario / "index.html").write_text(
        gerar_index(
            alertas, avisos_por_alerta, cobertura, str(metadados["backup_instante_utc"]), rodape
        ),
        encoding="utf-8",
    )
    (temporario / "dados.html").write_text(gerar_dados(metadados, rodape), encoding="utf-8")

    por_municipio: dict[str, list[AlertaSite]] = defaultdict(list)
    for a in alertas:
        por_municipio[a.codibge].append(a)
    for codibge, lista in por_municipio.items():
        (temporario / "municipio" / f"{codibge}.html").write_text(
            gerar_municipio(lista, avisos_por_alerta, rodape), encoding="utf-8"
        )
    for arquivo in [*(t.arquivo for t in TABELAS), "DICIONARIO.md", "metadados.json"]:
        shutil.copyfile(export / arquivo, temporario / "dados" / arquivo)

    trocar_diretorio(temporario, saida)
    return 2 + len(por_municipio)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o site estático do acervo AlertaVida.")
    parser.add_argument("--export", type=Path, required=True, help="diretório da exportação")
    parser.add_argument("--saida", type=Path, required=True, help="diretório do site (substituído)")
    args = parser.parse_args(argv)
    print(f"{gerar_site(args.export, args.saida)} páginas em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
