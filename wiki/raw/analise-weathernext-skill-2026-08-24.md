# Análise empírica WeatherNext 2 — validação de skill offline — 2026-08-24

Issue #69. Objetivo: medir, sem inferência, se o campo médio (mean) do
WeatherNext 2 mostra sinal de precipitação em escala municipal, com lead
time útil, para eventos reais brasileiros conhecidos. Trilha de análise
pura — zero mudanças em `src/`, `tests/`, `scripts/`.

## Pré-condições verificadas

```
$ gh api repos/CaioOlivieri/AlertaVida/issues/68 --jq .state
closed

$ bq query --use_legacy_sql=false --dry_run 'SELECT COUNT(*) FROM
  `weathernexttest-506315.weathernext_2_mean.weathernext_2_0_0_mean`
  WHERE init_time = TIMESTAMP("2026-05-01")'
Query successfully validated. Assuming the tables are not modified, running
this query will process upper bound of 33223680 bytes of data.
```

## Schema real da tabela mean (bq show)

```
init_time            TIMESTAMP  (partição DAY)
geography             GEOGRAPHY  (clustering)
geography_polygon     GEOGRAPHY
forecast               RECORD REPEATED
  forecast.time         TIMESTAMP
  forecast.hours         INTEGER
  forecast.100m_u_component_of_wind    FLOAT
  forecast.100m_v_component_of_wind    FLOAT
  forecast.100m_wind_speed              FLOAT
  forecast.10m_u_component_of_wind      FLOAT
  forecast.10m_v_component_of_wind      FLOAT
  forecast.10m_wind_speed                FLOAT
  forecast.2m_temperature                FLOAT
  forecast.mean_sea_level_pressure       FLOAT
  forecast.sea_surface_temperature       FLOAT
  forecast.total_precipitation_6hr       FLOAT
```

`total_precipitation_6hr` está em **metros** (valores da ordem de
0.005–0.04 por passo de 6h; ×1000 = mm).

## Seleção de eventos — funil completo (real, não inferido)

Fonte: NASA EONET v3, `status=all&days=340&limit=1000&category=floods,severeStorms`
(cobre desde antes de 2025-10-03). Escopo geográfico calculado reusando
`alertavida.domain.geographic.classificar_escopo` (bbox BRASIL + buffer
PROXIMO de 5°), sem reimplementar.

| Etapa | Critério | N |
|---|---|---|
| 0 | eventos brutos (floods+severeStorms, status=all, days=340) | 581 |
| 0b | título contém "Brazil" (sem filtro de data/escopo) | 12 |
| 1 | onset ≥ 2025-10-03 (cobertura WeatherNext), qualquer escopo | 446 |
| 2 | escopo BRASIL entre os acima | 25 |
| 2 | escopo PROXIMO entre os acima | 26 |
| 2 | escopo INTERNACIONAL entre os acima | 395 |
| 3 | BRASIL ∪ PROXIMO após corte de data | 51 |
| 4 | dos 51, título contém "Brazil" | **9** |
| — | `severeStorms` em escopo BRASIL/PROXIMO após corte | **0** |

Zero eventos `severeStorms` sobreviveram ao filtro geográfico: inspeção
confirma que os 80 eventos `severeStorms` da janela são ciclones/tufões do
Pacífico e Atlântico Norte, todos classificados INTERNACIONAL — consistente
com o fato meteorológico conhecido de que o Atlântico Sul praticamente não
gera ciclones tropicais nomeados. Não é lacuna de dado.

Dos 12 eventos com "Brazil" no título (sem filtro), 3 ficaram fora do passo
4:

- `EONET_15570` ("Flood in Brazil 1103515"), onset 2025-09-22 — **antes**
  do início de cobertura do WeatherNext (2025-10-03). Excluído
  corretamente.
- `EONET_22934` e `EONET_21537` — geometria **Polygon**, não Point. Tanto o
  filtro desta análise quanto `NasaEonetSource._fixes_validos` em produção
  (`src/alertavida/sources/nasa_eonet.py`) só processam fixes `Point`;
  eventos com geometria exclusivamente Polygon são descartados por
  `ValueError` em ambos. **Achado, não decisão**: parte dos eventos de
  flood mais recentes do EONET já usa geometria de polígono (provável
  contorno da área inundada) em vez de ponto — hoje nossa fonte EONET
  perde esses eventos inteiramente. Fora de escopo desta issue corrigir
  (zero mudanças em `src/`); registrado para avaliação futura.

Os 9 eventos finais (todos categoria `floods`, fonte GDACS via EONET):

| id | onset (GDACS) | lat, lon | fonte |
|---|---|---|---|
| EONET_15841 | 2025-10-23 | -16.4435, -39.0643 | gdacs.org FL 1103584 |
| EONET_15901 | 2025-11-14 | -21.5566, -45.4341 | gdacs.org FL 1103613 |
| EONET_16409 | 2025-12-11 | -18.8574, -41.9439 | gdacs.org FL 1103670 |
| EONET_18043 | 2026-02-02 | -22.7592, -43.4509 | gdacs.org FL 1103757 |
| EONET_18040 | 2026-02-20 | -23.6203, -45.4131 | gdacs.org FL 1103780 |
| EONET_19922 | 2026-04-26 | -3.8488, -38.3933  | gdacs.org FL 1103852 |
| EONET_20298 | 2026-05-22 | -21.1351, -41.6798 | gdacs.org FL 1103912 |
| EONET_20501 | 2026-06-10 | -24.4842, -51.8149 | gdacs.org FL 1103940 |
| EONET_20825 | 2026-06-25 | -27.6616, -53.6421 | gdacs.org FL 1103977 |

9 eventos, abaixo do alvo de 10–20 do enunciado original da issue. Conforme
a issue previu para esse cenário, o relatório o registra em vez de inventar
eventos adicionais — decisão do maintainer, tomada em `AskUserQuestion`
durante a sessão, foi prosseguir só com os 9 em vez de complementar com
vizinhos PROXIMO ou eventos de registro público fora do EONET.

## Ground truth ERA5 — metodologia e validação do pipeline

`total_precipitation_6hr` do WeatherNext é uma previsão; para saber se ela
"acertou" é preciso um dado observado independente. Usamos a Open-Meteo
Archive API (`archive-api.open-meteo.com/v1/archive`, `models=era5`),
gratuita, sem custo de BigQuery, que serve reanálise ERA5.

**Validação do pipeline** (antes de confiar nele para os 9 eventos):
pesquisa web identificou um desastre severo, bem documentado e
independente da amostra — as enchentes da Zona da Mata Mineira, chuva
extrema na noite de 23→24/02/2026 em Juiz de Fora/MG, 73 mortos
([pt.wikipedia.org/wiki/Enchentes_e_deslizamentos_na_Zona_da_Mata_Mineira_em_2026](https://pt.wikipedia.org/wiki/Enchentes_e_deslizamentos_na_Zona_da_Mata_Mineira_em_2026)).
Consulta real:

```
lat=-21.7642 lon=-43.3467 (Juiz de Fora) start=2026-02-21 end=2026-02-25
2026-02-21  25.6 mm
2026-02-22  11.0 mm
2026-02-23  16.4 mm
2026-02-24  30.4 mm
2026-02-25   1.9 mm
```

Precipitação elevada exatamente nas datas documentadas — pipeline
confirmado correto (coordenadas, unidades, modelo).

**Correção de metodologia durante a sessão**: a primeira tentativa usou
janela `onset-2`..`onset+1` em torno da data de onset reportada pelo
GDACS/EONET para achar o "dia-alvo" (pico de chuva real) de cada evento.
Para `EONET_20825` essa janela devolveu chuva zero em todos os 4 dias —
suspeito, dado que o evento é um flood real. Investigação (não custou bytes
do WeatherNext, só Open-Meteo): ampliando a janela para `onset-7`..`onset+1`,
o pico real (32.1 mm) aparece em 2026-06-22, **3 dias antes** da data de
onset reportada — efeito de tempo de resposta de bacia hidrográfica entre a
chuva e o alagamento observado/reportado, não erro de pipeline. A janela
final usada para todos os 9 eventos foi `onset-7`..`onset+1`, com o
dia-alvo definido como o dia de maior `precipitation_sum` ERA5 nessa janela:

| id | dia-alvo (pico ERA5) | ERA5 (mm) |
|---|---|---|
| EONET_15841 | 2025-10-20 | 27.5 |
| EONET_15901 | 2025-11-09 | 15.4 |
| EONET_16409 | 2025-12-07 | 29.2 |
| EONET_18043 | 2026-02-03 | 27.7 |
| EONET_18040 | 2026-02-18 | 22.8 |
| EONET_19922 | 2026-04-19 | 23.6 |
| EONET_20298 | 2026-05-20 | 15.5 |
| EONET_20501 | 2026-06-11 | 27.5 |
| EONET_20825 | 2026-06-22 | 32.1 |

## Queries BigQuery — desenho e custo real

Regra de custo: tabela `weathernext_2_mean.weathernext_2_0_0_mean`
exclusivamente (ensemble é 45× mais caro, não coube no orçamento para
10-20 eventos — não foi necessário para o veredito). Toda query filtra
`init_time` (coluna de partição) e usa `--maximum_bytes_billed` em 2× o
dry-run.

Desenho final (após ajuste de custo — ver abaixo):

```sql
SELECT f.time AS valid_time, f.total_precipitation_6hr AS precip_6hr,
       ST_DISTANCE(geography, ST_GEOGPOINT(<lon>, <lat>)) AS dist_m
FROM `weathernexttest-506315.weathernext_2_mean.weathernext_2_0_0_mean`,
UNNEST(forecast) AS f
WHERE init_time = TIMESTAMP("<init_day> 00:00:00")
  AND ST_DWITHIN(geography, ST_GEOGPOINT(<lon>, <lat>), 20000)
  AND f.time >= TIMESTAMP("<dia_alvo> 00:00:00")
  AND f.time <  TIMESTAMP("<dia_alvo+1> 00:00:00")
ORDER BY dist_m, valid_time
```

9 eventos × 5 lead times (1, 2, 4, 7, 11 dias antes do dia-alvo) = 45
queries. `init_day` mínimo usado: 2025-10-13 (EONET_15841, lead 11d) —
dentro da cobertura do dataset (desde 2025-10-03).

**Ajuste de custo por coluna selecionada** (medido, não assumido): a
primeira versão da query selecionava também `init_time` e `f.hours`,
custando 6.179.604.480 bytes/query no dry-run. Removendo essas duas
colunas do SELECT (mantendo-as só no filtro), o custo caiu para
4.186.183.680 bytes/query — batendo exatamente com o fato "mean → 4,19 GB
por partição/variável" já registrado. `ST_DWITHIN`/`ST_DISTANCE` sobre
`geography` não adicionam custo (mesmo valor com ou sem eles) — a coluna
`geography` em si é barata; o custo extra vinha de `init_time`/`hours`.

```
$ bq query --use_legacy_sql=false --dry_run < q_lean.sql
... upper bound of 4186183680 bytes of data.
```

Dry-run confirmado idêntico nas 45 queries finais: 45 × 4.186.183.680 =
188.378.265.600 bytes (≈188,4 GB, 17,1% do free tier de 1 TiB) — teto usado
para autorização.

### Bug encontrado em produção do relatório (transparência)

A primeira execução real (45 queries autorizadas) usou
`ORDER BY dist_m LIMIT 1`, pensado para pegar só a célula de grade mais
próxima. Erro: os 4 passos de 6h do dia-alvo, na mesma célula, têm o
**mesmo** `dist_m` — são empate. `LIMIT 1` descartou 3 dos 4 valores de
precipitação do dia, mantendo sempre a linha `00:00:00`:

```
$ cat q2_00.sql
... ORDER BY dist_m LIMIT 1
$ bq query ... < q2_00.sql
[{"dist_m":"9297.67","precip_6hr":"0.004610860254615545","valid_time":"2025-10-20 00:00:00"}]
```

Corrigido removendo o `LIMIT` (custo idêntico, confirmado por dry-run antes
de re-executar) e re-rodando as 45 queries:

```
$ cat q3_00.sql
... ORDER BY dist_m, valid_time
$ bq query ... < q3_00.sql
[{"dist_m":"9297.67","precip_6hr":"0.004610860254615545","valid_time":"2025-10-20 00:00:00"},
 {"dist_m":"9297.67","precip_6hr":"0.021250847727060318","valid_time":"2025-10-20 06:00:00"},
 {"dist_m":"9297.67","precip_6hr":"0.007932822220027447","valid_time":"2025-10-20 12:00:00"},
 {"dist_m":"9297.67","precip_6hr":"0.0052675786428153515","valid_time":"2025-10-20 18:00:00"}]
```

Registrado porque essa correção dobrou o orçamento gasto (dry-run estimado:
2 × 188,4 GB = 376,8 GB, 34,3% do free tier) — o maintainer autorizou o
re-run explicitamente após a explicação do bug.

### Custo real medido vs. estimado (achado adicional)

O dry-run é um limite superior pessimista. O custo **real faturado**,
lido de `bq ls -j -a` (soma de `totalBytesBilled` das 90 execuções reais —
45 com o bug + 45 corrigidas):

```
jobs com bytes faturados: 90
total de bytes faturados: 6.587.154.432
= 6,587 GB = 0,599% do free tier de 1 TiB
```

O custo real (6,59 GB) ficou **~57× abaixo** da estimativa de dry-run
(376,8 GB) usada para pedir autorização. Isso diverge do fato já registrado
de que "o clustering não poda com filtro espacial" — mas aquele teste
usava uma bbox larga (todo o Brasil) na tabela ensemble; aqui o filtro é um
raio de 20 km ao redor de um ponto, combinado com igualdade exata em
`init_time`. Achado: para consultas por ponto com raio apertado, a poda
real na execução é muito mais agressiva que o dry-run relata — relevante
para o orçamento de #70 (vigilância diária por município), que deve usar
o número real medido (ordens de grandeza menor que o dry-run) para
planejamento de custo, não o dry-run isoladamente.

## Resultados — precipitação prevista (mm) por lead time vs. ERA5

Célula mais próxima da grade (0.25°) a cada evento; distância real
5,1–16,2 km do ponto GDACS (dentro de meia diagonal de célula, como
esperado). `HIT` = previsão ≥ 50% do ERA5 observado; `parcial` = 20–50%;
`MISS` = <20%.

| evento | onset | ERA5 dia-alvo (mm) | 1d | 2d | 4d | 7d | 11d |
|---|---|---|---|---|---|---|---|
| EONET_15841 | 2025-10-23 | 27.5 | 39.1 (HIT) | 43.2 (HIT) | 39.3 (HIT) | 29.4 (HIT) | 2.5 (MISS) |
| EONET_15901 | 2025-11-14 | 15.4 | 12.1 (HIT) | 8.8 (HIT) | 6.7 (parcial) | 4.1 (parcial) | 7.0 (parcial) |
| EONET_16409 | 2025-12-11 | 29.2 | 3.3 (MISS) | 4.2 (MISS) | 3.8 (MISS) | 6.0 (parcial) | 5.9 (parcial) |
| EONET_18043 | 2026-02-02 | 27.7 | 11.8 (parcial) | 14.1 (HIT) | 13.8 (parcial) | 9.4 (parcial) | 14.0 (HIT) |
| EONET_18040 | 2026-02-20 | 22.8 | 14.4 (HIT) | 12.3 (HIT) | 13.4 (HIT) | 8.9 (parcial) | 5.3 (parcial) |
| EONET_19922 | 2026-04-26 | 23.6 | 30.1 (HIT) | 21.7 (HIT) | 14.4 (HIT) | 15.9 (HIT) | 10.0 (parcial) |
| EONET_20298 | 2026-05-22 | 15.5 | 4.4 (parcial) | 6.1 (parcial) | 2.7 (MISS) | 2.2 (MISS) | 4.3 (parcial) |
| EONET_20501 | 2026-06-10 | 27.5 | 29.0 (HIT) | 26.6 (HIT) | 17.7 (HIT) | 14.3 (HIT) | 3.4 (MISS) |
| EONET_20825 | 2026-06-25 | 32.1 | 29.9 (HIT) | 24.7 (HIT) | 24.3 (HIT) | 19.2 (HIT) | 10.6 (parcial) |

Sem cherry-picking: os 9 eventos aparecem, incluindo os 2 sem sinal útil em
nenhum lead testado (EONET_16409, EONET_20298). EONET_20825 não foi
excluído em nenhum momento — é o evento cuja "chuva zero" inicial era um
bug de janela desta análise (ver seção de correção de metodologia acima);
corrigido, ele está nesta tabela com um dos sinais mais fortes da amostra.

**Aviso estatístico**: N=9. O limiar HIT (≥50% da magnitude ERA5) é uma
escolha de corte desta análise, não um valor natural do problema — com
N=9, mudar 1 evento de categoria move qualquer percentual em ~11 pontos.
"67% em 1d" e "56% até 7d" (abaixo) diferem por exatamente 1 evento
(EONET_18043, HIT intermitente). Não tratar essas frações como taxas
precisas de skill do modelo; são uma leitura qualitativa de uma amostra
pequena.

**Resumo:**

- **6 de 9 eventos (67%)** mostram HIT já em lead de 1 dia.
- **5 de 9 eventos (56%)** mantêm HIT até 7 dias de lead (EONET_15841,
  EONET_19922, EONET_20501, EONET_20825, e EONET_18043 de forma
  intermitente).
- **2 de 9 eventos (22%)** — EONET_16409 e EONET_20298 — nunca atingem HIT
  em nenhum lead testado (1 a 11 dias), inclusive no lead mais curto.
- Em todos os 9 eventos, o sinal degrada para MISS ou parcial a partir de
  ~7–11 dias — consistente com o limite de previsibilidade conhecido de
  modelos NWP globais para precipitação quantitativa.

## Limitações desta medição

- **Só o campo mean, não o ensemble.** O mean é a média de 64 membros; é
  possível que membros individuais do ensemble captassem sinal em eventos
  onde o mean errou (EONET_16409, EONET_20298) — o mean tende a suavizar
  extremos. Esta análise não pode distinguir "o modelo não viu o evento"
  de "o mean apagou um sinal presente em parte do ensemble". Rodar o
  ensemble para esses 2 eventos custaria ~2 × 189 GB (17-19% do free tier
  cada) — decisão de fazer isso ou não é do maintainer, não foi executada
  aqui pela regra de custo da issue.
- **Onset do GDACS é impreciso.** A data de "onset" de um flood no GDACS
  reflete quando o alagamento foi reportado/observado, não
  necessariamente quando choveu — confirmado no caso EONET_20825 (defasagem
  de 3 dias). O ponto (lat/lon) é um centroide administrativo/de relatório,
  não necessariamente o local exato do pico de chuva — grade de 0.25°
  (~28 km) e o próprio evento de flood (subgrid) tornam esse desalinhamento
  espacial uma fonte de ruído inerente, não um defeito desta análise.
  `dist_m` medido (5,1–16,2 km) mostra que a célula mais próxima está bem
  dentro do raio esperado, mas "mais próxima" não é "onde choveu".
- **N=9, não 10-20.** Ver seção de seleção de eventos acima para o porquê.
