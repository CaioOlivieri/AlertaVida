status: integrated
sources: `src/alertavida/domain/cobrade.py`
updated: 2026-06-11

# domain-cobrade

COBRADE classification mapper (Parte A.2):

- `EVENTO_CEMADEN_PARA_COBRADE` — mapping table (2 entries based on empirical inspection of 240 alerts): `Risco Hidrológico → 1.2.0.0.0`, `Movimentos de Massa → 1.1.3.0.0`.
- Subgroup-level only (Camada 4 conscious limit). Subtype distinction (flood vs flash flood vs waterlogging) belongs to Camada 5 with topography/urban density/INMET data.
- `fonte_classificacao` registers provenance: DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA.
