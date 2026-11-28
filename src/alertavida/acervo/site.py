"""Gera o site estático do acervo a partir de uma exportação (issue #158).

Lê só os arquivos de `alertavida.acervo.exportar` — nunca o banco — e escreve
HTML + um CSS, sem JavaScript, com links relativos (abre por `file://` e
funciona em qualquer subcaminho de hospedagem):

- `index.html` — o que está ativo agora, a faixa dos últimos 30 dias (alertas
  por dia e quanto do dia o coletor esteve ligado) e os municípios por UF;
- `municipio/<codibge>.html` — o histórico de cada município com alerta;
- `dados.html` + `dados/` — os CSVs, o dicionário, os metadados e a
  procedência técnica (nome e SHA-256 do backup).

Desenho para o celular primeiro: alertas são uma lista semântica (rótulo e
valor em duas colunas), nunca uma tabela que role de lado. Nível de
risco nas cores convencionais da Defesa Civil, sempre com o texto ao lado.
Fontes do sistema (nenhum pedido a terceiros). Todo texto vindo das fontes
passa por `html.escape`. Horários na tela em horário de Brasília (UTC−3, sem
horário de verão desde 2019); os CSVs ficam em UTC. Determinístico: a mesma
exportação gera os mesmos bytes.

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
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

from alertavida.acervo.exportar import (
    ALERTA_AVISOS,
    ALERTAS,
    AVISOS,
    COBERTURA,
    TABELAS,
    preparar_temporario,
    trocar_diretorio,
)

BRASILIA = timezone(timedelta(hours=-3))
DIAS_RECENTES = 30

_NIVEIS = {"MODERADO": "Moderado", "ALTO": "Alto", "MUITO_ALTO": "Muito alto"}
_SEVERIDADES = {
    "PERIGO_POTENCIAL": "perigo potencial",
    "PERIGO": "perigo",
    "GRANDE_PERIGO": "grande perigo",
}
# O que o CEMADEN chama de cada subgrupo COBRADE que ele publica.
_TIPOS_POR_COBRADE = {"1.2.0.0.0": "Risco hidrológico", "1.1.3.0.0": "Movimento de massa"}
_MESES = (
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro"
).split()

ESTILO = """\
:root {
  color-scheme: light dark;
  --papel: #f5f7f7;
  --tinta: #1d2b30;
  --tinta-suave: #4b5b61;
  --linha: #d3dadc;
  --rio: #1f5f8b;
  --faixa: #9fb4bd;
  --aviso-fundo: #fbf3d9;
  --aviso-borda: #c9a227;
  --moderado: #f2c230;
  --alto: #e07b1a;
  --muito-alto: #c3312b;
  --nivel-texto: #1d2b30;
  --medida: 42rem;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --papel: #141c1f;
    --tinta: #e6ecee;
    --tinta-suave: #a7b5ba;
    --linha: #2f3d42;
    --rio: #8cc4ea;
    --faixa: #5d7884;
    --aviso-fundo: #2c2614;
    --aviso-borda: #8a7020;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--papel);
  color: var(--tinta);
  font-size: 1rem;
  line-height: 1.55;
}
.topo, main, .rodape { max-width: var(--medida); margin: 0 auto; padding: 0 16px; }
.topo {
  display: flex; justify-content: space-between; align-items: baseline;
  padding-top: 1rem; padding-bottom: 0.5rem;
}
.marca { font-weight: 700; color: var(--tinta); text-decoration: none; letter-spacing: -0.01em; }
a { color: var(--rio); text-underline-offset: 0.15em; }
a:focus-visible, summary:focus-visible { outline: 3px solid var(--rio); outline-offset: 2px; }
h1 { font-size: 1.95rem; line-height: 1.15; font-weight: 650; letter-spacing: -0.02em;
  margin: 1.25rem 0 0.75rem; }
h2 { font-size: 1.25rem; font-weight: 650; margin: 2.5rem 0 0.75rem; }
h3 { font-size: 1rem; font-weight: 650; margin: 1.75rem 0 0.5rem; color: var(--tinta-suave); }
p { margin: 0 0 1rem; }
.uf { font-weight: 400; color: var(--tinta-suave); }
.agora { font-size: 1.15rem; }
.nota, .rodape { color: var(--tinta-suave); font-size: 0.9rem; }
.aviso {
  background: var(--aviso-fundo); border-left: 4px solid var(--aviso-borda);
  padding: 0.75rem 1rem; margin: 1.25rem 0;
}
.sr {
  position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip-path: inset(50%); white-space: nowrap;
}

/* A faixa dos últimos 30 dias: alertas por dia em cima, coleta embaixo. */
.faixa {
  list-style: none; margin: 1rem 0 0.25rem; padding: 0;
  display: grid; grid-template-columns: repeat(30, minmax(0, 1fr)); gap: 2px;
  align-items: end;
}
.faixa li {
  display: grid; grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 6rem 0.5rem 1.2rem; gap: 3px;
}
.faixa .barra {
  align-self: end; justify-self: center; width: 72%;
  height: calc(var(--alertas) / var(--max) * 100%);
  min-height: 1px;
  background: var(--rio);
}
.faixa .coleta { background: var(--faixa); opacity: var(--cobertura); }
.faixa .coleta.sem-registro {
  opacity: 1;
  background: repeating-linear-gradient(135deg, var(--linha) 0 2px, transparent 2px 4px);
}
.faixa .marca-dia { font-size: 0.7rem; color: var(--tinta-suave); white-space: nowrap; }
/* O rótulo do último dia transborda para dentro, nunca para fora da página. */
.faixa li:last-child .marca-dia { justify-self: end; }
.legenda { display: flex; flex-wrap: wrap; gap: 0.25rem 1.25rem; margin-bottom: 1rem; }
.legenda span::before {
  content: ""; display: inline-block; width: 0.75rem; height: 0.75rem;
  margin-right: 0.35rem; vertical-align: -0.05rem;
}
.legenda .l-alertas::before { background: var(--rio); }
.legenda .l-coleta::before { background: var(--faixa); }
.legenda .l-sem::before {
  background: repeating-linear-gradient(135deg, var(--tinta-suave) 0 2px, transparent 2px 4px);
}

/* Alertas: blocos no celular, grade alinhada em telas largas. */
.alertas { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--linha); }
.alerta { padding: 0.9rem 0; border-bottom: 1px solid var(--linha); }
.alerta .lugar { font-weight: 650; font-size: 1.05rem; margin: 0 0 0.35rem; }
.alerta dl { margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem 1rem; }
.alerta .largo { grid-column: 1 / -1; }
.alerta dt { color: var(--tinta-suave); font-size: 0.85rem; }
.alerta dd { margin: 0; }
.nivel {
  display: inline-block; padding: 0 0.45rem; border-radius: 3px;
  color: var(--nivel-texto); font-weight: 600; font-size: 0.9rem;
}
.nivel-moderado { background: var(--moderado); }
.nivel-alto { background: var(--alto); }
.nivel-muito-alto { background: var(--muito-alto); color: #fff; }
.sem { color: var(--tinta-suave); }

details { border-bottom: 1px solid var(--linha); }
details:first-of-type { border-top: 1px solid var(--linha); }
summary { cursor: pointer; padding: 0.6rem 0; font-weight: 600; }
summary .contagem { font-weight: 400; color: var(--tinta-suave); }
.municipios { columns: 12rem; margin: 0 0 1rem; padding-left: 1.1rem; }
.municipios li { break-inside: avoid; }

.arquivos { padding-left: 1.1rem; }
.arquivos li { margin-bottom: 0.75rem; }
.procedencia { overflow-wrap: anywhere; }
.rodape { margin-top: 3rem; padding-top: 1rem; padding-bottom: 2.5rem;
  border-top: 1px solid var(--linha); }

@media (min-width: 40rem) {
  h1 { font-size: 2.4rem; }
  .faixa li { grid-template-rows: 8rem 0.5rem 1.2rem; }
}
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
        return _NIVEIS.get(self.nivel, self.nivel.capitalize())

    @property
    def classe_nivel(self) -> str:
        return "nivel-" + self.nivel.lower().replace("_", "-")


@dataclass(frozen=True)
class AvisoSite:
    evento: str
    severidade: str

    def __str__(self) -> str:
        return f"{self.evento}, {_SEVERIDADES.get(self.severidade, self.severidade.lower())}"


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
    """`2026-11-23T22:40:48Z` → `23/11/2026, 19:40`."""
    if not utc:
        return ""
    return _instante(utc).astimezone(BRASILIA).strftime("%d/%m/%Y, %H:%M")


def _mes_por_extenso(utc: str) -> str:
    local = _instante(utc).astimezone(BRASILIA)
    return f"{_MESES[local.month - 1].capitalize()} de {local.year}"


@dataclass(frozen=True)
class Contexto:
    """O que toda página precisa saber sobre a exportação."""

    atualizado_utc: str
    inicio_avisos_utc: str  # primeira coleta de avisos do INMET ("" se nenhuma)

    @property
    def rodape(self) -> str:
        return (
            f"<p>Dados atualizados em {em_brasilia(self.atualizado_utc)} "
            "(horário de Brasília). Fontes: CEMADEN (alertas) e INMET (avisos "
            "meteorológicos), coletados pelo AlertaVida.</p>"
        )


def _pagina(titulo: str, corpo: str, raiz: str, contexto: Contexto) -> str:
    return (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(titulo)}</title>\n"
        f'<link rel="stylesheet" href="{raiz}estilo.css">\n</head>\n<body>\n'
        f'<header class="topo"><a class="marca" href="{raiz}index.html">AlertaVida</a>'
        f'<a href="{raiz}dados.html">Dados</a></header>\n'
        f'<main>\n{corpo}\n</main>\n<footer class="rodape">{contexto.rodape}</footer>\n'
        "</body>\n</html>\n"
    )


_ORDEM_SEVERIDADE = {"GRANDE_PERIGO": 0, "PERIGO": 1, "PERIGO_POTENCIAL": 2}


def _avisos(alerta: AlertaSite, avisos: list[AvisoSite], contexto: Contexto) -> str:
    """Cada par (evento, severidade) uma vez, o mais grave primeiro. Avisos do
    INMET se sobrepõem (substituições, faixas vizinhas); repetir "Chuvas
    Intensas, perigo" não diz nada a quem lê. O CSV guarda cada mensagem."""
    if avisos:
        unicos = sorted(
            set(avisos), key=lambda a: (_ORDEM_SEVERIDADE.get(a.severidade, 9), a.evento)
        )
        return "<br>".join(escape(str(a)) for a in unicos)
    if not contexto.inicio_avisos_utc or alerta.inicio_utc < contexto.inicio_avisos_utc:
        return '<span class="sem">Antes da coleta de avisos</span>'
    return '<span class="sem">Nenhum em vigor</span>'


def _situacao(alerta: AlertaSite) -> str:
    if alerta.status == "ATIVO":
        return "Ativo"
    return f"Saiu do painel em {em_brasilia(alerta.resolucao_detectada_utc)}"


def _item_alerta(
    alerta: AlertaSite,
    avisos: list[AvisoSite],
    contexto: Contexto,
    *,
    lugar: str | None,
    com_situacao: bool,
) -> str:
    linhas = [f"<div><dt>Início</dt><dd>{em_brasilia(alerta.inicio_utc)}</dd></div>"]
    linhas.append(f"<div><dt>Tipo</dt><dd>{escape(alerta.tipo)}</dd></div>")
    linhas.append(
        f'<div><dt>Nível</dt><dd><span class="nivel {escape(alerta.classe_nivel)}">'
        f"{escape(alerta.nivel_legivel)}</span></dd></div>"
    )
    if com_situacao:
        linhas.append(f"<div><dt>Situação</dt><dd>{_situacao(alerta)}</dd></div>")
    linhas.append(
        f'<div class="largo"><dt>Avisos do INMET</dt>'
        f"<dd>{_avisos(alerta, avisos, contexto)}</dd></div>"
    )
    cabeca = f'<p class="lugar">{lugar}</p>' if lugar else ""
    return f'<li class="alerta">{cabeca}<dl>{"".join(linhas)}</dl></li>'


def _link_municipio(alerta: AlertaSite) -> str:
    return (
        f'<a href="municipio/{escape(alerta.codibge)}.html">'
        f"{escape(nome_proprio(alerta.municipio))}</a> "
        f'<span class="uf">{escape(alerta.uf)}</span>'
    )


def _faixa(alertas: list[AlertaSite], cobertura: list[dict[str, str]], contexto: Contexto) -> str:
    fim = _instante(contexto.atualizado_utc).astimezone(BRASILIA).date()
    dias = [fim - timedelta(days=d) for d in range(DIAS_RECENTES - 1, -1, -1)]
    por_dia: dict[date, int] = defaultdict(int)
    for a in alertas:
        por_dia[_instante(a.inicio_utc).astimezone(BRASILIA).date()] += 1
    # A cobertura é medida por dia em UTC; para a faixa basta o dia correspondente.
    cob = {c["dia"]: float(c["cobertura"]) for c in cobertura if c["fonte"] == "CEMADEN"}
    maximo = max([1, *(por_dia.get(d, 0) for d in dias)])

    itens = []
    for posicao, dia in enumerate(dias):
        n = por_dia.get(dia, 0)
        fracao = cob.get(dia.isoformat())
        if fracao is None:
            coleta = '<span class="coleta sem-registro"></span>'
            texto_coleta = "sem registro de coleta"
        else:
            coleta = f'<span class="coleta" style="--cobertura:{max(fracao, 0.08):.2f}"></span>'
            texto_coleta = f"coletor ligado em {fracao:.0%} do dia"
        mostrar = posicao % 7 == (DIAS_RECENTES - 1) % 7
        marca = f"{dia:%d/%m}" if mostrar else ""
        alertas_txt = "1 alerta" if n == 1 else f"{n} alertas"
        itens.append(
            f'<li style="--alertas:{n}"><span class="barra"></span>{coleta}'
            f'<span class="marca-dia" aria-hidden="true">{marca}</span>'
            f'<span class="sr">{dia:%d/%m}: {alertas_txt}; {texto_coleta}</span></li>'
        )
    return (
        f'<ol class="faixa" style="--max:{maximo}">{"".join(itens)}</ol>'
        '<p class="legenda nota"><span class="l-alertas">alertas iniciados no dia</span>'
        '<span class="l-coleta">coletor ligado (mais claro: menos horas)</span>'
        '<span class="l-sem">sem registro de coleta</span></p>'
    )


def gerar_index(
    alertas: list[AlertaSite],
    avisos_por_alerta: dict[str, list[AvisoSite]],
    cobertura: list[dict[str, str]],
    contexto: Contexto,
) -> str:
    ativos = sorted(
        (a for a in alertas if a.status == "ATIVO"),
        key=lambda a: (a.inicio_utc, a.cod_alerta),
        reverse=True,
    )
    municipios_ativos = len({a.codibge for a in ativos})
    if ativos:
        agora = (
            f"<strong>{len(ativos)} {'alerta ativo' if len(ativos) == 1 else 'alertas ativos'}"
            f"</strong> em {municipios_ativos} "
            f"{'município' if municipios_ativos == 1 else 'municípios'}, "
            f"em {em_brasilia(contexto.atualizado_utc)}."
        )
    else:
        agora = f"Nenhum alerta ativo em {em_brasilia(contexto.atualizado_utc)}."
    partes = [
        "<h1>Alertas de risco do CEMADEN, com os avisos do INMET</h1>",
        f'<p class="agora">{agora}</p>',
        "<p>Um registro aberto dos alertas de inundação e deslizamento que o CEMADEN "
        "publica, com os avisos de tempo do INMET que valiam no município quando cada "
        "alerta começou. Horários de Brasília.</p>",
        _AVISO_OFICIAL,
        f'<h2 id="t-faixa">Últimos {DIAS_RECENTES} dias</h2>',
        '<p class="nota">Num dia em que o coletor ficou desligado, alertas podem não ter '
        "sido registrados.</p>",
        _faixa(alertas, cobertura, contexto),
        '<h2 id="t-ativos">Ativos agora</h2>',
    ]
    if ativos:
        partes.append('<ul class="alertas">')
        partes += [
            _item_alerta(
                a,
                avisos_por_alerta.get(a.cod_alerta, []),
                contexto,
                lugar=_link_municipio(a),
                com_situacao=False,
            )
            for a in ativos
        ]
        partes.append("</ul>")
    else:
        partes.append("<p>Nenhum alerta ativo no momento.</p>")

    por_uf: dict[str, dict[str, tuple[str, int]]] = defaultdict(dict)
    for a in alertas:
        nome, total = por_uf[a.uf].get(a.codibge, (a.municipio, 0))
        por_uf[a.uf][a.codibge] = (nome, total + 1)
    total_municipios = sum(len(m) for m in por_uf.values())
    partes.append(f'<h2 id="t-municipios">Municípios com alertas ({total_municipios})</h2>')
    for uf in sorted(por_uf):
        itens = sorted(por_uf[uf].items(), key=lambda item: (item[1][0], item[0]))
        n = len(itens)
        partes.append(
            f'<details><summary>{escape(uf)} <span class="contagem">'
            f"{n} {'município' if n == 1 else 'municípios'}</span></summary>"
            '<ul class="municipios">'
        )
        partes += [
            f'<li><a href="municipio/{escape(cod)}.html">{escape(nome_proprio(nome))}</a> '
            f'<span class="sem">({total})</span></li>'
            for cod, (nome, total) in itens
        ]
        partes.append("</ul></details>")
    return _pagina("AlertaVida: alertas de risco do CEMADEN", "\n".join(partes), "", contexto)


def gerar_municipio(
    alertas: list[AlertaSite], avisos_por_alerta: dict[str, list[AvisoSite]], contexto: Contexto
) -> str:
    alertas = sorted(alertas, key=lambda a: (a.inicio_utc, a.cod_alerta), reverse=True)
    mais_antigo = alertas[-1]
    nome = nome_proprio(mais_antigo.municipio)
    ativos = sum(1 for a in alertas if a.status == "ATIVO")
    total = "1 alerta" if len(alertas) == 1 else f"{len(alertas)} alertas"
    resumo = f"{total} do CEMADEN desde {em_brasilia(mais_antigo.inicio_utc)[:10]}" + (
        f"; {ativos} {'ativo' if ativos == 1 else 'ativos'} agora." if ativos else "."
    )
    partes = [
        f'<h1>{escape(nome)} <span class="uf">{escape(mais_antigo.uf)}</span></h1>',
        f'<p class="agora">{resumo}</p>',
        _AVISO_OFICIAL,
        '<h2 id="t-historico">Histórico</h2>',
    ]
    mes_atual = None
    for a in alertas:
        mes = _mes_por_extenso(a.inicio_utc)
        if mes != mes_atual:
            if mes_atual is not None:
                partes.append("</ol>")
            partes += [f"<h3>{mes}</h3>", '<ol class="alertas">']
            mes_atual = mes
        partes.append(
            _item_alerta(
                a, avisos_por_alerta.get(a.cod_alerta, []), contexto, lugar=None, com_situacao=True
            )
        )
    partes.append("</ol>")
    partes.append(
        '<p class="nota">"Saiu do painel" é quando o AlertaVida percebeu que o alerta deixou '
        "de aparecer no painel do CEMADEN. Se o coletor estava desligado, ele pode ter saído "
        f"antes. Código IBGE do município: {escape(mais_antigo.codibge)}. "
        'Os dados completos estão em <a href="../dados.html">Dados</a>.</p>'
    )
    return _pagina(
        f"{nome} ({mais_antigo.uf}): alertas — AlertaVida", "\n".join(partes), "../", contexto
    )


def gerar_dados(metadados: dict[str, object], contexto: Contexto) -> str:
    linhas = metadados.get("linhas", {})
    assert isinstance(linhas, dict)
    partes = [
        "<h1>Dados</h1>",
        "<p>Tudo o que este site mostra sai destes arquivos. São CSV em UTF-8, separados "
        "por vírgula, com os instantes em UTC. O "
        '<a href="dados/DICIONARIO.md">dicionário de dados</a> descreve cada coluna.</p>',
        _AVISO_OFICIAL,
        '<ul class="arquivos">',
    ]
    partes += [
        f'<li><a href="dados/{escape(t.arquivo)}">{escape(t.arquivo)}</a> '
        f'<span class="sem">({linhas.get(t.arquivo, 0)} linhas)</span><br>'
        f"{escape(t.descricao)}</li>"
        for t in TABELAS
    ]
    partes += [
        "</ul>",
        '<h2 id="t-procedencia">Procedência</h2>',
        '<p class="procedencia">Esta versão foi gerada a partir do backup '
        f"<code>{escape(str(metadados.get('backup', '')))}</code>, de "
        f"{em_brasilia(str(metadados.get('backup_instante_utc', '')))} (horário de Brasília), "
        f"SHA-256 <code>{escape(str(metadados.get('backup_sha256', '')))}</code>. "
        'Os mesmos dados estão em <a href="dados/metadados.json">metadados.json</a>.</p>',
    ]
    return _pagina("Dados — AlertaVida", "\n".join(partes), "", contexto)


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
    primeiras = [a["primeira_coleta_utc"] for a in _ler_csv(export / AVISOS.arquivo)]
    contexto = Contexto(
        atualizado_utc=str(metadados["backup_instante_utc"]),
        inicio_avisos_utc=min(primeiras) if primeiras else "",
    )

    temporario = preparar_temporario(saida)
    (temporario / "municipio").mkdir()
    (temporario / "dados").mkdir()
    (temporario / "estilo.css").write_text(ESTILO, encoding="utf-8")
    (temporario / "index.html").write_text(
        gerar_index(alertas, avisos_por_alerta, cobertura, contexto), encoding="utf-8"
    )
    (temporario / "dados.html").write_text(gerar_dados(metadados, contexto), encoding="utf-8")

    por_municipio: dict[str, list[AlertaSite]] = defaultdict(list)
    for a in alertas:
        por_municipio[a.codibge].append(a)
    for codibge, lista in por_municipio.items():
        (temporario / "municipio" / f"{codibge}.html").write_text(
            gerar_municipio(lista, avisos_por_alerta, contexto), encoding="utf-8"
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
