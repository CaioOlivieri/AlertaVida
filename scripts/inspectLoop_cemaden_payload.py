"""
Inspect the CEMADEN wsAlertas2 payload.

Each run:
  - Fetches the live feed
  - Saves the full raw JSON to data/samples/cemaden_raw_<timestamp>.json
  - Appends a compact summary to data/samples/inspector.log

The log shows alert count, status values, and which alerts appeared or
disappeared since the previous run — the key data for Camada 3 decisions.

Usage:
    python scripts/inspect_cemaden_payload.py              # single run
    python scripts/inspect_cemaden_payload.py --loop 60   # every 60 min
    python scripts/inspect_cemaden_payload.py --loop 30   # every 30 min

Ctrl+C to stop the loop cleanly.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://painelalertas.cemaden.gov.br/wsAlertas2"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
LOG_FILE = SAMPLES_DIR / "inspector.log"
TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_payload() -> bytes:
    req = Request(ENDPOINT, headers={"User-Agent": "AlertaVida-Inspector/0.1"})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# Persist raw JSON
# ---------------------------------------------------------------------------

def save_raw(payload_bytes: bytes) -> Path:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    path = SAMPLES_DIR / f"cemaden_raw_{stamp}.json"
    parsed = json.loads(payload_bytes)
    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Parse alerts
# ---------------------------------------------------------------------------

def extract_alerts(parsed: Any) -> list[dict[str, Any]]:
    """Return the alert list regardless of whether the payload is a list or dict."""
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def append_log(entry: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")


def build_log_entry(
    run_number: int,
    alerts: list[dict[str, Any]],
    previous_codes: set[int] | None,
    error: str | None,
    raw_path: Path | None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append(f"[{now}] Run #{run_number}")

    if error:
        lines.append(f"  ERRO: {error}")
        return "\n".join(lines)

    current_codes = {int(a["cod_alerta"]) for a in alerts if "cod_alerta" in a}
    status_values = sorted({a.get("status") for a in alerts if "status" in a})
    nivel_counts: dict[str, int] = {}
    for a in alerts:
        nivel = a.get("nivel", "?")
        nivel_counts[nivel] = nivel_counts.get(nivel, 0) + 1

    lines.append(f"  Alertas ativos : {len(alerts)}")
    lines.append(f"  Status values  : {status_values}")
    lines.append(f"  Por nível      : {dict(sorted(nivel_counts.items()))}")

    if previous_codes is not None:
        novos = current_codes - previous_codes
        removidos = previous_codes - current_codes
        if novos:
            lines.append(f"  NOVOS          : {sorted(novos)}")
        else:
            lines.append(f"  Novos          : nenhum")
        if removidos:
            lines.append(f"  REMOVIDOS      : {sorted(removidos)}")
            # For each removed alert, note its last known status
            lines.append(f"  (ver rodada anterior para status dos removidos)")
        else:
            lines.append(f"  Removidos      : nenhum")
    else:
        lines.append(f"  (primeira rodada — sem comparação anterior)")

    if raw_path:
        lines.append(f"  JSON salvo em  : {raw_path.name}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------

def run_once(run_number: int, previous_codes: set[int] | None) -> set[int] | None:
    """
    Fetches, saves, logs. Returns the set of cod_alerta from this run
    (to be passed as previous_codes on the next run), or None on error.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{now}] Run #{run_number} — fetching...")

    try:
        payload_bytes = fetch_payload()
    except (HTTPError, URLError) as exc:
        msg = str(exc)
        print(f"  ERRO: {msg}")
        entry = build_log_entry(run_number, [], previous_codes, msg, None)
        append_log(entry)
        return previous_codes  # keep previous so next diff is still useful

    try:
        parsed = json.loads(payload_bytes)
        raw_path = save_raw(payload_bytes)
    except json.JSONDecodeError as exc:
        msg = f"JSON inválido: {exc}"
        print(f"  ERRO: {msg}")
        entry = build_log_entry(run_number, [], previous_codes, msg, None)
        append_log(entry)
        return previous_codes

    alerts = extract_alerts(parsed)
    current_codes = {int(a["cod_alerta"]) for a in alerts if "cod_alerta" in a}

    entry = build_log_entry(run_number, alerts, previous_codes, None, raw_path)
    append_log(entry)

    # Print compact summary to terminal
    print(entry)
    print(f"\n  Log atualizado: {LOG_FILE}")

    return current_codes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect CEMADEN wsAlertas2 payload.")
    parser.add_argument(
        "--loop",
        type=int,
        metavar="MINUTES",
        default=None,
        help="Repeat every N minutes until Ctrl+C. Omit for a single run.",
    )
    args = parser.parse_args()

    # Write a session header to the log
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    session_start = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    mode = f"loop a cada {args.loop} min" if args.loop else "execução única"
    append_log(f"\n{'='*60}")
    append_log(f"Sessão iniciada: {session_start} | Modo: {mode}")
    append_log(f"{'='*60}")

    if args.loop is None:
        run_once(1, None)
        return 0

    interval_seconds = args.loop * 60
    print(f"Loop mode: a cada {args.loop} min. Ctrl+C para parar.")
    print(f"Log em: {LOG_FILE}")

    run_count = 0
    previous_codes: set[int] | None = None
    try:
        while True:
            run_count += 1
            previous_codes = run_once(run_count, previous_codes)
            print(f"\n  Aguardando {args.loop} min... Ctrl+C para parar.")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        append_log(f"\nSessão encerrada após {run_count} rodada(s).")
        print(f"\n\nEncerrado após {run_count} rodada(s).")
        print(f"Log completo em: {LOG_FILE}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
