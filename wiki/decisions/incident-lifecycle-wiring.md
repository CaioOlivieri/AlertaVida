status: implemented
sources: `src/alertavida/ingestion/orquestrador.py`, `src/alertavida/database.py`, issue #61
updated: 2026-08-13

# Incident Lifecycle Wiring (issue #61)

Camada 5's kickoff technical plan ([[projects/layer-5-correlation]]) scoped
issue #61's "Files it touches" to `ingestion/orquestrador.py` + `reporting.py`
+ tests. Implementation needed three small additive reads on `database.py`
too, plus a return-value extension on an existing function — recorded here
because both are real deviations from that plan, not because either changes
an already-decided architecture.

## Why `database.py` needed touching after all

`avaliar_candidatos_correlacao(alerta_id, agora)` (#60) and the five
Incidente state-change functions (#59) all key off `alerta_id` (the
surrogate int), but `aplicar_resultado_deteccao` (#22/#59-era) computed that
id internally and returned nothing. The wiring point the kickoff plan itself
chose — "immediately after `aplicar_resultado_deteccao()`", in
`orquestrador.py` — has no other way to learn the id.

**Decided: extend `aplicar_resultado_deteccao`'s return type from `None` to
`dict[str, int]`** (`{cod_alerta: alerta_id}`), populated for every event
with a resolved `agregado_id` (CRIADO/ATUALIZADO/REATIVADO/RESOLVIDO — the
function already computes it in each branch), over adding a new
lookup-by-natural-key query function. Reasons:

- **Tell, Don't Ask**, the same principle `ResultadoDeteccao`'s own
  docstring already invokes: the persist step already knows the id inside
  the same transaction; re-querying it by `(fonte, cod_alerta)` a moment
  later would be a redundant round trip per alert, every round, forever.
- **No caller depended on the old `None` return.** `orquestrador.py` was the
  sole caller and never read the value; test doubles that stood in for the
  function (`tests/ingestion/test_orquestrador.py`'s
  `aplicar_com_falha_na_segunda`) needed one line added (`return
  _real(...)` instead of a bare call) to keep passing — not a contract
  break for any real consumer.

Three new small read-only query functions were added alongside it, all
needed by the lifecycle logic below and none present before #61:
`buscar_incidente_atual(alerta_id) -> int | None` (follows the `fundido_em`
redirect chain to the current survivor), `status_incidente(incidente_id) ->
str`, and `todos_membros_resolvidos(incidente_id) -> bool` (a recursive CTE
over the merge tree — see below for why the tree, not just the row, has to
be walked).

## Merge-survivor selection: the older (lower-id) incident

When a single alert's blocking candidates include **two** distinct open
Incidents that both reach `VINCULA`, the alert itself is the evidence that
proves the two describe one physical event (Round 1, Q6 — "triggers a merge
of two open incidents"). Something has to pick which one survives.

**Decided: the incident with the lower id (the older one) survives**;
`adicionar_membro_incidente` attaches the triggering alert to it, then
`fundir_incidentes(sobrevivente, fundido, ...)` redirects the newer one.
Deterministic, requires no extra query (ids are already in hand from the
blocking result), and matches the intuitive reading — the incident that
existed first absorbs the newer duplicate, rather than the reverse.

## REATIVADO: two different paths depending on prior membership

Q6 groups CRIADO and REATIVADO together ("correlate CRIADO and REATIVADO
alerts"), but they cannot share one code path. A REATIVADO alert already
has a permanent `incidente_membros` row from whenever it first correlated
(`UNIQUE (alerta_id)` — membership is never deleted, Round 1 Q6 forward-only
append-only), so blindly re-running `_abrir_ou_juntar_incidente` on it would
try to `INSERT` a second membership row and violate that constraint.

**Decided:** `_correlacionar_rodada` checks `buscar_incidente_atual` first.
If the alert already belongs to an Incidente, blocking is **not** re-run —
the only possible action is reactivating that Incidente if it had resolved
(Round 1, Q5: a member's reactivation reactivates the Incidente), via
`reativar_incidente`. If it has no membership at all (a REATIVADO alert that
predates #61 being wired, or any other gap), it falls back to the same
`_abrir_ou_juntar_incidente` path CRIADO uses — treated as if newly seen,
since correlation never ran for it before.

## RESOLVIDO propagation walks the merge tree, not just one incident

Round 1 Q5: an Incidente resolves only when its **last** unresolved member
resolves. Checking that naively — "are all rows in `incidente_membros` where
`incidente_id = X` resolved?" — is wrong once a merge has happened, because
`fundir_incidentes` never moves membership rows (append-only redirect,
[[decisions/agregado-incidente-id]] and the schema sketch in
[[projects/layer-5-correlation]]): a merged-away Incidente's members keep
`incidente_id` pointing at the incidente that no longer represents them.
`todos_membros_resolvidos` therefore walks a `WITH RECURSIVE` tree from the
survivor down through every Incidente whose `fundido_em` points into it
(directly or transitively) and counts unresolved members across the whole
tree. Verified in `tests/test_database.py::TestTodosMembrosResolvidos::
test_conta_membros_herdados_por_fusao`.

## An alert whose only candidates are REVISAO still opens its own Incidente

The issue spec states the four outcomes as `VINCULA` → join, "no candidate"
→ new Incidente, two incidents proven same → merge, `REVISAO` → "flagged
observation, no link" — but does not spell out what happens to the alert
itself when blocking finds real candidates and **every one** scores into the
review band (no `VINCULA` anywhere, but not "no candidate" either).

**Decided: it opens a new Incidente, exactly like the no-candidate case**,
in addition to the `REVISAO` row(s) `avaliar_candidatos_correlacao` already
wrote to `correlacao_observacoes`. Reasoning: Round 1, Q6 lists exactly
three permitted operations for any alert — join, open, or trigger a merge —
with no fourth "stay unlinked" state; every CRIADO/REATIVADO-without-prior-
membership alert must resolve to one of the three. Since `REVISAO` can never
resolve to "join" (Round 2 — bias to split, `REVISAO` never auto-links) and
never resolves to "merge" (merge requires `VINCULA` against two candidates),
elimination leaves "open a new one" as the only remaining permitted
operation. This also keeps the invariant `criar_incidente` documents true —
`alerta_id` is always a real triggering alert with a home — and keeps
`REVISAO` cheap exactly as [[projects/layer-5-correlation]]'s v1 scope
decision #5 intends: it is pure instrumentation (a flagged row for a human
to look at later), never a side channel that leaves an alert without an
Incidente. Tested in
`test_correlacao_banda_revisao_alerta_fica_separado_e_observacao_flagada`.

## ATUALIZADO does not re-run correlation (kept the issue's stated default)

`latitude`/`longitude`/`datahoracriacao` (onset) — the only fields blocking
uses to generate candidates — are written **once**, in the CRIADO branch of
`aplicar_resultado_deteccao`; the ATUALIZADO/REATIVADO branch's `UPDATE`
never touches them (see the comment at the CRIADO branch's spatial-index
INSERT, issue #60). `tipo_evento`/`cobrade_codigo` **are** rewritten on
every ATUALIZADO from the source's fresh payload, so they are not, strictly,
immutable — but in practice a tracked alert's risk **level** changes far
more often than its **category** across updates (CEMADEN re-derives from
the same category+level string; EONET's category mapping is set once at
creation and rarely revisited for an ongoing event). Re-running blocking on
every ATUALIZADO would almost always reproduce the same decision at
O(open incidents) extra cost per already-linked alert, per round, forever.
A genuine category flip is a real but rare gap this leaves open — accepted
for v1 given the Round 2 bias toward splitting (a stale link surviving a
rare flip is the cheaper failure mode) and REVISAO's low cost; worth
revisiting if dormant issue #63's calibration data shows it happening in
practice.

## Coverage starts at deploy, not at database creation

Camada 5 only ever acts on an `EventoDetectado` — `_correlacionar_rodada`
iterates `resultado_det.eventos`, and an alert that was already persisted
**before** #61 shipped produces no event at all in any round where its
`ult_atualizacao` hasn't changed: `detectar_mudancas` classifies it
INALTERADO (no `EventoDetectado`), so it never reaches the loop's
if/elif branches. This is not a gap to close — it is forward-only (Round 1,
Q6) working exactly as designed: correlation only ever looks at what
changes going forward, never re-derives meaning from history. No backfill
is proposed here.

The three event types behave differently for a pre-#61 alert, worth being
explicit about since none of them do anything useful for it:

- **INALTERADO forever, until something actually changes it** — no event,
  never enters `_correlacionar_rodada` at all.
- **ATUALIZADO** — reaches the loop but is skipped by the decision above
  (position/onset are what blocking needs, and ATUALIZADO doesn't
  re-correlate regardless of when the alert was created).
- **RESOLVIDO** — if a pre-#61 alert eventually goes three rounds absent,
  the event does fire and `_correlacionar_rodada` does look it up, but
  `buscar_incidente_atual` returns `None` (no `incidente_membros` row was
  ever written for it — correlation never ran while it was still ATIVO),
  so the `if incidente_id is not None` guard is false and nothing happens.
  The alert resolves normally at the `alertas` level; no Incidente is
  involved because none exists to involve.

**REATIVADO is the one path that does bring a pre-#61 alert in**, and by
design: `buscar_incidente_atual` returning `None` for it is exactly the
"no membership at all" branch the REATIVADO decision earlier on this page
already routes to `_abrir_ou_juntar_incidente` — so a pre-existing alert's
first-ever correlation naturally happens the first time it disappears and
reappears after deploy, not before.

Two operational consequences worth stating plainly rather than discovering
in production:

- **(a) `correlacao_observacoes` can stay empty for days after deploy if the
  active-alert base is stable** (nothing newly CRIADO, nothing REATIVADO).
  An empty table right after shipping #61 is expected behavior, not a
  wiring failure — don't read it as a sign the integration didn't take.
- **(b) Issue #63's calibration window starts at the #61 deploy timestamp,
  not at the database's creation date.** The `correlacao_observacoes`
  dataset dormant #63 will calibrate from has no observations for the
  pre-existing alert history — only for alerts CRIADO or REATIVADO after
  this issue shipped. Whoever picks up #63 should read the deploy date off
  this page (or the first row's `criado_em`) before treating the dataset's
  time span as the layer's whole operating history.

## Correlation failure is permanent, not retried

`aplicar_resultado_deteccao` commits its own transaction and returns before
`_correlacionar_rodada` runs — they are separate `with conectar()` blocks,
never one transaction. `executar_ingestao`'s `try/except` only wraps
`source.coletar()`; nothing wraps persistence or correlation, so an
exception raised anywhere inside `_correlacionar_rodada` (blocking, the
domain decision, or any of the five Incidente state-change functions)
propagates out of `executar_ingestao` uncaught — the same "bug deve quebrar
ruidosamente" policy the module docstring already states for any other
unexpected exception.

The consequence is a **new asymmetry introduced by #61**, worth naming
explicitly because it is easy to miss: persistence and correlation used to
be one conceptual step and now fail independently.

- If persistence itself fails, nothing commits (or only earlier sources in
  the round do — pre-existing behavior, unrelated to #61) and the alert
  simply doesn't exist yet; the **next round retries it from scratch as
  CRIADO**, self-correcting automatically.
- If correlation fails **after** persistence already committed, the alert
  is durably `CRIADO` in `alertas` with **no** `incidente_membros` row. The
  next round sees the same `ult_atualizacao` and classifies it INALTERADO
  (per the section above) — no event, so `_correlacionar_rodada` never sees
  this `cod_alerta` again. There is no retry queue and no record that
  correlation was ever attempted and failed (`correlacao_observacoes` only
  gets written by a *successful* `avaliar_candidatos_correlacao` call —
  nothing writes there on an exception). **Persistence self-heals on the
  next round; correlation does not.**

**Severity, stated honestly:** this is not data loss. The alert continues
to exist, continues to emit its own `AlertaCriado`/`AlertaAtualizado`/
`AlertaResolvido`/`AlertaReativado` events exactly as it did before #61, and
remains fully visible at the alert level — it just never joins, opens, or
merges an Incidente. Given Round 2's bias toward splitting (duplicate
incidents are cheap, a wrong merge is the error the project actively
guards against), a permanently solo, uncorrelated alert is the same shape
of outcome as a legitimate `NAO_VINCULA` — undesirable, not unsafe. This is
a mild-severity gap, not a life-safety one.

**Not implemented, left for if it ever matters:** a correlation-failure
counter on `RelatorioFonte` (so the gap would at least be visible in the
per-round report, the way `falha_coleta` already is for collection) and a
reprocessing pass over alerts with no `incidente_membros` row (a query
already expressible with the existing schema: `alertas` where
`status_interno = 'ATIVO'` and no matching `incidente_membros.alerta_id`).
Neither is built now — no observed failure has ever motivated it, and
building retry infrastructure for a mild-severity, not-yet-observed failure
mode would be exactly the kind of premature generality this codebase avoids
elsewhere. Recorded here so the path is known if #63's calibration data (or
production experience) ever shows it happening often enough to justify the
work.
