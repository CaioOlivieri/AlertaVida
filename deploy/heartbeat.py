"""Dead-man's switch for the collector (issue #141).

Run every 5 minutes by `alertavida-heartbeat.timer`. It measures what
matters — *did a round complete recently?* — not what is easy to measure
(*is the process alive?*): every successful round stamps
`visto_ultima_vez` on every alert of each source it collected, so
`MAX(visto_ultima_vez)` is the clock of the last completed round
(wiki/handoff-2026-09-06.md, section 9).

- Fresh (last round within `JANELA_FRESCA_MINUTOS`): ping the check URL.
- Stale, or the database unreadable: ping `<url>/fail` with the reason.
- The external service (healthchecks.io) alerts on a `/fail` ping and on
  the *absence* of pings — which covers the cases this script cannot report
  itself: VM down, network down, timer not running.

The check URL comes from `HEARTBEAT_URL` (EnvironmentFile
`/etc/alertavida/heartbeat.env`, never committed — anyone holding it can
send fake pings). Stdlib only; reads the database read-only.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DB_PATH_DEFAULT = Path("/var/lib/alertavida/alertavida.db")
# Rounds run every 5 min; 15 min = three missed rounds before alarming, so a
# single slow round (worst case ~268 s, see alertavida.service) never fires.
JANELA_FRESCA_MINUTOS = 15
TIMEOUT_SEGUNDOS = 10


def ultima_rodada(caminho_banco: Path) -> datetime | None:
    """`MAX(visto_ultima_vez)` as an aware datetime, or None if no alerts."""
    uri = f"file:{caminho_banco}?mode=ro"
    conexao = sqlite3.connect(uri, uri=True)
    try:
        valor = conexao.execute("SELECT MAX(visto_ultima_vez) FROM alertas").fetchone()[0]
    finally:
        conexao.close()
    if not valor:
        return None
    instante = datetime.fromisoformat(valor)
    return instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)


def avaliar(ultima: datetime | None, agora: datetime) -> tuple[bool, str]:
    """(saudável?, mensagem) — pure, so it can be tested without I/O."""
    if ultima is None:
        return False, "nenhuma rodada registrada (tabela alertas vazia)"
    idade = agora - ultima
    minutos = idade.total_seconds() / 60
    if idade <= timedelta(minutes=JANELA_FRESCA_MINUTOS):
        return True, f"ultima rodada ha {minutos:.1f} min"
    return False, f"ultima rodada ha {minutos:.1f} min (limite {JANELA_FRESCA_MINUTOS} min)"


def url_do_ping(base: str, saudavel: bool) -> str:
    if not base.startswith("https://"):
        raise ValueError("HEARTBEAT_URL precisa ser https://")
    return base.rstrip("/") + ("" if saudavel else "/fail")


def enviar(url: str, mensagem: str) -> None:
    pedido = Request(
        url,
        data=mensagem.encode("utf-8"),
        method="POST",
        headers={"User-Agent": "alertavida-heartbeat/1.0"},
    )
    with urlopen(pedido, timeout=TIMEOUT_SEGUNDOS) as resposta:  # noqa: S310 - https enforced
        resposta.read(1024)


def main() -> int:
    base = os.getenv("HEARTBEAT_URL", "").strip()
    if not base:
        print("HEARTBEAT_URL ausente — configure /etc/alertavida/heartbeat.env", file=sys.stderr)
        return 1
    caminho = Path(os.getenv("ALERTAVIDA_DB_PATH") or DB_PATH_DEFAULT)
    agora = datetime.now(timezone.utc)
    try:
        saudavel, mensagem = avaliar(ultima_rodada(caminho), agora)
    except sqlite3.Error as exc:
        saudavel, mensagem = False, f"banco ilegivel em {caminho}: {exc}"

    enviar(url_do_ping(base, saudavel), mensagem)
    estado = "OK" if saudavel else "FAIL"
    print(f"=== HEARTBEAT {estado}: {mensagem} ===")
    return 0 if saudavel else 1


if __name__ == "__main__":
    raise SystemExit(main())
