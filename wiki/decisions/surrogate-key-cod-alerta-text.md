status: implemented
sources: [[decisions/decision-record]]
updated: 2026-06-11

# Surrogate Key + cod_alerta as TEXT

`id INTEGER PRIMARY KEY AUTOINCREMENT` replaces composite PK. `UNIQUE (fonte, cod_alerta)` enforces business uniqueness.

`cod_alerta` changed from INTEGER to TEXT for inclusivity: CEMADEN uses numeric codes, EONET uses strings (`EONET_5421`).

FKs in other tables become simple INTEGERs. Future URLs stay opaque (`/alertas/12345`). Renaming sources does not break references.
