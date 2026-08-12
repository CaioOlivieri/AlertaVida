status: implemented
sources: `src/alertavida/database.py`, issue #59
updated: 2026-08-12

# Incident Lifecycle Events: `agregado_incidente_id`, Not Payload-Only

`eventos.agregado_id` has carried a `FOREIGN KEY → alertas(id)` since #22
([[decisions/foreign-key-eventos-agregado-id]]), so incident lifecycle events
(`IncidenteCriado`/`Atualizado`/`Resolvido`/`Reativado`/`Fundido`) cannot reuse
that column to reference `incidentes` rows. Three options were on the table:
(a) carry the incident id only inside the JSON `payload`, keeping
`agregado_id` pointed at a triggering alert; (b) a nullable second column
`agregado_incidente_id` with its own FK; (c) a separate outbox table
mirroring `eventos`.

**Decided: (b).** A new nullable `agregado_incidente_id INTEGER NULL`
column on `eventos`, with `FOREIGN KEY (agregado_incidente_id) REFERENCES
incidentes(id)` and its own child-key index
(`idx_eventos_agregado_incidente_id`), same style as #22's own FK. `eventos`
now carries two independent FKs — `agregado_id → alertas(id)` (unchanged) and
`agregado_incidente_id → incidentes(id)` (new) — never both required on the
same row: `agregado_id` stays `NOT NULL` on every row, `agregado_incidente_id`
is populated only on the five incident event types.

## Why not (a) or (c)

(a) reuses the existing FK untouched and needs no schema change, but every
future "list events for incident X" query would have to scan and parse the
JSON `payload` — no index, no DB-enforced referential integrity on the
incident side at all. (c) — a second outbox table — separates concerns
cleanly, but duplicates the `eventos` structure and, since `events.py`/
`OutboxDispatcher` is out of scope for #59, would sit with no dispatch path
until #61 wires it. (b) keeps both FKs independently indexed and enforced,
at the cost of one extra nullable column on a high-traffic table.

## Why `agregado_id` stays `NOT NULL` and populated for incident events too

The maintainer's condition before approving (b): enumerate every incident
event type and name its triggering alert, and stop if any type has none —
because a type without one would break `agregado_id NOT NULL`. All five do
have one, because #59's five state-change functions are designed to always
require it as an explicit parameter; the correlation/orchestration logic that
decides *when* to call them (owned by #60/#61) is what actually determines
the triggering alert, but the persistence layer never accepts a lifecycle
transition without it:

| Event | Function | Triggering alert (`agregado_id`) |
|---|---|---|
| `IncidenteCriado` | `criar_incidente(alerta_id, …)` | the alert whose correlation found no compatible open incident and opened a new one (Round 1, Q6, option 2) |
| `IncidenteAtualizado` | `adicionar_membro_incidente(incidente_id, alerta_id, …)` | the alert that joined a compatible open incident (Round 1, Q6, option 1) |
| `IncidenteResolvido` | `resolver_incidente(incidente_id, alerta_id_disparador, …)` | the alert whose own resolution completed the "all members resolved" condition (Round 1, Q5) |
| `IncidenteReativado` | `reativar_incidente(incidente_id, alerta_id_disparador, …)` | the alert that reappeared and reactivated (mirrors `AlertaReativado`, [[decisions/alert-reactivation-instead-of-crash]]) |
| `IncidenteFundido` | `fundir_incidentes(sobrevivente_id, fundido_id, alerta_id_disparador, …)` | the alert whose processing revealed the two open incidents describe the same physical event |

In v1's forward-only design (Round 1, Q6) every incident transition is driven
by processing one specific alert during ingestion — there is no background
sweep that re-evaluates incidents independently of a new alert — so none of
the five is exempt, and `agregado_id NOT NULL` holds without weakening.

## The atomic invariant, validated in code, not as a CHECK constraint

`agregado_incidente_id IS NOT NULL` **if and only if** `tipo` is one of the
five incident event types. SQLite cannot add a `CHECK` constraint via `ALTER
TABLE`, and doing so would break `_migrar_banco`'s additive-only policy (same
reasoning as the #22 FK itself). Instead, `_inserir_evento_outbox` — the
single insertion point the five incident state-change functions funnel
through — validates it at runtime, in the same
`tem_X != esta_Y → raise ValueError` style as
`Alerta._validar_invariante_classificacao` and
`Incidente._validar_invariante_resolucao`:

```python
eh_evento_incidente = tipo in _TIPOS_EVENTO_INCIDENTE
tem_agregado_incidente = agregado_incidente_id is not None
if eh_evento_incidente != tem_agregado_incidente:
    raise ValueError(...)
```

Covered by `TestInvarianteAgregadoIncidenteId` in `tests/test_database.py`.

`aplicar_resultado_deteccao` keeps its own pre-existing `INSERT INTO eventos`
rather than being rerouted through the helper — a deliberate non-change, to
keep #59's diff off working alert-path code. That INSERT never names
`agregado_incidente_id`, so alert events take the column default (`NULL`) and
satisfy the invariant by construction. Centralising both paths on
`_inserir_evento_outbox` is a legitimate later cleanup, not a correctness fix.

## Migration path for existing databases

`incidentes` and `incidente_membros` are brand-new tables, created directly
via `CREATE TABLE IF NOT EXISTS` in `criar_banco()` — no rejection branch
needed in `_verificar_compatibilidade_schema`, same reasoning the Camada 5
technical plan already recorded. The `eventos.agregado_incidente_id` column
is different: it extends an *existing* table, so it goes through
`_migrar_banco()`'s additive `ALTER TABLE ADD COLUMN` path, guarded by
`if "agregado_incidente_id" not in colunas_eventos`. Verified empirically
(not assumed) that SQLite's `ALTER TABLE ADD COLUMN` accepts an inline
`REFERENCES` clause and enforces it identically to a table-level `FOREIGN
KEY` clause declared at `CREATE TABLE` time, and that a `CREATE TABLE`
statement may forward-reference a table that does not exist yet (SQLite does
not validate FK targets at DDL time). That second property is load-bearing,
not decorative: `criar_banco()` creates in the order `alertas` → `eventos` →
`incidentes` → `incidente_membros` → `_migrar_banco`, so the `eventos` table
declares its FK to `incidentes` **before** `incidentes` exists. The child-key
index
`idx_eventos_agregado_incidente_id` is created *after* `_migrar_banco()`
returns, not alongside the other `eventos` indexes — creating it earlier would
fail with "no such column" on a legacy database before the `ALTER TABLE` runs.

## `ON DELETE NO ACTION`, index-every-FK-child, per-connection enforcement

All unchanged from the #22 precedent: no cascade (the outbox is an audit
trail), every FK's child column gets an index (`idx_incidentes_fundido_em`,
`idx_incidente_membros_incidente_id`, `idx_eventos_agregado_incidente_id`;
`incidente_membros.alerta_id` gets an implicit index for free from its own
`UNIQUE` constraint), and enforcement is per-connection via `conectar()`'s
`PRAGMA foreign_keys=ON` — raw `sqlite3.connect(...)` connections remain
unenforced by design.
