"""
Inspect the CEMADEN wsAlertas2 payload.

Exploratory tool: fetches the live feed once, saves the raw JSON to
data/samples/ with a UTC timestamp, and prints the schema of the response.

Run multiple times across different times of day to capture the feed in
different states (e.g. heavy rain vs quiet). Files accumulate so you can
diff them later.

Usage:
    python scripts/inspect_cemaden_payload.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENDPOINT = "https://painelalertas.cemaden.gov.br/wsAlertas2"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
TIMEOUT_SECONDS = 30

# Field-name fragments that hint at lifecycle/state semantics. Surfacing these
# is the whole point of this script: if any of them appear in the payload,
# AlertaResolvido / AlertaAtualizado can probably read them directly instead
# of inferring from absence across rounds.
LIFECYCLE_HINTS = (
    "valid", "expir", "fim", "atualiz", "update",
    "status", "ativo", "encerr", "vers", "modif", "cancel", "final",
)


def fetch_payload() -> bytes:
    """Single attempt, no retry — exploratory tooling, not production."""
    req = Request(ENDPOINT, headers={"User-Agent": "AlertaVida-Inspector/0.1"})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read()


def save_raw(payload_bytes: bytes) -> Path:
    """Pretty-print and save with a UTC timestamp. Returns the path written."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    path = SAMPLES_DIR / f"cemaden_raw_{stamp}.json"
    parsed = json.loads(payload_bytes)
    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def describe_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return f"str(len={len(value)})"
    if isinstance(value, list):
        return f"list(len={len(value)})"
    if isinstance(value, dict):
        return f"dict(keys={len(value)})"
    return type(value).__name__


def is_lifecycle_field(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in LIFECYCLE_HINTS)


def print_field_table(fields: dict[str, Any]) -> None:
    for key in sorted(fields.keys()):
        marker = "⚑" if is_lifecycle_field(key) else " "
        sample_repr = repr(fields[key])[:80]
        print(f"  {marker} {key:30s} {describe_value(fields[key]):20s} e.g. {sample_repr}")


def analyze_payload(parsed: Any) -> None:
    print("\n=== Top-level structure ===")
    print(f"Type: {describe_value(parsed)}")

    alerts: list[Any] | None = None
    if isinstance(parsed, list):
        alerts = parsed
    elif isinstance(parsed, dict):
        print("\nTop-level keys:")
        print_field_table(parsed)
        # Heuristic: first list-of-dicts value is treated as the alert collection.
        for value in parsed.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                alerts = value
                break

    if not alerts:
        print("\n!! No alert list detected. Inspect the saved file by hand.")
        return

    print(f"\n=== Alert list — {len(alerts)} item(s) ===")

    dict_items = [item for item in alerts if isinstance(item, dict)]
    if not dict_items:
        print("Items are not dicts — inspect manually.")
        return

    key_sets = [frozenset(item.keys()) for item in dict_items]
    union = set().union(*key_sets)
    intersection = set(key_sets[0])
    for s in key_sets[1:]:
        intersection &= s

    print(f"\nFields in ALL {len(dict_items)} items ({len(intersection)}):")
    for key in sorted(intersection):
        marker = "⚑" if is_lifecycle_field(key) else " "
        print(f"  {marker} {key}")

    sparse = union - intersection
    if sparse:
        print(f"\nFields in only SOME items ({len(sparse)}) "
              f"— candidates for Optional in the domain model:")
        for key in sorted(sparse):
            marker = "⚑" if is_lifecycle_field(key) else " "
            print(f"  {marker} {key}")
    else:
        print("\nAll items share the same field set.")

    print("\n=== Sample item (first in list) ===")
    print_field_table(dict_items[0])


def main() -> int:
    print(f"Fetching {ENDPOINT} ...")
    try:
        payload_bytes = fetch_payload()
    except HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    try:
        path = save_raw(payload_bytes)
    except json.JSONDecodeError as exc:
        print(f"Response is not valid JSON: {exc}", file=sys.stderr)
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        raw_path = SAMPLES_DIR / f"cemaden_raw_{stamp}.bin"
        raw_path.write_bytes(payload_bytes)
        print(f"Raw bytes saved to: {raw_path}", file=sys.stderr)
        return 2

    print(f"Saved: {path}")
    print(f"Size:  {len(payload_bytes):,} bytes")

    analyze_payload(json.loads(payload_bytes))

    print("\n⚑ = field name suggests lifecycle/state semantics. "
          "If any are flagged, they likely answer the AlertaResolvido / "
          "AlertaAtualizado question without needing inference.")
    print("\nRun again in a few hours to capture the feed in a different state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())