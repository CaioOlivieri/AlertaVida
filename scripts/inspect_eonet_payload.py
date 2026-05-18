"""
Inspect the NASA EONET v3 events API payload.

Exploratory tool for Camada 4 Parte C pre-implementation analysis.
Makes TWO requests in a single execution:
  - Requisição A: open events (status=open, limit=500)
  - Requisição B: 30-day history, open and closed (status=all, days=30, limit=500)

Saves raw JSON samples to data/samples/eonet/ (gitignored) with UTC timestamps and prints
a tabular report of the payload structure. NOT production code — this script is
discarded after Parte C design decisions are made.

Usage:
    python -m scripts.inspect_eonet_payload
"""
from __future__ import annotations

import json
import socket
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Force UTF-8 on Windows consoles (same pattern as monitor.py)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EONET_BASE_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples" / "eonet"
TIMEOUT_SECONDS = 30
USER_AGENT = "AlertaVida-Inspector/0.1 (https://github.com/CaioOlivieri/AlertaVida)"

# Brasil bounding box for scope classification
BRASIL_LAT_MIN = -34.0
BRASIL_LAT_MAX = 5.5
BRASIL_LON_MIN = -74.0
BRASIL_LON_MAX = -34.0

# All 13 EONET v3 category IDs (strings, not v2.1 integers)
EONET_CATEGORIES = (
    "drought",
    "dustHaze",
    "earthquakes",
    "floods",
    "landslides",
    "manmade",
    "seaLakeIce",
    "severeStorms",
    "snow",
    "tempExtremes",
    "volcanoes",
    "waterColor",
    "wildfires",
)


def _build_url(params: dict[str, str | int]) -> str:
    return f"{EONET_BASE_URL}?{urlencode(params)}"


def fetch_events(url: str) -> bytes:
    """Single attempt — exploratory tooling, not production."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read()


def save_fixture(payload_bytes: bytes, filename: str) -> tuple[Path, dict[str, Any]]:
    """Save JSON fixture and return (path, parsed dict).

    Writes raw bytes first so evidence survives a malformed payload.
    Then parses and overwrites with pretty-printed JSON for readability.
    Propagates json.JSONDecodeError / UnicodeDecodeError on bad input.
    """
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / filename
    path.write_bytes(payload_bytes)  # forensic copy — always survives
    parsed = json.loads(payload_bytes)  # raises on malformed; raw bytes already on disk
    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, parsed


def _first_geometry_point(geometries: list[dict[str, Any]]) -> tuple[float, float] | None:
    """Return (lon, lat) from the first Point geometry, or None."""
    for geom in geometries:
        if geom.get("type") == "Point":
            coords = geom.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                return float(coords[0]), float(coords[1])
    return None


def _is_within_brasil_bbox(lon: float, lat: float) -> bool:
    return (
        BRASIL_LAT_MIN <= lat <= BRASIL_LAT_MAX
        and BRASIL_LON_MIN <= lon <= BRASIL_LON_MAX
    )


def _category_ids(event: dict[str, Any]) -> list[str]:
    cats = event.get("categories", [])
    return [c["id"] for c in cats if isinstance(c, dict) and "id" in c]


def analyze_events(events: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """Compute all statistics for one batch of events. Returns a results dict."""
    total = len(events)

    # Category distribution
    cat_counts: dict[str, int] = {c: 0 for c in EONET_CATEGORIES}
    other_cats: dict[str, int] = {}
    for ev in events:
        for cat_id in _category_ids(ev):
            if cat_id in cat_counts:
                cat_counts[cat_id] += 1
            else:
                other_cats[cat_id] = other_cats.get(cat_id, 0) + 1

    # Closed status
    closed_count = sum(1 for ev in events if ev.get("closed") is not None)
    open_count = total - closed_count

    # Geometry analysis
    fixes_per_event: list[int] = []
    geom_type_counts: dict[str, int] = {}
    total_fixes = 0
    for ev in events:
        geoms = ev.get("geometry", [])
        n_fixes = len(geoms)
        fixes_per_event.append(n_fixes)
        total_fixes += n_fixes
        for geom in geoms:
            gtype = geom.get("type", "unknown")
            geom_type_counts[gtype] = geom_type_counts.get(gtype, 0) + 1

    single_fix = sum(1 for n in fixes_per_event if n == 1)
    multi_fix = sum(1 for n in fixes_per_event if n > 1)
    avg_fixes = statistics.mean(fixes_per_event) if fixes_per_event else 0.0
    median_fixes = statistics.median(fixes_per_event) if fixes_per_event else 0.0
    max_fixes = max(fixes_per_event) if fixes_per_event else 0

    # Magnitude analysis
    magnitude_events = 0
    magnitude_unit_counts: dict[str, int] = {}
    for ev in events:
        has_magnitude = False
        for geom in ev.get("geometry", []):
            mag_val = geom.get("magnitudeValue")
            if mag_val is not None:
                has_magnitude = True
                unit = geom.get("magnitudeUnit", "unknown") or "null"
                magnitude_unit_counts[unit] = magnitude_unit_counts.get(unit, 0) + 1
        if has_magnitude:
            magnitude_events += 1

    # Brasil bbox scope
    brasil_count = 0
    for ev in events:
        geoms = ev.get("geometry", [])
        pt = _first_geometry_point(geoms)
        if pt is not None and _is_within_brasil_bbox(pt[0], pt[1]):
            brasil_count += 1

    return {
        "label": label,
        "total": total,
        "cat_counts": cat_counts,
        "other_cats": other_cats,
        "closed_count": closed_count,
        "open_count": open_count,
        "single_fix": single_fix,
        "multi_fix": multi_fix,
        "total_fixes": total_fixes,
        "avg_fixes": avg_fixes,
        "median_fixes": median_fixes,
        "max_fixes": max_fixes,
        "geom_type_counts": geom_type_counts,
        "magnitude_events": magnitude_events,
        "magnitude_unit_counts": magnitude_unit_counts,
        "brasil_count": brasil_count,
    }


def print_report(stats_a: dict[str, Any], stats_b: dict[str, Any]) -> None:
    """Print the tabular analysis report to stdout."""
    print("\n" + "=" * 70)
    print("NASA EONET v3 — Payload Inspection Report")
    print("=" * 70)

    for stats in (stats_a, stats_b):
        label = stats["label"]
        total = stats["total"]
        print(f"\n--- {label} ---")
        print(f"  Total events: {total}")

    print("\n=== Distribuição por categoria ===")
    print(f"  {'Category ID':<20} {'open':>8} {'all_30d':>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8}")
    all_cats = set(list(stats_a["cat_counts"].keys()) + list(stats_b["cat_counts"].keys()))
    all_cats |= set(stats_a["other_cats"].keys()) | set(stats_b["other_cats"].keys())
    for cat in sorted(all_cats):
        count_a = stats_a["cat_counts"].get(cat, 0) + stats_a["other_cats"].get(cat, 0)
        count_b = stats_b["cat_counts"].get(cat, 0) + stats_b["other_cats"].get(cat, 0)
        marker = "" if cat in EONET_CATEGORIES else " (*)"
        print(f"  {cat + marker:<20} {count_a:>8} {count_b:>8}")

    print("\n=== Status closed/open ===")
    print(f"  {'Status':<15} {'open_req':>10} {'all_30d_req':>12}")
    print(f"  {'-'*15} {'-'*10} {'-'*12}")
    print(f"  {'open (closed=null)':<15} {stats_a['open_count']:>10} {stats_b['open_count']:>12}")
    print(f"  {'closed':<15} {stats_a['closed_count']:>10} {stats_b['closed_count']:>12}")

    print("\n=== Geometria temporal (fixes por event) ===")
    print(f"  {'Métrica':<25} {'open_req':>10} {'all_30d_req':>12}")
    print(f"  {'-'*25} {'-'*10} {'-'*12}")
    print(f"  {'events com 1 fix':<25} {stats_a['single_fix']:>10} {stats_b['single_fix']:>12}")
    print(f"  {'events com N>1 fixes':<25} {stats_a['multi_fix']:>10} {stats_b['multi_fix']:>12}")
    print(f"  {'total fixes':<25} {stats_a['total_fixes']:>10} {stats_b['total_fixes']:>12}")
    print(f"  {'média fixes/event':<25} {stats_a['avg_fixes']:>10.2f} {stats_b['avg_fixes']:>12.2f}")
    print(f"  {'mediana fixes/event':<25} {stats_a['median_fixes']:>10.1f} {stats_b['median_fixes']:>12.1f}")
    print(f"  {'máximo fixes/event':<25} {stats_a['max_fixes']:>10} {stats_b['max_fixes']:>12}")

    print("\n=== Geometria espacial (tipo do fix) ===")
    all_gtypes = set(stats_a["geom_type_counts"]) | set(stats_b["geom_type_counts"])
    print(f"  {'geometry.type':<15} {'open_req':>10} {'all_30d_req':>12}")
    print(f"  {'-'*15} {'-'*10} {'-'*12}")
    for gtype in sorted(all_gtypes):
        ca = stats_a["geom_type_counts"].get(gtype, 0)
        cb = stats_b["geom_type_counts"].get(gtype, 0)
        print(f"  {gtype:<15} {ca:>10} {cb:>12}")

    print("\n=== Magnitudes ===")
    print(f"  {'Métrica':<30} {'open_req':>10} {'all_30d_req':>12}")
    print(f"  {'-'*30} {'-'*10} {'-'*12}")
    print(f"  {'events com magnitude != null':<30} {stats_a['magnitude_events']:>10} {stats_b['magnitude_events']:>12}")
    all_units = set(stats_a["magnitude_unit_counts"]) | set(stats_b["magnitude_unit_counts"])
    for unit in sorted(all_units):
        ca = stats_a["magnitude_unit_counts"].get(unit, 0)
        cb = stats_b["magnitude_unit_counts"].get(unit, 0)
        print(f"  {('  unit=' + unit):<30} {ca:>10} {cb:>12}")

    print("\n=== Escopo Brasil (bbox simples, primeiro fix) ===")
    print(f"  bbox: lat [{BRASIL_LAT_MIN}, {BRASIL_LAT_MAX}] lon [{BRASIL_LON_MIN}, {BRASIL_LON_MAX}]")
    print(f"  {'Req':<15} {'eventos Brasil':>14} {'total':>8}")
    print(f"  {'-'*15} {'-'*14} {'-'*8}")
    print(f"  {'open':<15} {stats_a['brasil_count']:>14} {stats_a['total']:>8}")
    print(f"  {'all_30d':<15} {stats_b['brasil_count']:>14} {stats_b['total']:>8}")
    print()


def write_md_report(
    stats_a: dict[str, Any],
    stats_b: dict[str, Any],
    url_a: str,
    url_b: str,
    docs_dir: Path,
    capture_time: datetime,
) -> None:
    """Write analysis report to docs/analise_eonet_YYYY-MM-DD.md.

    Creates the file on the first call of the day; appends a new section on
    subsequent calls. Does not touch stdout — caller is responsible for that.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    date_str = capture_time.strftime("%Y-%m-%d")
    time_str = capture_time.strftime("%H:%M:%S")
    ts_str = capture_time.strftime("%Y-%m-%dT%H:%M:%S")
    md_path = docs_dir / f"analise_eonet_{date_str}.md"

    lines: list[str] = []
    lines.append(f"\n## Captura {time_str} UTC\n")
    lines.append(f"\n**URL Requisição A:** `{url_a}`  ")
    lines.append(f"\n**URL Requisição B:** `{url_b}`  ")
    lines.append(f"\n**Timestamp UTC:** {ts_str}\n")

    # Volume
    lines.append("\n### Volume\n")
    lines.append("\n| Requisição | Total eventos |")
    lines.append("\n|---|---|")
    lines.append(f"\n| open | {stats_a['total']} |")
    lines.append(f"\n| all_30d | {stats_b['total']} |")

    # Distribuição por categoria
    lines.append("\n\n### Distribuição por categoria\n")
    lines.append("\n| Categoria | open | all_30d | Fora do esperado |")
    lines.append("\n|---|---|---|---|")
    all_cats = (
        set(stats_a["cat_counts"])
        | set(stats_b["cat_counts"])
        | set(stats_a["other_cats"])
        | set(stats_b["other_cats"])
    )
    for cat in sorted(all_cats):
        count_a = stats_a["cat_counts"].get(cat, 0) + stats_a["other_cats"].get(cat, 0)
        count_b = stats_b["cat_counts"].get(cat, 0) + stats_b["other_cats"].get(cat, 0)
        fora = "sim" if cat not in EONET_CATEGORIES else "—"
        lines.append(f"\n| {cat} | {count_a} | {count_b} | {fora} |")

    # Status closed/open
    lines.append("\n\n### Status closed/open\n")
    lines.append("\n| Status | open_req | all_30d_req |")
    lines.append("\n|---|---|---|")
    lines.append(f"\n| open (closed=null) | {stats_a['open_count']} | {stats_b['open_count']} |")
    lines.append(f"\n| closed | {stats_a['closed_count']} | {stats_b['closed_count']} |")

    # Geometria temporal
    lines.append("\n\n### Geometria temporal\n")
    lines.append("\n| Métrica | open_req | all_30d_req |")
    lines.append("\n|---|---|---|")
    lines.append(f"\n| events com 1 fix | {stats_a['single_fix']} | {stats_b['single_fix']} |")
    lines.append(f"\n| events com N>1 fixes | {stats_a['multi_fix']} | {stats_b['multi_fix']} |")
    lines.append(f"\n| total fixes | {stats_a['total_fixes']} | {stats_b['total_fixes']} |")
    lines.append(f"\n| média fixes/event | {stats_a['avg_fixes']:.2f} | {stats_b['avg_fixes']:.2f} |")
    lines.append(f"\n| mediana fixes/event | {stats_a['median_fixes']:.1f} | {stats_b['median_fixes']:.1f} |")
    lines.append(f"\n| máximo fixes/event | {stats_a['max_fixes']} | {stats_b['max_fixes']} |")

    # Geometria espacial
    lines.append("\n\n### Geometria espacial\n")
    all_gtypes = set(stats_a["geom_type_counts"]) | set(stats_b["geom_type_counts"])
    lines.append("\n| geometry.type | open_req | all_30d_req |")
    lines.append("\n|---|---|---|")
    for gtype in sorted(all_gtypes):
        ca = stats_a["geom_type_counts"].get(gtype, 0)
        cb = stats_b["geom_type_counts"].get(gtype, 0)
        lines.append(f"\n| {gtype} | {ca} | {cb} |")

    # Magnitudes
    lines.append("\n\n### Magnitudes\n")
    lines.append("\n| Métrica | open_req | all_30d_req |")
    lines.append("\n|---|---|---|")
    lines.append(
        f"\n| events com magnitude != null"
        f" | {stats_a['magnitude_events']} | {stats_b['magnitude_events']} |"
    )
    all_units = set(stats_a["magnitude_unit_counts"]) | set(stats_b["magnitude_unit_counts"])
    for unit in sorted(all_units):
        ca = stats_a["magnitude_unit_counts"].get(unit, 0)
        cb = stats_b["magnitude_unit_counts"].get(unit, 0)
        lines.append(f"\n| unit={unit} | {ca} | {cb} |")

    # Escopo Brasil
    lines.append("\n\n### Escopo Brasil\n")
    lines.append(
        f"\n> bbox: lat [{BRASIL_LAT_MIN}, {BRASIL_LAT_MAX}]"
        f" lon [{BRASIL_LON_MIN}, {BRASIL_LON_MAX}]\n"
    )
    lines.append("\n| Req | Eventos Brasil | Total |")
    lines.append("\n|---|---|---|")
    lines.append(f"\n| open | {stats_a['brasil_count']} | {stats_a['total']} |")
    lines.append(f"\n| all_30d | {stats_b['brasil_count']} | {stats_b['total']} |")

    # Observações
    lines.append("\n\n### Observações\n")
    unexpected = set(stats_a["other_cats"]) | set(stats_b["other_cats"])
    if unexpected:
        lines.append("\nCategorias fora do conjunto esperado (`EONET_CATEGORIES`):\n")
        for cat in sorted(unexpected):
            lines.append(f"\n- `{cat}`")
    else:
        lines.append("\nNenhuma categoria fora do conjunto esperado.")
    lines.append("\n")

    section = "".join(lines)

    if md_path.exists():
        with md_path.open("a", encoding="utf-8") as f:
            f.write(section)
    else:
        header = f"# Análise empírica NASA EONET v3 — {date_str}\n"
        md_path.write_text(header + section, encoding="utf-8")

    print(f"  Relatório MD: {md_path}")


def _fetch_and_save(
    params: dict[str, str | int],
    filename: str,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one EONET endpoint, save fixture, return (events, stats)."""
    url = _build_url(params)
    print(f"Fetching {label}: {url}")
    try:
        payload_bytes = fetch_events(url)
    except HTTPError as exc:
        print(f"HTTP error ({label}): {exc.code} {exc.reason}", file=sys.stderr)
        raise
    except URLError as exc:
        print(f"Network error ({label}): {exc.reason}", file=sys.stderr)
        raise
    except socket.timeout as exc:
        print(f"Socket timeout ({label}): {exc}", file=sys.stderr)
        raise

    try:
        path, parsed = save_fixture(payload_bytes, filename)
    except json.JSONDecodeError as exc:
        print(f"Response is not valid JSON ({label}): {exc}", file=sys.stderr)
        raise
    except UnicodeDecodeError as exc:
        print(f"Unicode decode error ({label}): {exc}", file=sys.stderr)
        raise

    print(f"  Saved: {path} ({len(payload_bytes):,} bytes)")

    events: list[dict[str, Any]] = parsed.get("events", [])
    stats = analyze_events(events, label)
    return events, stats


def main() -> int:
    capture_time = datetime.now(timezone.utc)
    stamp = capture_time.strftime("%Y-%m-%dT%H%M%SZ")

    params_a: dict[str, str | int] = {"status": "open", "limit": 500}
    filename_a = f"eonet_open_{stamp}.json"
    url_a = _build_url(params_a)

    params_b: dict[str, str | int] = {"status": "all", "days": 30, "limit": 500}
    filename_b = f"eonet_all_30d_{stamp}.json"
    url_b = _build_url(params_b)

    try:
        _, stats_a = _fetch_and_save(params_a, filename_a, "Requisição A (open)")
        _, stats_b = _fetch_and_save(params_b, filename_b, "Requisição B (all 30d)")
    except (HTTPError, URLError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError):
        return 1

    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    print_report(stats_a, stats_b)
    write_md_report(stats_a, stats_b, url_a, url_b, docs_dir, capture_time)
    return 0


if __name__ == "__main__":
    sys.exit(main())
