status: integrated
sources: `src/alertavida/domain/alerta.py`, `municipio.py`, `coordenadas.py`, `enums.py`
updated: 2026-06-11

# domain-models

Pydantic v2 frozen models and enums. All domain code in Portuguese:

- `Alerta` — frozen model with `fonte: Annotated[FonteDado, Strict()]`, `cobrade_codigo`, `fonte_classificacao`, COBRADE invariants via `@model_validator`. Entry: `Alerta.from_dict(data, *, fonte: FonteDado)`.
- `Municipio` — IBGE code, name, state, coordinates.
- `Coordenadas` — latitude/longitude value object.
- `FonteDado(StrEnum)` — closed set: CEMADEN, EONET, INMET, INPE. `from_string` raises on unknown (strict).
- `TipoEvento(StrEnum)` — COBRADE subgroups: HIDROLOGICO, GEOLOGICO, METEOROLOGICO, CLIMATOLOGICO, BIOLOGICO, INDETERMINADO. `from_string` returns INDETERMINADO for unknowns.
- `NivelRisco(StrEnum)` — BAIXO, MODERADO, ALTO, MUITO_ALTO, INDETERMINADO. `from_string` raises.
- `EscopoGeografico(StrEnum)` — BRASIL, PROXIMO, INTERNACIONAL.
- `FonteClassificacao(StrEnum)` — DIRETA, MAPEADA_POR_NOME, INFERIDA_POR_CONTEXTO, INDETERMINADA.
