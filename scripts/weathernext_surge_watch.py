"""WeatherNext surge watch — daily deterministic surge-risk artifact (issue #70).

Fase B da trilha WeatherNext ([[decisions/weathernext-anticipation-not-datasource]]):
o discriminador centroide-vs-ponto-de-risco do Round 2
([[projects/layer-5-correlation]]) precisa de vários alertas CEMADEN no MESMO
município, e isso só acontece durante um surto de chuva. Este script roda uma
vez por dia, consulta o WeatherNext 2 (tabela `mean`, nunca o ensemble — regra
de custo já decidida) para os próximos 48h sobre o bbox do Brasil, e grava um
indicador determinístico local. Quando qualquer célula de grade cruza o
limiar provisório, `watch_mode` liga — `scripts/weathernext_cemaden_capture.py`
lê essa flag para decidir se aciona a captura de alta frequência.

Fora do runtime por design (nenhuma dependência nova em [project.dependencies],
nada em `domain/correlacao.py`, nada voltado ao usuário final): usa o binário
`bq` (subprocess) para falar com BigQuery — não a lib cliente Python — e roda
sob a conta do mantenedor, não `alertavida` (decisão registrada na decision
page: a captura precisa da credencial ADC pessoal em ~/.config/gcloud, que o
usuário de serviço systemd não atravessa).

Query e custo validados na análise offline da #69
(wiki/raw/analise-weathernext-skill-2026-08-24.md): filtro por `init_time`
(coluna de partição) + `ST_INTERSECTSBOX` sobre `geography`. O dry-run cobra
o mesmo teto pessimista (~4.19 GB) independente do bbox — o corte real vem do
clustering em tempo de execução, medido em 2026-09-05 para a query real desta
issue (bbox Brasil, janela de 48h): 374.341.632 bytes (~374 MB), ~57x abaixo
do teto usado para `--maximum_bytes_billed` (ver decision page).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from alertavida.domain.geographic import FAIXA_BRASIL

logger = logging.getLogger(__name__)

# --- BigQuery: tabela mean, validada em wiki/raw/analise-weathernext-skill-2026-08-24.md ---
PROJECT: Final[str] = "weathernexttest-506315"
DATASET: Final[str] = "weathernext_2_mean"
TABLE: Final[str] = "weathernext_2_0_0_mean"

# Regra de custo já decidida (issue #69/#70): SÓ a tabela mean, nunca o
# ensemble (45x mais caro). Teto = custo medido por partição/variável
# (4.186.183.680 bytes, wiki/raw/analise-weathernext-skill-2026-08-24.md),
# arredondado para cima. 30 dias neste teto = 126 GB/mês = 12,6% do free
# tier de 1 TiB — o número citado na decisão de custo da issue #70. O custo
# real medido para a query desta issue é bem menor (ver docstring do módulo);
# o teto continua no valor pessimista porque é uma GUARDA, não uma previsão.
MAXIMUM_BYTES_BILLED: Final[int] = 4_200_000_000

# `bq query --max_rows` trunca em silêncio quando o resultado real excede o
# limite — sem erro, sem aviso, só menos linhas do que existem de verdade.
# Medido em 2026-09-05: 25.758 células no bbox do Brasil, 40x de folga. O
# aviso abaixo (MAX_ROWS_WARNING_RATIO) é o único jeito de perceber se essa
# folga um dia encolher, já que um truncamento silencioso deixaria o
# indicador incompleto sem nenhum sinal de erro.
MAX_ROWS: Final[int] = 1_000_000
MAX_ROWS_WARNING_RATIO: Final[float] = 0.9

# 4 rodadas/dia, publicadas ~7h30 após o init (wiki/decisions/
# weathernext-anticipation-not-datasource.md).
RUN_HOURS_UTC: Final[tuple[int, ...]] = (0, 6, 12, 18)
PUBLISH_LATENCY: Final[timedelta] = timedelta(hours=7, minutes=30)

HORIZON_HOURS: Final[int] = 48

# PROVISÓRIA — rotulada como tal por disciplina wiki/_schema.md regra 1,
# mesmo padrão de domain/correlacao.py. Soma dos passos de 6h
# (`total_precipitation_6hr`, convertido de metros para mm) na janela de 48h,
# por célula de grade 0.25°. Calibrar NÃO é escopo desta issue (#70) — ver
# decision page para o raciocínio por trás do valor inicial.
SURGE_WATCH_THRESHOLD_MM_48H: Final[float] = 50.0

ATTRIBUTION_NOTICE: Final[str] = (
    "Source: Google DeepMind WeatherNext 2 (weathernext_2_mean table). "
    "CC BY 4.0 for data whose valid time is more than 48h in the past; GDM "
    "Real-Time Weather Forecasting Experimental Data Terms of Use otherwise. "
    "Internal use only (Terms Sec. 2(a)) — never displayed to end users. "
    "This data is intended for experimental modelling only and is not "
    "intended, validated, or approved for real world use (Terms Sec. 4(b)). "
    "Does not replace official alerts from Defesa Civil, CEMADEN, INMET or "
    "other government agencies."
)

ARTIFACT_PATH_DEFAULT: Final[Path] = (
    Path(__file__).resolve().parent.parent / "data" / "weathernext_surge_watch.json"
)
ENV_ARTIFACT_PATH: Final[str] = "ALERTAVIDA_WEATHERNEXT_ARTIFACT_PATH"


def artifact_path() -> Path:
    """Resolve o caminho do artefato, mesma convenção de `database.db_path()`.

    `ALERTAVIDA_WEATHERNEXT_ARTIFACT_PATH` sobrepõe o default
    (`data/weathernext_surge_watch.json`, gitignored). Valor ausente ou em
    branco cai no default, sem levantar.
    """
    valor = os.getenv(ENV_ARTIFACT_PATH)
    if valor is None or not valor.strip():
        return ARTIFACT_PATH_DEFAULT
    return Path(valor)


def ultimo_init_time_disponivel(agora: datetime) -> datetime:
    """Maior `init_time` cuja publicação (init + 7h30) já ocorreu até `agora`.

    Considera as rodadas de hoje e de ontem — nunca menos que uma rodada
    disponível, mesmo logo após a virada do dia UTC.
    """
    candidatos = []
    for dias_atras in (0, 1):
        dia = (agora - timedelta(days=dias_atras)).date()
        for hora in RUN_HOURS_UTC:
            candidato = datetime(dia.year, dia.month, dia.day, hora, tzinfo=timezone.utc)
            if candidato + PUBLISH_LATENCY <= agora:
                candidatos.append(candidato)
    if not candidatos:
        raise RuntimeError(
            f"Nenhum init_time do WeatherNext publicado ainda para 'agora'={agora.isoformat()}"
        )
    return max(candidatos)


def montar_query(init_time: datetime, janela_inicio: datetime, janela_fim: datetime) -> str:
    """SQL validado em wiki/raw/analise-weathernext-skill-2026-08-24.md,
    adaptado de ponto+raio para bbox do Brasil (`ST_INTERSECTSBOX`,
    verificado empiricamente contra o projeto real em 2026-09-05)."""
    return (
        "SELECT geography, f.time AS valid_time, "
        "f.total_precipitation_6hr AS precip_6hr\n"
        f"FROM `{PROJECT}.{DATASET}.{TABLE}`, UNNEST(forecast) AS f\n"
        f'WHERE init_time = TIMESTAMP("{init_time:%Y-%m-%d %H:%M:%S}")\n'
        f"  AND ST_INTERSECTSBOX(geography, {FAIXA_BRASIL.lon_min}, "
        f"{FAIXA_BRASIL.lat_min}, {FAIXA_BRASIL.lon_max}, {FAIXA_BRASIL.lat_max})\n"
        f'  AND f.time >= TIMESTAMP("{janela_inicio:%Y-%m-%d %H:%M:%S}")\n'
        f'  AND f.time <  TIMESTAMP("{janela_fim:%Y-%m-%d %H:%M:%S}")'
    )


class OrcamentoExcedidoError(Exception):
    """Guarda de custo (`--maximum_bytes_billed`) disparou — esperado, não é bug.

    Texto de correspondência ("exceeded limit for bytes billed") verificado
    empiricamente contra o projeto real em 2026-09-05: `bq query` recusa a
    query e fatura 0 bytes (`errorResult.reason == "bytesBilledLimitExceeded"`),
    exatamente o comportamento já registrado na decision page da #69.

    O casamento por substring é FRÁGIL por natureza — texto de erro de um
    serviço externo pode mudar sem aviso. Aceito deliberadamente porque falha
    na direção segura: se o texto parar de bater, `executar_query_bq` cai no
    branch de `CalledProcessError` (falha ALTA, visível no status da unit),
    nunca em gasto silencioso sem sinal nenhum. NÃO trocar por um `except`
    largo que trate qualquer falha do `bq` como guarda de custo — isso
    inverteria a direção segura e esconderia exatamente o sinal que este
    desenho existe para preservar (autenticação/rede quebradas passariam
    batidas como "orçamento excedido, tudo bem, pula pro dia seguinte").
    """


def executar_query_bq(sql: str) -> list[dict]:
    """Roda `sql` via o binário `bq` (subprocess, sem lib cliente Python).

    Distingue os dois modos de falha por desenho explícito do mantenedor:
    o guarda de custo disparando é o guarda FUNCIONANDO (log e segue);
    qualquer outra falha do `bq` (autenticação, rede, SQL inválido) é
    defeito/infra e propaga como `subprocess.CalledProcessError`.
    """
    resultado = subprocess.run(
        [
            "bq",
            "query",
            "--use_legacy_sql=false",
            "--format=json",
            f"--max_rows={MAX_ROWS}",
            f"--maximum_bytes_billed={MAXIMUM_BYTES_BILLED}",
            sql,
        ],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        if "exceeded limit for bytes billed" in resultado.stderr.lower():
            raise OrcamentoExcedidoError(resultado.stderr.strip())
        raise subprocess.CalledProcessError(
            resultado.returncode,
            ["bq", "query", "..."],
            output=resultado.stdout,
            stderr=resultado.stderr,
        )
    saida = resultado.stdout.strip()
    if not saida:
        return []
    linhas = list(json.loads(saida))

    if len(linhas) >= MAX_ROWS * MAX_ROWS_WARNING_RATIO:
        logger.warning(
            "Resultado com %d linhas, perto do teto --max_rows=%d do bq — "
            "possível truncamento silencioso; indicador pode estar incompleto.",
            len(linhas),
            MAX_ROWS,
        )

    return linhas


def indicador_por_regiao(linhas: list[dict]) -> dict[str, float]:
    """Soma `precip_6hr` (metros -> mm) por célula de grade (`geography`)."""
    acumulado: dict[str, float] = defaultdict(float)
    for linha in linhas:
        acumulado[linha["geography"]] += float(linha["precip_6hr"]) * 1000.0
    return dict(acumulado)


def montar_artefato(
    *, init_time: datetime, gerado_em: datetime, indicador: dict[str, float]
) -> dict:
    """Monta o artefato JSON — atribuição e aviso experimental embutidos."""
    regioes_em_risco = {
        geo: round(mm, 2)
        for geo, mm in indicador.items()
        if mm >= SURGE_WATCH_THRESHOLD_MM_48H
    }
    return {
        "generated_at": gerado_em.isoformat(),
        "init_time": init_time.isoformat(),
        "horizon_hours": HORIZON_HOURS,
        "attribution": ATTRIBUTION_NOTICE,
        "threshold_mm_48h": SURGE_WATCH_THRESHOLD_MM_48H,
        "threshold_is_provisional": True,
        "watch_mode": bool(regioes_em_risco),
        "regions_at_risk": regioes_em_risco,
        "regions_evaluated": len(indicador),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    agora = datetime.now(timezone.utc)

    try:
        init_time = ultimo_init_time_disponivel(agora)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    janela_inicio = agora
    janela_fim = agora + timedelta(hours=HORIZON_HOURS)
    sql = montar_query(init_time, janela_inicio, janela_fim)

    try:
        linhas = executar_query_bq(sql)
    except OrcamentoExcedidoError as exc:
        logger.warning(
            "Guarda de custo disparou (--maximum_bytes_billed=%d): %s. "
            "Pulando esta rodada; artefato anterior (se existir) mantido.",
            MAXIMUM_BYTES_BILLED,
            exc,
        )
        return 0
    except subprocess.CalledProcessError as exc:
        logger.error("Falha ao consultar BigQuery (não é o guarda de custo): %s", exc.stderr)
        return 1

    indicador = indicador_por_regiao(linhas)
    artefato = montar_artefato(init_time=init_time, gerado_em=agora, indicador=indicador)

    caminho = artifact_path()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(artefato, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        "Artefato gravado em %s — %d regiões avaliadas, %d em risco, watch_mode=%s",
        caminho,
        artefato["regions_evaluated"],
        len(artefato["regions_at_risk"]),
        artefato["watch_mode"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
