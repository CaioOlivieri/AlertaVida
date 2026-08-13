status: implemented
sources: `src/alertavida/database.py`, `tests/test_database.py`, issue #60, PR #76
updated: 2026-08-12

# Blocking Spatial Index: R-Tree Confirmed, No Fallback Needed

Issue #60 required empirical proof — not inference — that the SQLite build
used by CI (`uv python install`, both `ubuntu-latest` and `windows-latest`)
ships the R-Tree module, before the blocking stage could rely on it. Per
`wiki/_schema.md` rule 1, this could not be asserted from documentation about
`python-build-standalone` (the toolchain `uv` uses); it had to be checked in
both runners as they actually run in this CI matrix.

## Evidence

`TestCapacidadeEspacialSQLite` (`tests/test_database.py`) does two things:
checks `PRAGMA compile_options` for an `RTREE` entry, and actually creates
and queries an `rtree` virtual table. Both tests ran in PR #76's CI on both
legs and passed:

```
pytest (ubuntu-latest):  test_rtree_habilitado_via_compile_options PASSED
                          test_rtree_cria_tabela_virtual_e_consulta PASSED
pytest (windows-latest): test_rtree_habilitado_via_compile_options PASSED
                          test_rtree_cria_tabela_virtual_e_consulta PASSED
```

Local verification (Linux, same `uv python install` toolchain as
`ubuntu-latest`) additionally printed `sqlite3.sqlite_version: 3.50.4` with
`ENABLE_RTREE` present in `compile_options`.

**Decided: use the real R-Tree module.** The `plain indexed min/max bbox
columns` fallback named in the issue was not needed on either matrix leg.

## What the R-Tree indexes

Not `incidentes` — the Camada 5 kickoff technical plan is explicit that
issue #60 "adds the third table" (`correlacao_observacoes`), meaning no new
columns on `incidentes` were planned. Instead, `idx_alertas_espacial` is a
standalone `USING rtree(id, min_lat, max_lat, min_lon, max_lon)` virtual
table indexing every `alertas` row as a degenerate point bbox
(`min_lat = max_lat = latitude`, same for longitude). `id` matches
`alertas.id`.

An alert's position never changes after `CRIADO` (`aplicar_resultado_deteccao`'s
ATUALIZADO/REATIVADO branches never touch `latitude`/`longitude`), so a
single `INSERT` at creation time is sufficient — no update path is needed.
Pre-existing alerts (a database that already had rows before this migration)
are backfilled idempotently in `_migrar_banco()` via
`INSERT ... SELECT ... WHERE id NOT IN (SELECT id FROM idx_alertas_espacial)`.

Candidate generation then joins `idx_alertas_espacial` → `incidente_membros`
→ `incidentes` (filtered to `status = 'ATIVO' AND fundido_em IS NULL`) —
the R-Tree bbox test only ever touches members of already-open incidents,
keeping the query cost O(open incidents), never O(history) (Round 1, Q6;
`wiki/projects/layer-5-correlation.md`).

## Blocking buffer, never used on the decision path

`BUFFER_BLOQUEIO_GRAUS` (`database.py`) converts `domain.correlacao.DISTANCIA_MAXIMA_KM`
(50 km, #58) to decimal degrees using the worst-case longitude compression
in Brazilian territory (~34°S, 1° longitude ≈ 92 km, rounded down) so the
buffer never under-selects at any Brazilian latitude — latitude's ~111 km/°
is roughly constant, so the same buffer over-covers that axis too. This
value only feeds the R-Tree `WHERE` clause; the actual decision
(`domain.correlacao.decidir_correlacao`) always uses exact haversine
distance over real coordinates, never degrees (Round 1, Q2).

A known v1 gap: candidate generation is spatial-only (bbox + per-type time
window). It does not also block on `codigo_ibge` equality, so a pathological
case — same municipality, but far enough apart to miss the buffered bbox —
would be excluded from candidates even though `decidir_correlacao` could
still have linked it on administrative-key evidence alone. The issue spec
frames candidate generation strictly as bbox + window, not `codigo_ibge`;
adding an IBGE-based blocking path is left to a future issue if it proves
necessary in the `#63` calibration data.
