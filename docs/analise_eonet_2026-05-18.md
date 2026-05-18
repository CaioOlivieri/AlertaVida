# Análise empírica NASA EONET v3 — 2026-05-18

## Captura 20:10:50 UTC

**URL Requisição A:** `https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=500`  
**URL Requisição B:** `https://eonet.gsfc.nasa.gov/api/v3/events?status=all&days=30&limit=500`  
**Timestamp UTC:** 2026-05-18T20:10:50

### Volume

| Requisição | Total eventos |
|---|---|
| open | 500 |
| all_30d | 328 |

### Distribuição por categoria

| Categoria | open | all_30d | Fora do esperado |
|---|---|---|---|
| drought | 0 | 0 | — |
| dustHaze | 0 | 0 | — |
| earthquakes | 0 | 0 | — |
| floods | 0 | 36 | — |
| landslides | 0 | 0 | — |
| manmade | 0 | 0 | — |
| seaLakeIce | 0 | 16 | — |
| severeStorms | 0 | 2 | — |
| snow | 0 | 0 | — |
| tempExtremes | 0 | 0 | — |
| volcanoes | 3 | 2 | — |
| waterColor | 0 | 0 | — |
| wildfires | 497 | 272 | — |

### Status closed/open

| Status | open_req | all_30d_req |
|---|---|---|
| open (closed=null) | 500 | 97 |
| closed | 0 | 231 |

### Geometria temporal

| Métrica | open_req | all_30d_req |
|---|---|---|
| events com 1 fix | 500 | 310 |
| events com N>1 fixes | 0 | 18 |
| total fixes | 500 | 821 |
| média fixes/event | 1.00 | 2.50 |
| mediana fixes/event | 1.0 | 1.0 |
| máximo fixes/event | 1 | 52 |

### Geometria espacial

| geometry.type | open_req | all_30d_req |
|---|---|---|
| Point | 500 | 821 |

### Magnitudes

| Métrica | open_req | all_30d_req |
|---|---|---|
| events com magnitude != null | 497 | 290 |
| unit=NM^2 | 0 | 449 |
| unit=acres | 497 | 90 |
| unit=hectare | 0 | 182 |
| unit=kts | 0 | 60 |

### Escopo Brasil

> bbox: lat [-34.0, 5.5] lon [-74.0, -34.0]

| Req | Eventos Brasil | Total |
|---|---|---|
| open | 0 | 500 |
| all_30d | 3 | 328 |

### Observações

Nenhuma categoria fora do conjunto esperado.
