status: implemented
sources: `src/alertavida/sources/cemaden.py`, `src/alertavida/domain/tempo.py`, `src/alertavida/domain/alerta.py`, `src/alertavida/database.py`, issue #127, production database (2026-11-14), `data/weathernext_cemaden_captures/`
updated: 2026-11-16

# CEMADEN timestamps are Brasília time: source-owned zone + one-time migration

The CEMADEN painel sends `datahoracriacao` / `ult_atualizacao` without an
offset (`"2026-11-13 17:31:22.137"`). `parse_iso_utc` assumed UTC for naive
input ([[decisions/utc-timestamps-consistency]]), so every CEMADEN
timestamp stored before #127 was **3 hours early**.

## Evidence (measured, not read from documentation)

The painel publishes no documentation of the field's zone. Three independent
measurements:

- **Production database, 756 CEMADEN alerts:** `detectado_em −
  datahoracriacao`, stored value read as UTC, was never below **180.7 min**;
  zero alerts under 175 min, 60 between 180 and 190. A 5-minute poller cannot
  be systematically 3 h late on a fresh alert and never once earlier.
- **1,049 raw captures** (5-minute cadence, [[decisions/weathernext-surge-watch-design]]):
  over 42 alerts first seen in a continuous sequence, minimum lag 180.9 min,
  median 183.
- **The envelope says so where the items don't:** `"atualizado": "13-11-2026
  21:50:01 UTC"`.

After the migration was rehearsed on a copy of the production database, the
same minimum lag dropped from 180.7 min to **0.7 min**, with no negative
value — the fix closes the gap instead of overshooting it.

## Decisions

**The zone belongs to the source.** `parse_iso_utc` gained
`fuso_se_naive` (default UTC); `Alerta.from_dict` passes it through;
`CemadenSource` declares `FUSO_PAINEL_CEMADEN = UTC−3`. EONET (offset-bearing
`Z` strings) is unchanged. A string that carries its own offset always wins.
Same principle as invariant 10: each source owns its quirks.

**`parse_iso_utc` now always normalizes to UTC.** Before, an explicit
`-03:00` was kept as `-03:00`. One `.isoformat()` shape for every source
matters because `ChangeDetector` compares `ult_atualizacao` **as a string**
against the stored snapshot.

**Fixed offset, not `zoneinfo("America/Sao_Paulo")`.** Brazil abolished DST
in 2019, and `zoneinfo` needs the `tzdata` package on Windows (CI runs
`windows-latest`) — a new runtime dependency for a constant. If DST returns,
`FUSO_PAINEL_CEMADEN` is the one place to change.

**Migration gated by `PRAGMA user_version`.** Until #127 every migration in
`_migrar_banco` was idempotent by inspection (does the column exist?). A
value shift cannot be inspected — running it twice would add 6 h. The
database now carries a schema version: 0 = before #127, 1 = CEMADEN
timestamps in UTC. Fresh databases start at 1. `user_version` is
transactional in SQLite (verified), so the `UPDATE`s and the bump commit
together or not at all — a test simulates a failure mid-migration and
checks nothing was shifted.

**The migration's offset is frozen.** `_DESLOCAMENTO_FUSO_CEMADEN` in
`database.py` is deliberately *not* imported from `sources/cemaden.py`: it
describes the error the pre-#127 data carries, not the painel's current
zone.

**Migrated strings equal freshly parsed strings, byte for byte.** Done in
Python via `datetime`, not SQL string arithmetic. A parametrized test feeds
the same raw value through both paths. A drift of one character would have
emitted a spurious `AlertaAtualizado` for every active CEMADEN alert on the
first round after deploy.

## Not migrated, on purpose

`eventos.payload` — the outbox is append-only history; its `data_criacao` /
`ult_atualizacao` fields for CEMADEN events before 2026-11-14 keep the old,
3-hour-early values. Anyone reading historical payloads must apply the
shift; this page is that record.

## Impact on Camada 5

None so far: on 2026-11-14 there were 0 cross-source rows in
`correlacao_observacoes` and 0 mixed-source incidents, so no recorded
decision depended on the wrong offset. CEMADEN × CEMADEN comparisons were
unaffected (the error cancels). The fix matters for what comes next:
CEMADEN × EONET windows and #63's calibration corpus.

## Rehearsal on a copy of production (2026-11-14)

On a `.backup()` copy of `alertavida-20261114T135031Z.db`, running the new
`criar_banco()`:

- `user_version` 0 → 1; **756** CEMADEN rows shifted, every one by exactly
  3.0 h; EONET rows byte-identical; `integrity_check` ok.
- Second `criar_banco()`: no further shift.
- Simulated next round (live painel payload, new parser, migrated
  snapshots): 3 alerts, **0 events** — no spurious `AlertaAtualizado`.

### Measured after the deploy (2026-11-16, service at `82d491c`)

The redeploy happened two days after the merge (2026-11-16 17:40 -03), so
the migration ran against 777 CEMADEN rows, not 756. Read from the production
database and the journal at 17:50 -03:

| | Measured |
|---|---|
| `PRAGMA user_version` | 1 |
| Minimum `detectado_em − datahoracriacao`, 777 CEMADEN rows | **0.7 min**, 0 negative (was 180.7 min) |
| Spurious CEMADEN `AlertaAtualizado` after the restart | **0** |
| First round | CEMADEN 20 collected (17 new, 3 unchanged); EONET 82 |
| Following rounds | all unchanged |
| Restarts / error lines in the journal | 0 / 0 |
