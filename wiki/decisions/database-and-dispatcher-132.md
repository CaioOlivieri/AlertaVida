status: implemented
sources: `src/alertavida/database.py`, `src/alertavida/events.py`, `tests/test_database.py`, `tests/test_events.py`, issue #132
updated: 2026-11-23

# Partial pending index, batched stamping, handlers outside the write lock

Found by the 2026-11-13 audit ([[audit-2026-11-13]]); done before the INMET
source (#153), which adds a table and a large `(warning, municipality)`
fan-out.

## 1. `idx_eventos_pendentes` becomes a partial index (schema step 2)

The dispatcher's only query is `WHERE processado_em IS NULL ORDER BY
criado_em LIMIT n`, and almost the whole outbox is already processed. The
full index on `(processado_em, criado_em)` indexed every row ever written.
Now: `CREATE INDEX idx_eventos_pendentes ON eventos (criado_em) WHERE
processado_em IS NULL` — the size of the pending queue.

Second numbered step under `PRAGMA user_version` (1 → 2), after #127's
(0 → 1); same transaction as `criar_banco()`. `CREATE INDEX IF NOT EXISTS`
does not replace an existing index of the same name, hence the explicit
`DROP` + `CREATE` once.

Measured on a copy of the 2026-11-22 production backup (6,825 events, 0
pending):

| | Before | After |
|---|---|---|
| `idx_eventos_pendentes` | 516 KB (12.4 % of the file) | **4 KB** |
| File, both vacuumed | 3,832 KB | **3,380 KB** (−12 %) |
| Dispatcher plan | `SEARCH eventos USING INDEX idx_eventos_pendentes (processado_em=?)` | `SCAN eventos USING INDEX idx_eventos_pendentes` (the partial index holds only pending rows) |

## 2. `visto_ultima_vez` stamping in batches

`aplicar_resultado_deteccao` ran one `UPDATE` per alert seen-but-unchanged
and one per alert absent — ~100 statements per round. `_atualizar_em_lote`
groups the codes by source and runs one `UPDATE ... WHERE fonte = ? AND
cod_alerta IN (...)` per source, in chunks of 500 parameters (well below
SQLite's limit on any bundled version). A test with a chunk size of 2 and
the same `cod_alerta` in two sources pins the resulting rows, including the
untouched ones.

## 3. Handlers run outside any write transaction

`OutboxDispatcher.processar_pendentes` used to publish each event and
`UPDATE` it inside one connection's transaction: the first `UPDATE` opened
the write transaction, and it stayed open while the handlers of every
following event ran. Harmless with `log_handler`; a network handler
(Camada 8) would have held the lock and made the ingestion round hit
`busy_timeout`.

Now: read the batch → publish (no transaction) → mark the batch with one
`UPDATE ... WHERE id IN (...)` in a short transaction.

**Proved with a test that fails on the old code:** a handler opens a second
connection with `timeout=0` and tries `BEGIN IMMEDIATE`. Old dispatcher,
three events: `[True, False, False]` — the lock was held from the second
event on. New: `[True, True, True]`.

**Delivery semantics unchanged: at-least-once.** A crash between publishing
and marking re-delivers the batch — as before, when the rollback undid the
whole batch's marks.
