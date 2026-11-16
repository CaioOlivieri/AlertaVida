"""O que a coordenada de um alerta CEMADEN representa? (issue #136)

Discriminador da Round 2 da Camada 5 (wiki/projects/layer-5-correlation.md):
vários alertas no MESMO município — coordenadas idênticas ⇒ ponto fixo por
município (centroide); coordenadas variando ⇒ ponto de risco.

Duas evidências independentes, ambas lidas, nunca escritas:

- o banco (`alertas`): a coordenada de cada alerta CEMADEN, gravada na
  criação — responde "alertas diferentes do mesmo município caem no mesmo
  ponto?";
- as capturas cruas do surge watch (#70): a mesma `cod_alerta` em payloads
  sucessivos — responde "a coordenada de um alerta muda depois de publicada?",
  o que o banco não vê (só grava a posição no CRIADO).

Uso (o banco é aberto em modo somente leitura; aponte para uma cópia de
backup, nunca para o banco vivo):

    uv run python -m scripts.analise_coordenada_cemaden \\
        --banco /var/lib/alertavida/backups/alertavida-<ts>.db \\
        --capturas data/weathernext_cemaden_captures_archive
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from alertavida.domain.correlacao import distancia_haversine_km

# Duas coordenadas são "a mesma" se coincidem até a 9ª casa decimal (~0,1 mm).
# O payload traz 12 casas; arredondar só absorve ruído de float.
CASAS_DECIMAIS: int = 9

Ponto = tuple[float, float]


@dataclass(frozen=True)
class AlertaCoordenada:
    codibge: int
    municipio: str
    uf: str
    cod_alerta: str
    latitude: float
    longitude: float

    @property
    def ponto(self) -> Ponto:
        return (round(self.latitude, CASAS_DECIMAIS), round(self.longitude, CASAS_DECIMAIS))


@dataclass(frozen=True)
class ResultadoMunicipio:
    codibge: int
    municipio: str
    uf: str
    alertas: int
    pontos_distintos: int
    espalhamento_km: float

    @property
    def identicas(self) -> bool:
        return self.pontos_distintos == 1


@dataclass(frozen=True)
class ResultadoCapturas:
    observacoes: int
    alertas: int
    alertas_com_coordenada_alterada: int


def carregar_alertas_banco(caminho: Path) -> list[AlertaCoordenada]:
    """Alertas CEMADEN com município conhecido. Abre o banco em `mode=ro`."""
    uri = f"file:{caminho}?mode=ro"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as conexao:
        linhas = conexao.execute(
            """
            SELECT codibge, municipio, uf, cod_alerta, latitude, longitude
            FROM alertas
            WHERE fonte = 'CEMADEN' AND codibge IS NOT NULL
            """
        ).fetchall()
    return [AlertaCoordenada(*linha) for linha in linhas]


def classificar_municipios(alertas: Iterable[AlertaCoordenada]) -> list[ResultadoMunicipio]:
    """Um resultado por município com 2+ alertas — só esses discriminam."""
    por_municipio: dict[int, list[AlertaCoordenada]] = defaultdict(list)
    for alerta in alertas:
        por_municipio[alerta.codibge].append(alerta)

    resultados = []
    for codibge, grupo in por_municipio.items():
        if len(grupo) < 2:
            continue
        pontos = sorted({a.ponto for a in grupo})
        espalhamento = max(
            (
                distancia_haversine_km(p[0], p[1], q[0], q[1])
                for i, p in enumerate(pontos)
                for q in pontos[i + 1 :]
            ),
            default=0.0,
        )
        resultados.append(
            ResultadoMunicipio(
                codibge=codibge,
                municipio=grupo[0].municipio,
                uf=grupo[0].uf,
                alertas=len(grupo),
                pontos_distintos=len(pontos),
                espalhamento_km=espalhamento,
            )
        )
    return sorted(resultados, key=lambda r: (-r.alertas, r.codibge))


def analisar_capturas(diretorio: Path) -> ResultadoCapturas:
    """A coordenada de uma mesma `cod_alerta` muda entre payloads sucessivos?

    Arquivo ilegível ou sem `alertas` é pulado — uma captura truncada não
    invalida as outras.
    """
    pontos_por_alerta: dict[str, set[Ponto]] = defaultdict(set)
    observacoes = 0
    for arquivo in sorted(diretorio.glob("cemaden_raw_*.json")):
        try:
            payload = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        itens = payload.get("alertas") if isinstance(payload, dict) else None
        if not isinstance(itens, list):
            continue
        for item in itens:
            try:
                ponto = (
                    round(float(item["latitude"]), CASAS_DECIMAIS),
                    round(float(item["longitude"]), CASAS_DECIMAIS),
                )
                cod = str(item["cod_alerta"])
            except (KeyError, TypeError, ValueError):
                continue
            pontos_por_alerta[cod].add(ponto)
            observacoes += 1
    return ResultadoCapturas(
        observacoes=observacoes,
        alertas=len(pontos_por_alerta),
        alertas_com_coordenada_alterada=sum(len(p) > 1 for p in pontos_por_alerta.values()),
    )


def formatar_relatorio(
    alertas: list[AlertaCoordenada],
    municipios: list[ResultadoMunicipio],
    capturas: ResultadoCapturas | None,
) -> str:
    identicos = sum(r.identicas for r in municipios)
    linhas = [
        "## Banco — alertas diferentes no mesmo município",
        "",
        f"- alertas CEMADEN com município: {len(alertas)}",
        f"- municípios distintos: {len({a.codibge for a in alertas})}",
        f"- municípios com 2+ alertas: {len(municipios)} "
        f"({sum(r.alertas for r in municipios)} alertas)",
        f"- desses, todas as coordenadas idênticas: {identicos}",
        f"- desses, coordenadas variando: {len(municipios) - identicos}",
        f"- maior espalhamento dentro de um município: "
        f"{max((r.espalhamento_km for r in municipios), default=0.0):.3f} km",
        "",
        "| codibge | município | UF | alertas | pontos distintos | espalhamento km |",
        "|---|---|---|---|---|---|",
    ]
    for r in municipios[:10]:
        linhas.append(
            f"| {r.codibge} | {r.municipio} | {r.uf} | {r.alertas} | "
            f"{r.pontos_distintos} | {r.espalhamento_km:.3f} |"
        )
    if capturas is not None:
        linhas += [
            "",
            "## Capturas — a mesma alerta em payloads sucessivos",
            "",
            f"- observações (item × payload): {capturas.observacoes}",
            f"- alertas distintos: {capturas.alertas}",
            f"- alertas cuja coordenada mudou: {capturas.alertas_com_coordenada_alterada}",
        ]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--banco", type=Path, required=True)
    parser.add_argument("--capturas", type=Path)
    args = parser.parse_args(argv)

    if not args.banco.exists():
        print(f"Banco não encontrado: {args.banco}", file=sys.stderr)
        return 1
    alertas = carregar_alertas_banco(args.banco)
    municipios = classificar_municipios(alertas)
    capturas = analisar_capturas(args.capturas) if args.capturas else None
    print(formatar_relatorio(alertas, municipios, capturas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
