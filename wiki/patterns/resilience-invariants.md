status: integrated
sources: [[raw/claude-md-2026-06-11.pt.md]]
updated: 2026-06-11

# Resilience Invariants

1. **Counter assertion in `executar_ingestao`** — `novos + atualizados + reativados + inalterados + descartados == coletados` per source. If you add a new outcome path, increment the matching counter.
2. **Per-item `try/except` in the ingestion loop** — one bad alert must never stop the rest of the batch. Errors are counted, not raised.
3. **Retry only on 5xx / 408 / 429 / URLError / socket.timeout** — 4xx (other than 408/429) re-raise immediately.
4. **Transactional outbox** — INSERTs into alerts and outbox events must happen in the same SQLite transaction.
5. **`ChangeDetector` is pure** — no I/O, no database, no network.
6. **`BackgroundScheduler` + `time.sleep(1)` loop** — don't switch to `BlockingScheduler`.
7. **`max_instances=1, coalesce=True, misfire_grace_time=60`** — prevents pile-up.
8. **UTF-8 stdout reconfigure in `monitor.py`'s `__main__` entrypoint block (before `main()`)**, guarded by `hasattr(sys.stdout, 'reconfigure')` — Windows consoles default to cp1252.
9. **`escopo_geografico` is computed at ingestion time, never at query time** — reclassification requires `scripts/reclassificar_escopos.py`.
10. **`TipoEvento` values are COBRADE subgroups, not source terminology** — each `DataSource` implements its own mapping to neutral values.
11. **`cobrade_codigo` and `fonte_classificacao` change atomically** — any UPDATE must change both in the same transaction.
12. **Schema check before `_migrar_banco()`** — `criar_banco()` calls `_verificar_compatibilidade_schema()` first.
13. **`Alerta.fonte` is `Annotated[FonteDado, Strict()]`, never a raw string** — strict cirúrgico via `Annotated`, not global `strict=True`.
14. **`ResultadoDeteccao.fonte_por_codigo` is populated for EVERY code** in `codigos_vistos ∪ codigos_ausentes`.
15. **`buscar_snapshots` reads `fonte` from the row via `FonteDado.from_string`** — safety net for corrupt data. Returns snapshots of all statuses (not only ATIVO) so that RESOLVIDO alerts reappearing in the feed are detected.
16. **`DataSource.coletar()` is side-effect-free except for network reads** — no print, no database writes, no filesystem.
17. **Orchestrator isolates failures per source** — each `source.coletar()` call wrapped in `try/except FalhaDeColeta`.
18. **`RelatorioFonte` counters obey the sanity assertion per source** — `coletados == novos + atualizados + reativados + inalterados + descartados`.
19. **`CemadenSource.coletar()` captures ONLY `ValueError` when mapping each raw item** — internal bugs propagate.
20. **Round-level failures wrapped in `FalhaDeColeta(fonte=self.fonte, causa=..., original=exc)` with `from exc`** — do not let raw transport exceptions leak from `coletar()`.
21. **A RESOLVIDO alert reappearing in the feed MUST emit `AlertaReativado` and reactivate the row** — never INSERT (UNIQUE constraint) and never silently ignore.
22. **cod_alerta MUST be unique per batch in `executar_ingestao`** — duplicates within the same source response are deduplicated (first occurrence kept, each duplicate increments `descartados`).
23. **Unknown payload format in `_normalize_payload` MUST raise `FalhaDeColeta`** — a dict without any recognized wrapping key, or a non-list/non-dict payload, must not silently return an empty list.
