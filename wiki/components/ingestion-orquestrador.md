status: integrated
sources: `src/alertavida/ingestion/orquestrador.py`
updated: 2026-09-05 (issue #87)

# ingestion-orquestrador

Ingestion orchestrator (B.2). Pure orchestration — no entrypoint responsibility:

- `executar_ingestao(sources, *, agora=None)` — for each `DataSource`: calls `coletar()`, isolates `FalhaDeColeta`, runs `detectar_mudancas` + `aplicar_resultado_deteccao`, then `_correlacionar_rodada` (issue #61 — Camada 5 correlation, see below). Returns `RelatorioIngestao`.
- `RelatorioFonte` — frozen dataclass with `__post_init__` invariants (counters balance when no failure; zero + `coletado_em=None` on failure; the four incident counters below are included in the failure-branch zero check).
- `RelatorioIngestao` — frozen aggregate with `@property total`.

Orchestrator is silent (zero print/logging). Presentation is caller's responsibility. `agora` generated once and propagated for all sources.

## Correlation wiring (issue #61)

Right after `aplicar_resultado_deteccao` persists a source's batch (which now
returns `{cod_alerta: alerta_id}` — see
[[decisions/incident-lifecycle-wiring]]), `_correlacionar_rodada` applies the
Camada 5 Incidente lifecycle (Round 1, Q6, forward-only — see
[[projects/layer-5-correlation]]) over that batch's `EventoDetectado`s:

- **CRIADO** → `_abrir_ou_juntar_incidente`: runs `avaliar_candidatos_correlacao`
  (#60 blocking → #58 pure decision) and acts on the result. A single
  `VINCULA` joins that Incidente (`adicionar_membro_incidente`); zero
  `VINCULA` opens a new one (`criar_incidente`, even when a `REVISAO`
  observation exists — Round 2's bias to split means `REVISAO` never
  auto-links); two or more distinct `VINCULA`s triggers a merge
  (`fundir_incidentes`, survivor = the older/lower-id Incidente).
- **REATIVADO** → if the alert already has a permanent Incidente membership
  (`buscar_incidente_atual`), blocking is *not* re-run — only reactivates
  that Incidente via `reativar_incidente` if it had resolved (Round 1, Q5).
  Otherwise (no prior membership) falls back to the CRIADO path.
- **RESOLVIDO** → `todos_membros_resolvidos` (merge-tree aware) gates
  `resolver_incidente`: only when every member — including ones inherited
  through a merge — is resolved.
- **ATUALIZADO** does not participate — justified in
  [[decisions/incident-lifecycle-wiring]] (position/onset are immutable
  after CRIADO; re-running blocking on every update would almost always
  reproduce the same decision).

**Reconciliation sweep (issue #87).** Before any of the above,
`_correlacionar_rodada` calls `buscar_alertas_orfaos(fonte)` and runs each
result through `_abrir_ou_juntar_incidente` — recovery for an alert left
`ATIVO` with no `incidente_membros` row by a process killed between
`avaliar_candidatos_correlacao` and `criar_incidente`/
`adicionar_membro_incidente` in a *previous* round. Ids already in this
round's `ids_por_codigo` are excluded (they're mid-flight in the loop
below, not orphaned). See
[[decisions/incident-boundary-reconciliation-sweep]] for why this — not a
shared-connection transaction — was chosen, and invariant 4's now-explicit
exception for this persistence chain.

`RelatorioFonte` gained five counters — `incidentes_criados`,
`incidentes_juntados`, `incidentes_fundidos`, `incidentes_revisao`,
`incidentes_orfaos_recuperados` — rendered
by `formatar_relatorio` ([[components/reporting]]). Incident *resolution* and
*reactivation* are deliberately **not** counters here, mirroring the existing
precedent for alert resolution (`RelatorioFonte` has no `resolvidos` field
either): both are derived from absence/reappearance over time, not a
synchronous outcome of the collected batch, and are verified end-to-end via
the outbox (`eventos` table) instead — same pattern as
`test_alerta_ausente_por_tres_rodadas_emite_resolvido_no_outbox`.
