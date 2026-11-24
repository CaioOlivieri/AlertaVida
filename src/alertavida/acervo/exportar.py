"""Exporta o acervo em CSV a partir de um backup (issue #158).

Lê o backup com `mode=ro&immutable=1` — nunca o banco vivo — e escreve num
diretório:

- `alertas_cemaden.csv`, `avisos_inmet.csv`, `aviso_municipios.csv`,
  `alerta_avisos.csv`, `cobertura.csv`;
- `DICIONARIO.md`, gerado das MESMAS definições de coluna que os cabeçalhos
  dos CSVs (não há como os dois divergirem);
- `metadados.json` — de qual backup veio (nome + SHA-256) e contagens.

Determinística: nenhum carimbo de geração; o mesmo backup produz os mesmos
bytes. A cobertura junta a tabela `rodadas` (#161) às extrações do journal
em `wiki/raw/rodadas-journal-*.csv` (antes da tabela existir).

Uso:

    uv run python -m alertavida.acervo.exportar \\
        --backup /var/lib/alertavida/backups --saida /var/lib/alertavida/export
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import math
import re
import shutil
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from alertavida.database import consultar_avisos_vigentes
from alertavida.domain.tempo import parse_iso_utc

VERSAO_FORMATO = 1

_RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]
RODADAS_HISTORICAS_PADRAO = sorted(
    (_RAIZ_REPOSITORIO / "wiki" / "raw").glob("rodadas-journal-*.csv")
)

_NOME_BACKUP = re.compile(r"^alertavida-(\d{8}T\d{6}Z)\.db$")

# Janela de cobertura por fonte: o intervalo do job no scheduler.
JANELA_SEGUNDOS: dict[str, int] = {"CEMADEN": 300, "INMET": 1800}


@dataclass(frozen=True)
class Coluna:
    nome: str
    descricao: str


@dataclass(frozen=True)
class Tabela:
    arquivo: str
    descricao: str
    colunas: tuple[Coluna, ...]

    @property
    def cabecalho(self) -> list[str]:
        return [c.nome for c in self.colunas]


ALERTAS = Tabela(
    "alertas_cemaden.csv",
    "Um alerta do CEMADEN por linha, como o coletor o viu no painel "
    "(painelalertas.cemaden.gov.br).",
    (
        Coluna("cod_alerta", "Identificador do alerta no painel do CEMADEN."),
        Coluna("codibge", "Código IBGE (7 dígitos) do município."),
        Coluna("municipio", "Nome do município, como o CEMADEN publica."),
        Coluna("uf", "Sigla da UF."),
        Coluna("tipo_evento", "HIDROLOGICO ou GEOLOGICO (subgrupo COBRADE)."),
        Coluna("cobrade_codigo", "Código COBRADE do subgrupo (ex.: 1.2.0.0.0)."),
        Coluna("nivel", "Nível de risco publicado (MODERADO, ALTO, MUITO_ALTO)."),
        Coluna("inicio_utc", "Criação do alerta pelo CEMADEN, em UTC."),
        Coluna("atualizado_utc", "Última atualização publicada pelo CEMADEN, em UTC."),
        Coluna("detectado_utc", "Quando o coletor viu o alerta pela primeira vez, em UTC."),
        Coluna("status", "ATIVO ou RESOLVIDO no momento do backup."),
        Coluna(
            "resolucao_detectada_utc",
            "Quando o coletor concluiu que o alerta saiu do painel (3ª rodada "
            "seguida sem ele), em UTC. Vazio se ATIVO. Com o coletor desligado, "
            "a saída real pode ter sido bem antes — ver cobertura.csv.",
        ),
        Coluna(
            "latitude",
            "Latitude publicada. É um ponto fixo por município (provável "
            "centroide), não o local do risco.",
        ),
        Coluna("longitude", "Longitude publicada (mesma ressalva da latitude)."),
    ),
)

AVISOS = Tabela(
    "avisos_inmet.csv",
    "Uma mensagem de aviso meteorológico do INMET por linha "
    "(apiprevmet3.inmet.gov.br). Coletados desde 2026-11-23; sem histórico "
    "anterior.",
    (
        Coluna("codigo_cap", "Identificador CAP da mensagem (urn:oid:2.49.0.0.76.0...)."),
        Coluna("id_aviso", "Número do aviso no INMET."),
        Coluna(
            "id_sequencia",
            "Sequência da mensagem; uma sequência maior do mesmo id_aviso substitui a anterior.",
        ),
        Coluna("evento", "Fenômeno (Tempestade, Chuvas Intensas, Vendaval...)."),
        Coluna("severidade", "Perigo Potencial, Perigo ou Grande Perigo."),
        Coluna("inicio_utc", "Início da validade, em UTC."),
        Coluna("fim_utc", "Fim da validade, em UTC."),
        Coluna("encerrado", "1 se o INMET encerrou o aviso antes do fim."),
        Coluna("primeira_coleta_utc", "Primeira vez que o coletor viu a mensagem, em UTC."),
        Coluna("ultima_coleta_utc", "Última vez que o coletor viu a mensagem, em UTC."),
        Coluna("municipios", "Quantos municípios a mensagem cobre."),
    ),
)

AVISO_MUNICIPIOS = Tabela(
    "aviso_municipios.csv",
    "Os municípios cobertos por cada mensagem de aviso.",
    (
        Coluna("codigo_cap", "Mensagem de aviso (avisos_inmet.csv)."),
        Coluna("codibge", "Código IBGE do município coberto."),
    ),
)

ALERTA_AVISOS = Tabela(
    "alerta_avisos.csv",
    "Os avisos do INMET em vigor no município de cada alerta, no instante "
    "inicio_utc do alerta. Só a sequência mais recente de cada aviso conta; "
    "avisos encerrados não contam. Só avisos que o coletor chegou a ver contam: "
    "a coleta começou em 2026-11-23T13:46Z, e um aviso que saiu da lista de "
    "ativos antes de ser coletado não anota ninguém.",
    (
        Coluna("cod_alerta", "Alerta (alertas_cemaden.csv)."),
        Coluna("codigo_cap", "Mensagem de aviso em vigor (avisos_inmet.csv)."),
        Coluna("evento", "Fenômeno do aviso."),
        Coluna("severidade", "Severidade do aviso."),
    ),
)

COBERTURA = Tabela(
    "cobertura.csv",
    "Quanto de cada dia o coletor esteve ligado, por fonte. Um alerta que não "
    "aparece num dia de cobertura baixa pode simplesmente não ter sido visto. "
    "Antes de 2026-09-28T23:49Z não há registro de cobertura.",
    (
        Coluna("dia", "Dia em UTC."),
        Coluna("fonte", "CEMADEN (janelas de 5 min) ou INMET (janelas de 30 min)."),
        Coluna("janelas_possiveis", "Janelas do dia dentro do período conhecido."),
        Coluna("janelas_com_coleta", "Janelas com ao menos uma coleta bem-sucedida."),
        Coluna("cobertura", "janelas_com_coleta / janelas_possiveis, 4 casas."),
        Coluna("coletas_com_falha", "Coletas que falharam (fonte fora do ar, rede)."),
    ),
)

TABELAS: tuple[Tabela, ...] = (ALERTAS, AVISOS, AVISO_MUNICIPIOS, ALERTA_AVISOS, COBERTURA)

_AVISO_DICIONARIO = """\
Este acervo **não é um canal oficial de alerta**. Em situação de risco, siga a
Defesa Civil do seu município (SMS 40199, Defesa Civil Alerta).

Fontes: CEMADEN (alertas) e INMET (avisos meteorológicos), coletados pelo
AlertaVida. Todos os instantes estão em UTC, no formato `AAAA-MM-DDTHH:MM:SSZ`.
CSV em UTF-8, separado por vírgula.
"""


def _utc(valor: str | None) -> str:
    if valor is None or valor == "":
        return ""
    return parse_iso_utc(valor).strftime("%Y-%m-%dT%H:%M:%SZ")


def instante_do_backup(caminho: Path) -> datetime:
    """O instante do nome `alertavida-<AAAAMMDDTHHMMSSZ>.db` (deploy/backup.py)."""
    casamento = _NOME_BACKUP.match(caminho.name)
    if casamento is None:
        raise ValueError(f"nome de backup inesperado: {caminho.name}")
    return datetime.strptime(casamento.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def escolher_backup(caminho: Path) -> Path:
    """Um arquivo é usado como está; num diretório, o backup mais recente."""
    if caminho.is_file():
        return caminho
    candidatos = sorted(p for p in caminho.glob("alertavida-*.db") if _NOME_BACKUP.match(p.name))
    if not candidatos:
        raise FileNotFoundError(f"nenhum backup alertavida-*.db em {caminho}")
    return candidatos[-1]


def abrir_somente_leitura(caminho: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{caminho.resolve().as_uri()}?mode=ro&immutable=1", uri=True)


def linhas_alertas(conexao: sqlite3.Connection) -> Iterator[list[object]]:
    for (
        cod_alerta,
        codibge,
        municipio,
        uf,
        evento,
        cobrade,
        nivel,
        inicio,
        atualizado,
        detectado,
        status,
        resolucao,
        latitude,
        longitude,
    ) in conexao.execute(
        """
        SELECT a.cod_alerta, a.codibge, a.municipio, a.uf, a.evento, a.cobrade_codigo,
               a.nivel, a.datahoracriacao, a.ult_atualizacao, a.detectado_em,
               a.status_interno,
               CASE WHEN a.status_interno = 'RESOLVIDO' THEN (
                   SELECT MAX(e.criado_em) FROM eventos e
                   WHERE e.tipo = 'AlertaResolvido' AND e.agregado_id = a.id
               ) END,
               a.latitude, a.longitude
        FROM alertas a
        WHERE a.fonte = 'CEMADEN'
        ORDER BY a.datahoracriacao, a.cod_alerta
        """
    ):
        yield [
            cod_alerta,
            codibge,
            municipio,
            uf,
            evento,
            cobrade or "",
            nivel,
            _utc(inicio),
            _utc(atualizado),
            _utc(detectado),
            status,
            _utc(resolucao),
            latitude,
            longitude,
        ]


def linhas_avisos(conexao: sqlite3.Connection) -> Iterator[list[object]]:
    for linha in conexao.execute(
        """
        SELECT a.codigo_cap, a.id_aviso, a.id_sequencia, a.evento, a.severidade,
               a.inicio, a.fim, a.encerrado, a.primeira_coleta, a.ultima_coleta,
               (SELECT COUNT(*) FROM aviso_municipios m WHERE m.aviso_id = a.id)
        FROM avisos_meteorologicos a
        ORDER BY a.inicio, a.codigo_cap
        """
    ):
        cap, id_aviso, seq, evento, severidade, inicio, fim, encerrado, primeira, ultima, n = linha
        yield [
            cap,
            id_aviso,
            seq,
            evento,
            severidade,
            _utc(inicio),
            _utc(fim),
            encerrado,
            _utc(primeira),
            _utc(ultima),
            n,
        ]


def linhas_aviso_municipios(conexao: sqlite3.Connection) -> Iterator[list[object]]:
    for cap, codibge in conexao.execute(
        """
        SELECT a.codigo_cap, m.codibge
        FROM aviso_municipios m JOIN avisos_meteorologicos a ON a.id = m.aviso_id
        ORDER BY a.codigo_cap, m.codibge
        """
    ):
        yield [cap, codibge]


def linhas_alerta_avisos(conexao: sqlite3.Connection) -> Iterator[list[object]]:
    alertas = conexao.execute(
        """
        SELECT cod_alerta, codibge, datahoracriacao FROM alertas
        WHERE fonte = 'CEMADEN' AND codibge IS NOT NULL AND datahoracriacao IS NOT NULL
        ORDER BY datahoracriacao, cod_alerta
        """
    ).fetchall()
    for cod_alerta, codibge, inicio in alertas:
        for aviso in consultar_avisos_vigentes(conexao, codibge, inicio):
            yield [cod_alerta, aviso.codigo_cap, aviso.evento, aviso.severidade]


@dataclass(frozen=True)
class Coleta:
    instante: datetime
    fonte: str
    falha: bool


def coletas_do_banco(conexao: sqlite3.Connection) -> Iterator[Coleta]:
    """Backups anteriores a #161 não têm `rodadas`: a cobertura deles está toda
    nas extrações do journal."""
    existe = conexao.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'rodadas'"
    ).fetchone()
    if existe is None:
        return
    for iniciada_em, fonte, falha in conexao.execute(
        "SELECT iniciada_em, fonte, falha FROM rodadas"
    ):
        yield Coleta(parse_iso_utc(iniciada_em), fonte, bool(falha))


def coletas_historicas(arquivos: Iterable[Path]) -> Iterator[Coleta]:
    for arquivo in arquivos:
        with arquivo.open(encoding="utf-8", newline="") as entrada:
            for linha in csv.DictReader(entrada):
                yield Coleta(
                    parse_iso_utc(linha["instante_utc"].replace("Z", "+00:00")),
                    linha["fonte"],
                    linha["falha"] == "1",
                )


def calcular_cobertura(coletas: Iterable[Coleta], ate: datetime) -> Iterator[list[object]]:
    """Por (dia, fonte): janelas com ao menos uma coleta bem-sucedida.

    O período conhecido de cada fonte vai da sua primeira coleta registrada
    (com ou sem falha) até `ate` (o instante do backup). Só janelas que já
    TERMINARAM em `ate` contam — uma janela em curso no backup não é falta de
    coleta.
    """
    por_fonte: dict[str, list[Coleta]] = defaultdict(list)
    for coleta in coletas:
        if coleta.fonte in JANELA_SEGUNDOS and coleta.instante < ate:
            por_fonte[coleta.fonte].append(coleta)

    saida: list[list[object]] = []
    for fonte, lista in por_fonte.items():
        janela = JANELA_SEGUNDOS[fonte]
        primeira = math.floor(min(c.instante for c in lista).timestamp() / janela)
        ultima = math.floor(ate.timestamp() / janela) - 1
        if ultima < primeira:
            continue
        no_periodo = [c for c in lista if math.floor(c.instante.timestamp() / janela) <= ultima]
        cobertas = {math.floor(c.instante.timestamp() / janela) for c in no_periodo if not c.falha}
        falhas_por_dia: dict[date, int] = defaultdict(int)
        for c in no_periodo:
            if c.falha:
                falhas_por_dia[c.instante.date()] += 1

        dia = datetime.fromtimestamp(primeira * janela, UTC).date()
        fim = datetime.fromtimestamp(ultima * janela, UTC).date()
        while dia <= fim:
            inicio_dia = datetime(dia.year, dia.month, dia.day, tzinfo=UTC).timestamp()
            de = max(primeira, int(inicio_dia) // janela)
            ate_janela = min(ultima, int(inicio_dia + 86400) // janela - 1)
            possiveis = ate_janela - de + 1
            com_coleta = sum(1 for k in range(de, ate_janela + 1) if k in cobertas)
            saida.append(
                [
                    dia.isoformat(),
                    fonte,
                    possiveis,
                    com_coleta,
                    f"{com_coleta / possiveis:.4f}",
                    falhas_por_dia.get(dia, 0),
                ]
            )
            dia += timedelta(days=1)
    saida.sort(key=lambda linha: (str(linha[0]), str(linha[1])))
    yield from saida


def gerar_dicionario(tabelas: Sequence[Tabela] = TABELAS) -> str:
    partes = ["# Dicionário de dados — acervo AlertaVida", "", _AVISO_DICIONARIO]
    for tabela in tabelas:
        partes += [
            f"## `{tabela.arquivo}`",
            "",
            tabela.descricao,
            "",
            "| Coluna | Descrição |",
            "|---|---|",
        ]
        partes += [f"| `{c.nome}` | {c.descricao} |" for c in tabela.colunas]
        partes.append("")
    return "\n".join(partes)


def _escrever(destino: Path, tabela: Tabela, linhas: Iterable[Sequence[object]]) -> int:
    total = 0
    with (destino / tabela.arquivo).open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida, lineterminator="\n")
        escritor.writerow(tabela.cabecalho)
        for linha in linhas:
            if len(linha) != len(tabela.colunas):
                raise ValueError(
                    f"{tabela.arquivo}: {len(linha)} campos, esperado {len(tabela.colunas)}"
                )
            escritor.writerow(linha)
            total += 1
    return total


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as entrada:
        for bloco in iter(lambda: entrada.read(1 << 20), b""):
            digest.update(bloco)
    return digest.hexdigest()


def exportar(backup: Path, saida: Path, rodadas_historicas: Sequence[Path]) -> dict[str, object]:
    """Escreve o acervo em `saida` (substituído por inteiro) e devolve os metadados."""
    ate = instante_do_backup(backup)
    temporario = saida.with_name(saida.name + ".tmp")
    if temporario.exists():
        shutil.rmtree(temporario)
    temporario.mkdir(parents=True)

    with contextlib.closing(abrir_somente_leitura(backup)) as conexao:
        contagens = {
            ALERTAS.arquivo: _escrever(temporario, ALERTAS, linhas_alertas(conexao)),
            AVISOS.arquivo: _escrever(temporario, AVISOS, linhas_avisos(conexao)),
            AVISO_MUNICIPIOS.arquivo: _escrever(
                temporario, AVISO_MUNICIPIOS, linhas_aviso_municipios(conexao)
            ),
            ALERTA_AVISOS.arquivo: _escrever(
                temporario, ALERTA_AVISOS, linhas_alerta_avisos(conexao)
            ),
        }
        coletas = [*coletas_historicas(rodadas_historicas), *coletas_do_banco(conexao)]
    contagens[COBERTURA.arquivo] = _escrever(
        temporario, COBERTURA, calcular_cobertura(coletas, ate)
    )

    (temporario / "DICIONARIO.md").write_text(gerar_dicionario(), encoding="utf-8")
    metadados: dict[str, object] = {
        "versao_formato": VERSAO_FORMATO,
        "backup": backup.name,
        "backup_sha256": _sha256(backup),
        "backup_instante_utc": ate.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rodadas_historicas": [p.name for p in rodadas_historicas],
        "linhas": contagens,
    }
    (temporario / "metadados.json").write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if saida.exists():
        shutil.rmtree(saida)
    temporario.rename(saida)
    return metadados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exporta o acervo AlertaVida a partir de um backup."
    )
    parser.add_argument(
        "--backup", type=Path, required=True, help="arquivo de backup ou diretório deles"
    )
    parser.add_argument(
        "--saida", type=Path, required=True, help="diretório de saída (substituído)"
    )
    parser.add_argument(
        "--rodadas-historicas",
        type=Path,
        nargs="*",
        default=RODADAS_HISTORICAS_PADRAO,
        help="CSVs de rodadas extraídos do journal (padrão: wiki/raw/rodadas-journal-*.csv)",
    )
    args = parser.parse_args(argv)
    metadados = exportar(escolher_backup(args.backup), args.saida, args.rodadas_historicas)
    print(json.dumps(metadados, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
