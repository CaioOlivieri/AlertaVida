status: implemented
sources: `src/alertavida/database.py`, `src/alertavida/sources/cemaden.py`, `tests/test_database.py`, `tests/sources/test_cemaden.py`, issue #130
updated: 2026-11-22

# Retire migrations for schemas that no longer exist

Found by the 2026-11-13 audit ([[audit-2026-11-13]]). `_migrar_banco`
carried an `ALTER TABLE` / `DROP INDEX` step for every schema change since
May — and `tests/fixtures/schemas_legados.py` (200 lines) existed only to
exercise them. #127 introduced `PRAGMA user_version`, which made a clean
cut possible.

## Which databases exist, and what they need

Dated from git history, not assumed:

| Change | Merged | Needed by |
|---|---|---|
| A.2 COBRADE columns, #8 `assinatura` drop, #11 index drops and `descricao` | May–July 2026 | nothing that exists |
| #22 `eventos` FK | 2026-07-28 | nothing that exists |
| #59 `agregado_incidente_id`, #60 R-Tree (+ backfill) | **2026-08-12** | nothing — the production database was created on **2026-08-13** (first `detectado_em`), with both already in `CREATE TABLE`; 0 alerts missing from the R-Tree |
| #89 `idx_fonte` / `idx_escopo_geografico` drops | 2026-09-06 | **the pre-cutover snapshot of 2026-09-05** — kept |
| #127 CEMADEN timezone shift (`user_version` 0 → 1) | 2026-11-14 | every database before it — kept |

## What changed

- `_migrar_banco` keeps only the #89 index drops and `_corrigir_fuso_cemaden`.
  Removed: the A.2/#11 column additions, the `assinatura` drop, the
  speculative-index drops, the `agregado_incidente_id` `ALTER TABLE` and the
  R-Tree backfill.
- `_verificar_compatibilidade_schema` became one guard: a database with
  `user_version = 0` must already have `alertas` columns `id`, `fonte`,
  `cobrade_codigo`, `fonte_classificacao`, `descricao`, and `eventos` with the
  FK and `agregado_incidente_id`; otherwise `SchemaIncompativelError` lists
  everything missing. `user_version >= 1` skips inspection — it only exists
  from #127 on. Future schema changes should be numbered steps under
  `user_version`, not column inspection.
- `tests/fixtures/schemas_legados.py` deleted; its tests replaced by inline
  minimal schemas that prove the refusals (pre-A.1, pre-A.2 — refused
  *before* any `ALTER`, `eventos` without FK, pre-#59), plus a test for the
  #89 drop that remains.
- **`CemadenSource._normalize_payload`** accepts only the real envelope,
  `{"alertas": [...], "atualizado": ...}` — 966 of 966 archived captures
  have exactly those two keys. The speculative variants (list at the top,
  `data`/`items`/`results`) now raise `FalhaDeColeta`; the daily contract test
  catches a real format change the same day.

## Deliberately not done

- **`EventBus.handler_count`** stays, although the audit listed it as
  test-only. It is the only non-private way to assert that
  `criar_bus_producao()` subscribed every event type — removing it would
  push those tests onto `bus._handlers`. A test-only accessor that verifies
  production wiring is not dead code.
- The 11 `TipoEvento.from_string` aliases — #91's territory.

## Verified against real databases (copies, never the live file)

| Database | Before | After `criar_banco()` |
|---|---|---|
| Production backup 2026-11-06 (`user_version` 0, before #127) | 1,357 alerts, integrity ok | `user_version` 1, same row counts and indexes, second run changes nothing, snapshots load (638 CEMADEN / 719 EONET) |
| Production backup 2026-11-22 (`user_version` 1) | 1,649 alerts | identical — counts and indexes unchanged |

| **Pre-cutover snapshot 2026-09-05** (`user_version` 0, the oldest database that exists) | had `idx_fonte` + `idx_escopo_geografico` → **dropped by the kept #89 step**; already had `agregado_incidente_id` → the removed #59 `ALTER` was indeed unneeded; guard passed; `user_version` 0 → 1; 574 alerts / 1,312 events / 537 incidents unchanged; second run changes nothing; #127 shift applied (oldest CEMADEN onset 05:37 → 08:37 UTC); snapshots load (7 CEMADEN / 567 EONET) |

The snapshot result is the strongest evidence for the cut: the one step it
still needed is the one that was kept, and the one it did not need is the one
that was removed.
