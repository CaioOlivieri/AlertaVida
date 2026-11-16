# Análise: o que a coordenada de um alerta CEMADEN representa — 2026-11-16

Relatório bruto da issue #136. Discriminador da Round 2 da Camada 5: vários
alertas no mesmo município — coordenadas idênticas ⇒ ponto fixo por
município; coordenadas variando ⇒ ponto de risco.

## Fontes

- Banco: backup de produção `alertavida-20261116T030847Z.db`, aberto em
  `mode=ro` (cobre 2026-08-13 → 2026-11-16).
- Capturas cruas do surge watch (#70): `data/weathernext_cemaden_captures_archive/`,
  966 arquivos de `cemaden_raw_20261018T150513Z.json` a
  `cemaden_raw_20261116T205516Z.json`. As de 14–17/10 já tinham sido podadas
  pela retenção de 30 dias antes da cópia.

## Comando

```
uv run python -m scripts.analise_coordenada_cemaden \
    --banco /var/lib/alertavida/backups/alertavida-20261116T030847Z.db \
    --capturas data/weathernext_cemaden_captures_archive
```

## Saída

## Banco — alertas diferentes no mesmo município

- alertas CEMADEN com município: 758
- municípios distintos: 379
- municípios com 2+ alertas: 187 (566 alertas)
- desses, todas as coordenadas idênticas: 187
- desses, coordenadas variando: 0
- maior espalhamento dentro de um município: 0.000 km

| codibge | município | UF | alertas | pontos distintos | espalhamento km |
|---|---|---|---|---|---|
| 3550308 | SÃO PAULO | SP | 11 | 1 | 0.000 |
| 3303906 | PETRÓPOLIS | RJ | 9 | 1 | 0.000 |
| 3136702 | JUIZ DE FORA | MG | 8 | 1 | 0.000 |
| 1302603 | MANAUS | AM | 7 | 1 | 0.000 |
| 3509502 | CAMPINAS | SP | 7 | 1 | 0.000 |
| 3504107 | ATIBAIA | SP | 6 | 1 | 0.000 |
| 3549904 | SÃO JOSÉ DOS CAMPOS | SP | 6 | 1 | 0.000 |
| 3550704 | SÃO SEBASTIÃO | SP | 6 | 1 | 0.000 |
| 3552205 | SOROCABA | SP | 6 | 1 | 0.000 |
| 4202909 | BRUSQUE | SC | 6 | 1 | 0.000 |

## Capturas — a mesma alerta em payloads sucessivos

- observações (item × payload): 14497
- alertas distintos: 363
- alertas cuja coordenada mudou: 0


## Medição complementar: distância do ponto fixo até a sede municipal

Rodada à parte (consulta ad hoc no mesmo backup), contra coordenadas
públicas aproximadas da sede de cada município:

| Município | Ponto CEMADEN | Alertas | Distância da sede |
|---|---|---|---|
| São Paulo | (-23.65008, -46.64811) | 11 | 11.2 km |
| Petrópolis | (-22.39855, -43.15731) | 9 | 12.0 km |
| Juiz de Fora | (-21.74549, -43.46474) | 8 | 12.0 km |
| Campinas | (-22.88376, -47.04378) | 7 | 3.0 km |
| Manaus | (-2.62592, -60.25963) | 7 | 60.9 km |
| Rio de Janeiro | (-22.92319, -43.45026) | 5 | 24.7 km |

O deslocamento acompanha a forma do território: Manaus se estende muito ao
norte da sede, o Rio a oeste, São Paulo ao sul. É o padrão de um centroide de
polígono. **Não verificado contra a malha municipal do IBGE** — isso fica
para quando a #62 trouxer a malha.

## Leitura

- 187 de 187 municípios com mais de um alerta: um único ponto, espalhamento
  0,000 km, entre tipos diferentes (hidrológico e geológico) e ao longo de
  três meses.
- 0 de 363 alertas mudaram de coordenada em 14.497 observações sucessivas.
- A coordenada do CEMADEN é um **ponto fixo por município**, não a sede e não
  um ponto de risco; muito provavelmente o centroide do polígono.
