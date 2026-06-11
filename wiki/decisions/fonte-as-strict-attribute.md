status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# fonte as Strict Attribute on Alerta

`fonte: Annotated[FonteDado, Strict()]` — surgical strict via `Annotated`, NOT global `strict=True` (which would break datetime/enum coercion).

`Alerta.from_dict(data, *, fonte: FonteDado)` requires `fonte` as keyword-only enum. Source provenance is immutable domain metadata; mismatching against the producing source is a domain invariant violation.

`FonteDado(StrEnum)` is a closed set (CEMADEN, EONET, INMET, INPE) — no INDETERMINADA, source is always known at collection time. `from_string` raises on unknown values.
