"""Extrai do journal as rodadas de coleta concluídas (issue #158).

Até a tabela `rodadas` existir, a cobertura da coleta só está nos journals:
o banco guarda `visto_ultima_vez` por alerta, não as rodadas. Sem isso, "nenhum
alerta" e "coletor desligado" são indistinguíveis no acervo.

Uma rodada de alertas é um bloco de `formatar_relatorio()`:

    <agora ISO>: rodada concluída
      CEMADEN: 23 coletados (...)  |  CEMADEN: FALHA de coleta (0.12s)
      EONET: ...
    Total: N alertas

O instante da rodada é o `agora` do cabeçalho (UTC, gravado pelo próprio
orquestrador), não o carimbo do journal. A coleta de avisos do INMET (#153)
é um job à parte, sem cabeçalho; o instante dela é o carimbo do journal.

Saída: CSV com uma linha por (rodada, fonte) — `instante_utc`, `fonte`,
`coletados` (vazio quando falhou), `falha` (0/1). Só carimbos e contagens:
nenhum nome de máquina, nenhum caminho.

Uso:

    journalctl -u alertavida.service -o short-iso --no-pager \\
        | uv run python -m scripts.extrair_rodadas_journal --saida rodadas.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

# Carimbo `-o short-iso` do journalctl: primeira coluna da linha.
_CARIMBO = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:?\d{2})\s")
_CABECALHO = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d:.]+[+-]\d{2}:\d{2}): rodada concluída$")
_FONTE_OK = re.compile(r"^\s+(CEMADEN|EONET): (\d+) coletados ")
_FONTE_FALHA = re.compile(r"^\s+(CEMADEN|EONET): FALHA de coleta ")
_INMET_OK = re.compile(r"^\s+INMET \(avisos\): (\d+) vigentes ou futuros ")
_INMET_FALHA = re.compile(r"^\s+INMET \(avisos\): FALHA de coleta ")
_TOTAL = re.compile(r"^Total: \d+ alertas$")


@dataclass(frozen=True, order=True)
class RodadaFonte:
    instante_utc: datetime
    fonte: str
    coletados: int | None
    falha: bool


def _utc(valor: str) -> datetime:
    return datetime.fromisoformat(valor).astimezone(UTC).replace(microsecond=0)


def _mensagem(linha: str) -> str:
    """O texto que o processo escreveu, sem o prefixo `carimbo host proc[pid]: `."""
    _, separador, resto = linha.partition("]: ")
    return resto if separador else linha


def extrair(linhas: Iterable[str]) -> Iterator[RodadaFonte]:
    rodada_atual: datetime | None = None
    for bruta in linhas:
        linha = bruta.rstrip("\n")
        mensagem = _mensagem(linha)

        cabecalho = _CABECALHO.search(mensagem)
        if cabecalho:
            rodada_atual = _utc(cabecalho.group(1))
            continue
        if _TOTAL.match(mensagem):
            rodada_atual = None
            continue

        if rodada_atual is not None:
            ok = _FONTE_OK.match(mensagem)
            if ok:
                yield RodadaFonte(rodada_atual, ok.group(1), int(ok.group(2)), False)
                continue
            falha = _FONTE_FALHA.match(mensagem)
            if falha:
                yield RodadaFonte(rodada_atual, falha.group(1), None, True)
                continue

        carimbo = _CARIMBO.match(linha)
        if carimbo is None:
            continue
        inmet_ok = _INMET_OK.match(mensagem)
        if inmet_ok:
            yield RodadaFonte(_utc(carimbo.group(1)), "INMET", int(inmet_ok.group(1)), False)
        elif _INMET_FALHA.match(mensagem):
            yield RodadaFonte(_utc(carimbo.group(1)), "INMET", None, True)


def escrever_csv(rodadas: Iterable[RodadaFonte], saida: TextIO) -> None:
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(["instante_utc", "fonte", "coletados", "falha"])
    for r in sorted(set(rodadas)):
        escritor.writerow(
            [
                r.instante_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                r.fonte,
                "" if r.coletados is None else r.coletados,
                int(r.falha),
            ]
        )


def resumir(rodadas: Iterable[RodadaFonte]) -> str:
    """Rodadas de alertas concluídas por mês, sobre 288 possíveis por dia."""
    instantes = sorted({r.instante_utc for r in rodadas if r.fonte != "INMET"})
    if not instantes:
        return "nenhuma rodada encontrada"
    por_mes = Counter(i.strftime("%Y-%m") for i in instantes)
    linhas = [
        f"rodadas de alertas: {len(instantes)} "
        f"({instantes[0]:%Y-%m-%dT%H:%MZ} → {instantes[-1]:%Y-%m-%dT%H:%MZ})"
    ]
    linhas += [f"  {mes}: {n}" for mes, n in sorted(por_mes.items())]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entrada", type=Path, help="journal em texto (padrão: stdin)")
    parser.add_argument("--saida", type=Path, required=True, help="CSV de saída")
    args = parser.parse_args(argv)

    if args.entrada is None:
        rodadas = list(extrair(sys.stdin))
    else:
        with args.entrada.open(encoding="utf-8") as entrada:
            rodadas = list(extrair(entrada))

    with args.saida.open("w", encoding="utf-8", newline="") as saida:
        escrever_csv(rodadas, saida)
    print(resumir(rodadas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
