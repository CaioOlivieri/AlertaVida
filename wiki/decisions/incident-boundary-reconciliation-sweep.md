status: implemented
sources: `src/alertavida/database.py`, `src/alertavida/ingestion/orquestrador.py`, issue #87
updated: 2026-09-05

# Reconciliation sweep for the incident-correlation transaction boundary (issue #87)

## The gap, and how #78 changed it

`_abrir_ou_juntar_incidente` runs `avaliar_candidatos_correlacao` (its own
transaction, writes `correlacao_observacoes`) and then `criar_incidente` or
`adicionar_membro_incidente` (a separate transaction, writes
`incidente_membros`). A process killed between the two leaves the alert
durably `ATIVO` with no `incidente_membros` row. There is no self-heal path:
an `ATIVO` alert with unchanged `ult_atualizacao` is classified `INALTERADO`
by `detectar_mudancas`, which never produces an `EventoDetectado`, so
`_correlacionar_rodada`'s event loop never looks at this `cod_alerta` again
([[decisions/incident-lifecycle-wiring]], "Correlation failure is
permanent").

Issue #78 (systemd deployment, `KillSignal=SIGINT` + a real
`shutdown(wait=True)` drain) closed the dominant trigger: `systemctl
stop`/`restart` now waits for the in-flight round to finish before the
process exits, so a graceful restart can no longer land in this window
([[decisions/systemd-vps-deployment]], "Consequence for #87"). What's left
is SIGKILL (OOM, `systemctl kill -s KILL`) and a crash inside
`_correlacionar_rodada` itself — routine on this host, since WSL's reboot
and suspend paths do not go through systemd's graceful shutdown at all.

## Reproduction (evidence, per `_schema.md` rule 1)

Deleting the `incidente_membros` row for an alert still present in the feed
and running three subsequent rounds:

```
apos o 'crash': membros=0, incidentes=0
  rodada 2: novos=0 atualizados=0 inalterados=1 inc_criados=0
  rodada 3: novos=0 atualizados=0 inalterados=1 inc_criados=0
  rodada 4: novos=0 atualizados=0 inalterados=1 inc_criados=0

membership final: 0   incidentes finais: 0
-> alerta orfao permanente
```

Confirms the gap is real and permanent, not theoretical, prior to this
issue's fix. Production baseline at the time this issue was picked up: 0
orphans in 574 alerts — the window had never been hit, because the process
had never died mid-round before #78 put it under systemd restart/kill
pressure.

Connection-cost measurement (instrumented `sqlite3.connect`), cited because
option (b) below would have eliminated this cost as a side effect:

```
n=  50 alertas novos ->   102 conexoes sqlite  (2.0/alerta)   48.5 ms
n= 200 alertas novos ->   302 conexoes sqlite  (1.5/alerta)  157.1 ms
rodada sem mudanca   ->     2 conexoes                         1.6 ms
```

Cost in steady state is low and proportional to *new* alerts per round —
not an urgent problem on its own.

## Decision: (a), reconciliation sweep — not (b), shared connection

Two options were on the table:

- **(a) Reconciliation sweep.** At the start of `_correlacionar_rodada`, a
  `SELECT` of `ATIVO` alerts from the source with no `incidente_membros`
  row, correlating each one exactly as `_abrir_ou_juntar_incidente` would
  for a fresh `CRIADO`. Reversible, touches no transaction boundary.
- **(b) Shared connection.** `avaliar_candidatos_correlacao`,
  `criar_incidente`, `adicionar_membro_incidente`, `fundir_incidentes`,
  `buscar_incidente_atual`, `status_incidente` and
  `todos_membros_resolvidos` all accept a `conexao` parameter, and the
  whole correlation round becomes one transaction. Makes the invariant true
  in the literal sense and eliminates the per-alert connection cost above.

**Decided: (a).** Reasons, in order of weight:

1. **Reversibility against a live, production coordinator.** (b) changes
   the transactional shape of seven functions against a collector polling
   every 5 minutes with real data. Any subtle interaction — specifically
   the one flagged below — would only surface under real production load,
   and undoing it means reverting the same seven signatures again. (a) is
   one extra query per source per round, trivially removable.
2. **The acceptance criteria explicitly allow the exception route.** Either
   Camada 5 complies with invariant 4, or the invariant gets an explicit
   exception plus a compensating mechanism. (a) is the second branch,
   honestly described (see below) — not a cosmetic fix.
3. **The connection cost isn't the problem being solved here.** The
   measured 1.5–2.0 connections/alert at 48–157ms in steady state show no
   performance urgency. (b) would resolve that for free, but that's solving
   a problem the issue itself says doesn't exist yet — engineering ahead of
   the actual need.

**Why (b) is rejected now, specifically:** (b)'s transaction would last the
entire correlation round. With `busy_timeout=5000` and a dispatcher job
polling `eventos` every 30s, a round with many new alerts could hold the
write lock long enough that the dispatcher's own write blocks for the full
5s and then raises `SQLITE_BUSY` — a real, unmeasured risk, not a
hypothetical one. The issue explicitly requires whoever proposes (b) to
state how they'd handle that interaction before the choice is made; no such
proof exists, and (a) never needs it because it doesn't touch the
transaction boundary at all.

## What (a) does NOT do — invariant 4's exception, stated honestly

**The sweep does not make Camada 5 comply with invariant 4.** The two
transactions inside `_abrir_ou_juntar_incidente` are still separate
commits; a crash between them can still produce an `ATIVO` alert with no
membership, for up to one round's duration. What (a) adds is a
**compensating mechanism**: the *next* round's sweep, for that source,
finds and correlates it. This is invariant 4's exception branch, not its
compliance branch — `wiki/patterns/resilience-invariants.md`'s invariant 4
entry now states this explicitly, scoped to `aplicar_resultado_deteccao`
only, with Camada 5's own persistence chain named as the carved-out
exception.

Worth stating in the same breath: this recovery bound is **one round**
(5 minutes in production), not indefinite — the sweep runs unconditionally
every round, so an orphan is caught the very next time `_correlacionar_
rodada` runs for its source, well before `rodadas_ausente` could ever push
it to `RESOLVIDO` (see below for why that matters).

## Where it runs: inside `_correlacionar_rodada`, per source — recovery, not prevention

`buscar_alertas_orfaos(fonte)` runs at the very start of
`_correlacionar_rodada`, before that round's own `eventos` loop, reusing the
per-source loop `executar_ingestao` already has (one extra query per source
per round, empty in the normal case).

This has to explicitly exclude the alert ids `aplicar_resultado_deteccao`
just persisted **this same round** (`ids_por_codigo.values()`). A `CRIADO`
alert from the current round is, at the moment the sweep runs, already
`ATIVO` with no `incidente_membros` row — indistinguishable from a real
orphan by the `WHERE` clause alone, because `_abrir_ou_juntar_incidente`
hasn't run for it yet in the loop below. Without the exclusion, the sweep
double-processes it and the second `adicionar_membro_incidente`/
`criar_incidente` call violates `UNIQUE (alerta_id)` on
`incidente_membros` (caught by the full test suite on the first attempt at
this — 20 tests failed with exactly that `IntegrityError` before the
exclusion was added; `uv run pytest -q` now reports 410 passed, 1
deselected, 0 failed). The docstring on `_correlacionar_rodada` states this
plainly: the sweep is recovery for a **previous** round's failure, never a
substitute for processing the **current** round's events.

## RESOLVIDO orphans are explicitly out of scope

`buscar_alertas_orfaos`'s `WHERE` is `status_interno = 'ATIVO' AND` no
`incidente_membros` row — deliberately excluding `RESOLVIDO`. An orphan that
transitions to `RESOLVIDO` before ever being swept (a narrow race: the same
round that would have caught it also pushes it past its
absence threshold) is left uncorrelated, permanently, exactly like a
pre-#61 legacy alert that resolves without ever having been correlated
([[decisions/incident-lifecycle-wiring]], "RESOLVIDO" bullet under
"Coverage starts at deploy"). Opening a new Incident for an alert that's
already dead has no operational value — an Incident is supposed to
represent live, ongoing correlated activity — so this is the same
mild-severity, explicitly-accepted gap the project already lives with, not
a new one. Not treated as unsafe, same reasoning as the existing precedent.

## Trigger for reconsidering (b)

Written down so "temporary compensation" doesn't become permanent by
omission. Reopen the shared-connection design if either of these is
observed:

- **The sweep recovers an orphan in production more than once.** One
  recovery in the lifetime of the deployment is the system working as
  designed (SIGKILL/OOM/crash happens, the sweep catches it next round). A
  second occurrence means the crash-and-recover cycle is no longer a rare
  operational event, and the cost of running correlation as one transaction
  becomes worth paying to close the window at the source instead of
  compensating for it every time.
- **New-alerts-per-round grows enough that the 1.5–2.0
  connections/alert cost starts to matter** — a real volume increase (a
  larger source like INMET/INPE, or a backfill), not the current steady
  state.

Either condition is directly observable: `RelatorioFonte` now has an
`incidentes_orfaos_recuperados` counter (0 in the normal case), logged every
round by `scheduler.py`'s existing `formatar_relatorio` call into journald —
no new instrumentation needed to watch for the first trigger.

## Correction to invariant 4's scope

Invariant 4 ("Transactional outbox") is now stated as scoped to
`aplicar_resultado_deteccao` (`alertas` + `eventos`) only, with Camada 5's
own Incidente-persistence chain named as an explicit, documented exception
compensated by this sweep — see
`wiki/patterns/resilience-invariants.md`. Shipping this issue with the wiki
silently implying invariant 4 covered the whole system, while the code
still didn't, was exactly the wiki/code divergence issue #86 fixed
elsewhere — the invariant would have been misdescribed the same way here if
left as-is.
