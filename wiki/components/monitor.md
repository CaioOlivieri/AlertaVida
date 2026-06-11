status: integrated
sources: `src/alertavida/monitor.py`
updated: 2026-06-11

# monitor

Entrypoint for one-shot ingestion (`python -m alertavida.monitor`). Pure entrypoint (46 lines) after B.2.b refactor:

- `main()` — calls `criar_banco()`, instantiates `CemadenSource()`, calls `executar_ingestao()`, prints formatted report, returns exit code 0.
- `_formatar_relatorio()` — pure function, testable without I/O.
- `raise SystemExit(main())` in `if __name__ == "__main__"`.

Contracts: imports from `alertavida.ingestion.orquestrador` and `alertavida.sources.cemaden`. UTF-8 stdout reconfigure at top for Windows compatibility.
