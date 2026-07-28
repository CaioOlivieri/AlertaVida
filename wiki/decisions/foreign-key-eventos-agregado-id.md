status: implemented
sources: `src/alertavida/database.py`
updated: 2026-07-28

# Foreign Key: `eventos.agregado_id` → `alertas.id`

Issue #22 item B. The outbox `eventos` table always referenced `alertas.id` by
convention only — no `FOREIGN KEY` clause, and `PRAGMA foreign_keys` was never
enabled. This decision declares the FK in `CREATE TABLE eventos` and turns
`foreign_keys=ON` in `conectar()`, without the SQLite 12-step table rebuild.

## The FK protects nothing today — stated plainly

There is no way to create a dangling `agregado_id` in the current code:

- No `DELETE` and no `DROP TABLE` exists anywhere in `src/` or `scripts/`
  (verified by grep). Nothing removes an `alertas` row an event could orphan.
- Every `agregado_id` written by `aplicar_resultado_deteccao` derives from a row
  written or updated **in the same transaction**: `cursor.lastrowid` on the
  `CRIADO` branch; `UPDATE … RETURNING id` on `ATUALIZADO`/`REATIVADO` and on
  `RESOLVIDO`. The outbox INSERT is guarded by `if agregado_id is not None`, and
  the column is `NOT NULL`. No code path can fabricate a hanging id.

So this is a **cheap-now, expensive-later** guardrail, not a bug fix.

## Why do it anyway, now

Local databases are still disposable, so paying the cost now is nearly free.
Camada 6 adds the API and very likely retention/purge of the outbox (`eventos`
grows forever otherwise). That is exactly when a `DELETE` on `alertas` — or a
purge that races an insert — makes an orphan possible, and by then there is real
data to migrate. Declaring the FK while the schema break is free avoids a
12-step migration on a populated production database later.

## Why not the 12-step rebuild (recreate `eventos` in a migration)

SQLite cannot add a `FOREIGN KEY` via `ALTER TABLE`; the only in-place path is
the 12-step table rebuild. That was rejected:

- It follows the existing precedent for structural breaks without migration:
  pre-A.1 databases are barred by `SchemaIncompativelError` and recreated
  (see [[decisions/schema-incompatibility-pre-a1]]). `_migrar_banco()` stays
  additive/cleanup-only — putting a table rebuild there would break that policy.
- A rebuild-in-migration would produce two databases of the *same version* with
  different schemas — precisely the schema drift `_verificar_compatibilidade_schema`
  exists to catch.

Instead, `_verificar_compatibilidade_schema()` gained a second check: an
`eventos` table that exists **without** the FK raises `SchemaIncompativelError`
(distinct message from the pre-A.1 one), telling the operator to delete the file
and re-run `criar_banco()` (export to JSON first if there is data).

## Consequence: the A.1→A.2 migration path is now unreachable

Rejecting pre-#22 databases has a side effect worth stating explicitly. The
`eventos` table dates from Camada 3 (02/05/2026) and never carried the FK before
this issue, so **every** real database created before 2026-07-28 now fails the
new check. A database that passes both checks either has no `eventos` table at
all, or was created after #22 — in which case its `alertas` already has the
current schema and there is nothing to migrate additively. Verified empirically
against a reconstructed A.1-era database (`alertas` with `id`+`fonte`, `eventos`
without the FK): `criar_banco()` raises before reaching `_migrar_banco()`.

`_migrar_banco()` therefore still runs on every `criar_banco()` and stays
idempotent, but its legacy A.1→A.2 branches (add the COBRADE columns, drop
`assinatura`, drop the old indexes, add `descricao`) are vestigial for real
databases. To keep them under regression test rather than untested-but-running,
`tests/fixtures/schemas_legados.py::aplicar_schema_pos_a1_pre_a2` was
deliberately turned into a chimera — A.1-era `alertas` plus a post-#22 `eventos`
carrying the FK — a combination that never existed in production. The real
historical shape lives in `aplicar_schema_eventos_sem_fk`, which proves the
rejection. Retiring the vestigial branches (and the chimera with them) is a
candidate follow-up, not part of this issue.

## `ON DELETE NO ACTION`, not `CASCADE`

The FK uses the default `ON DELETE NO ACTION`. The outbox is the product's audit
trail — purging an `alertas` row must never silently erase its event history.
A future purge policy has to deal with `eventos` explicitly.

## Enforcement is per connection

`PRAGMA foreign_keys` is a per-connection setting. `conectar()` turns it on
(before the transaction block — it is a no-op inside a transaction), so every
production call site is covered. Raw `sqlite3.connect(...)` connections — used by
some test fixtures that insert events with no parent alert — are **not** enforced,
by design; those tests stay green without inventing parent rows.

## The limit of the guarantee — do not oversell it

The FK catches a **dangling** id, not a **wrong** id. The `cursor.lastrowid` read
on the `CRIADO` branch is the fragile point: a future refactor that reorders
statements could make `lastrowid` point at a *different, existing* `alertas` row,
and the FK would still be satisfied while the event points at the wrong alert.
The FK must not create false confidence that `agregado_id` is *correct* — only
that it is *present in `alertas`*.

## Re-evaluation

Revisit at Camada 6, when the API and outbox retention/purge land — that is when
orphaning becomes reachable and the guardrail starts doing real work.
