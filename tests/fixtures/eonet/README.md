# tests/fixtures/eonet/

## Propósito

**Fixtures sintéticas mínimas** da fonte NASA EONET v3, usadas pelos testes
de `NasaEonetSource` (Camada 4 Parte C.1+, ver `__init__.py` neste diretório
e `tests/sources/test_nasa_eonet.py`).

## O que NÃO está aqui

Amostras reais capturadas da API EONET **não** ficam versionadas no git.
São geradas pelo script `scripts/inspect_eonet_payload.py` e salvas em
`data/samples/eonet/` (gitignored).

Motivo: padrão estabelecido pelo projeto para fixtures de inspeção exploratória.
A fonte CEMADEN segue o mesmo padrão (`data/samples/cemaden_raw_*.json`).
Amostras EONET pretty-printed pesam ~500 KB cada — versioná-las infla o histórico
do repo sem benefício de auditoria (git delta não compacta JSON pretty-printed).

## Onde encontrar o quê

| Tipo | Localização | Versionado? |
|---|---|---|
| Script de captura | `scripts/inspect_eonet_payload.py` | sim |
| Amostras brutas | `data/samples/eonet/eonet_open_*.json`, `eonet_all_30d_*.json` | não |
| Relatório consolidado | `wiki/raw/analise-eonet-2026-05-18.md` | sim |
| Fixtures sintéticas para testes | `__init__.py` (este diretório) | sim |

## Categorias EONET v3 (13 categorias, IDs string)

Referência rápida — IDs usados em `categories[].id` no payload:

| ID | Descrição |
|---|---|
| `drought` | Seca |
| `dustHaze` | Poeira / Neblina |
| `earthquakes` | Terremotos |
| `floods` | Inundações |
| `landslides` | Deslizamentos / Movimentos de massa |
| `manmade` | Eventos de origem humana |
| `seaLakeIce` | Gelo marinho / lacustre |
| `severeStorms` | Tempestades severas |
| `snow` | Neve |
| `tempExtremes` | Extremos de temperatura |
| `volcanoes` | Vulcões |
| `waterColor` | Coloração da água (algas, sedimentos) |
| `wildfires` | Incêndios florestais |

Atenção: EONET v2.1 usava inteiros como IDs de categoria — fixtures dessa versão são incompatíveis.

## Disclaimer NASA (literal)

> All EONET metadata and services are intended to be used for visualization and general
> information purposes only and should not be construed as 'official' with regards to
> spatial or temporal extent.

Fonte: https://eonet.gsfc.nasa.gov/what-is-eonet
