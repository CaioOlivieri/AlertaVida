status: done
sources: [[raw/context-md-2026-06-11.pt.md]] (§3)
updated: 2026-06-11

# Layer 1: Resilient Data Ingestion

CEMADEN feed consumption with retry+backoff, SQLite persistence with dedup by `cod_alerta` PK.

**Delivered:**
- `monitor.py` fetches from CEMADEN with exponential backoff (4 attempts: immediate, 2s, 4s, 8s)
- `database.py` persists to SQLite with dedup
- `scheduler.py` wraps everything in APScheduler (5 min interval)
- Schema compatibility enforced via `_verificar_compatibilidade_schema()`
- 4xx errors (except 408/429) skipped; 5xx/timeout retried
- UTF-8 stdout reconfigure for Windows
