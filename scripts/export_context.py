import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    ".ruff_cache",
    ".pytest_cache",
    "data",
    "reports",
}

VALID_EXTENSIONS = {".py", ".md", ".toml", ".json"}

SECURITY_FILES = {".env", ".env.keys", ".env.example"}
SECURITY_EXTENSIONS = {".db", ".sqlite3"}


def should_ignore(path: Path) -> bool:
    if path.is_dir():
        return path.name in IGNORED_DIRS
    name = path.name
    if name in SECURITY_FILES:
        return True
    if path.suffix.lower() in SECURITY_EXTENSIONS:
        return True
    if name.startswith(".env"):
        return True
    return False


def walk():
    results = []
    for root_dir, dirs, files in os.walk(ROOT):
        root_path = Path(root_dir)

        dirs[:] = [d for d in dirs if not should_ignore(root_path / d)]

        for file in files:
            fpath = root_path / file
            rel = fpath.relative_to(ROOT)

            if should_ignore(fpath):
                continue
            if fpath.suffix.lower() not in VALID_EXTENSIONS:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            results.append((rel.as_posix(), content))
    return results


def generate_report():
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime.now(tz)
    filename = now.strftime("contexto_%d-%m-%y_%H.%M.md")
    out_path = REPORTS_DIR / filename
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    files = walk()

    lines = [
        "# AlertaVida — Context Export\n",
        f"**Generated:** {now.strftime('%Y-%m-%d %H:%M')} BRT\n",
        f"**Files:** {len(files)}\n",
        "---\n",
    ]

    for rel_path, content in files:
        lines.append(f'<file path="{rel_path}">')
        lines.append(content)
        if not content.endswith("\n"):
            lines.append("")
        lines.append("</file>\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    out = generate_report()
    print(f"Context export: {out}")
