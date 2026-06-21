status: integrated
sources: `src/alertavida/domain/cobrade.py`
updated: 2026-06-21

# domain-cobrade

COBRADE classification mapper (Partes A.2 + C.2):

- `EVENTO_CEMADEN_PARA_COBRADE` — mapping table (2 entries based on empirical inspection of 240 alerts): `Risco Hidrológico → 1.2.0.0.0`, `Movimentos de Massa → 1.1.3.0.0`.
- `EVENTO_EONET_PARA_COBRADE` — mapping table (5 categories) for NASA EONET v3 categories to COBRADE codes. Granularity rule: map to the most specific level the EONET terminology determines without inference. `floods`/`severeStorms` stay at group level (category does not distinguish subgroups); `wildfires` maps to subgrupo Seca (`1.4.1.0.0`); `volcanoes` to subgrupo Emanação Vulcânica (`1.1.2.0.0`); `landslides` to subgrupo Movimento de Massa (`1.1.3.0.0`).
- `mapear_eonet(categoria)` — mirrors `mapear_cemaden` for EONET category strings.
- Subgroup-level only (Camada 4 conscious limit). Subtype distinction (flood vs flash flood vs waterlogging) belongs to Camada 5 with topography/urban density/INMET data.
- `fonte_classificacao` registers provenance: DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA.
