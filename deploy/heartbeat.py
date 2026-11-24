"""Dead-man's switch for the collector — two signals (issues #141, #166).

Run every 5 minutes by `alertavida-heartbeat.timer`. It measures what
matters — *did rounds complete recently?* — from the `rodadas` table (#161),
one row per (round, source), `falha = 1` when that source's collection failed.

Two checks, because they need opposite responses (an alert is only worth
having if the receiver knows what to do):

- **coletor** (`HEARTBEAT_URL`, required): healthy when *any* round completed
  in the last `JANELA_COLETOR_MINUTOS`. A round whose sources all failed still
  proves the collector, host, network and database are alive. Failing means
  something of ours is down — act now.
- **CEMADEN** (`HEARTBEAT_URL_CEMADEN`, optional): healthy when CEMADEN was
  collected *successfully* in the last `JANELA_CEMADEN_MINUTOS`. Failing while
  the collector is healthy means the upstream is down — nothing to fix, but
  the open archive (#158) has a gap. Skipped with a log line when the URL is
  not configured.

Each check pings its own healthchecks.io URL (`<url>/fail` when unhealthy);
the service alerts on `/fail` and on the *absence* of pings, which covers what
this script cannot report itself (VM down, network down, timer not running).
One ping failing never stops the other.

The URLs come from `/etc/alertavida/heartbeat.env` (EnvironmentFile, never
committed — anyone holding one can send fake pings). Stdlib only; reads the
database read-only.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DB_PATH_DEFAULT = Path("/var/lib/alertavida/alertavida.db")
# Rounds run every 5 min; 15 min = three missed rounds before alarming, so a
# single slow round (worst case ~268 s, see alertavida.service) never fires.
JANELA_COLETOR_MINUTOS = 15
# Upstream blips of one or two rounds are normal (19 CEMADEN-only failed
# rounds in eight weeks of journal); 60 min tolerates them and still catches
# the measured 85-min outage of 2026-11-21 (#166).
JANELA_CEMADEN_MINUTOS = 60
TIMEOUT_SEGUNDOS = 10


@dataclass(frozen=True)
class Instantes:
    """What the database says, read once per run."""

    ultima_rodada: datetime | None
    ultima_coleta_cemaden: datetime | None


@dataclass(frozen=True)
class Resultado:
    nome: str
    saudavel: bool
    mensagem: str


def _aware(valor: str | None) -> datetime | None:
    if not valor:
        return None
    instante = datetime.fromisoformat(valor)
    return instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)


def ler_instantes(caminho_banco: Path) -> Instantes:
    """Latest round (any source) and latest successful CEMADEN collection.

    `ORDER BY iniciada_em DESC LIMIT 1` walks the primary key from the end
    instead of scanning the table. String order is time order here: every
    value is `datetime.isoformat()` of an aware UTC instant (`+00:00`), and a
    whole second without a fraction (`…:55+00:00`) still sorts before the
    same second with one (`…:55.000001+00:00`).
    """
    uri = f"file:{caminho_banco}?mode=ro"
    conexao = sqlite3.connect(uri, uri=True)
    try:
        rodada = conexao.execute(
            "SELECT iniciada_em FROM rodadas ORDER BY iniciada_em DESC LIMIT 1"
        ).fetchone()
        cemaden = conexao.execute(
            "SELECT iniciada_em FROM rodadas WHERE fonte = 'CEMADEN' AND falha = 0 "
            "ORDER BY iniciada_em DESC LIMIT 1"
        ).fetchone()
    finally:
        conexao.close()
    return Instantes(
        ultima_rodada=_aware(rodada[0] if rodada else None),
        ultima_coleta_cemaden=_aware(cemaden[0] if cemaden else None),
    )


def _minutos(agora: datetime, instante: datetime) -> float:
    return (agora - instante).total_seconds() / 60


def avaliar_coletor(ultima_rodada: datetime | None, agora: datetime) -> tuple[bool, str]:
    """(saudável?, mensagem) — pure."""
    if ultima_rodada is None:
        return False, "nenhuma rodada registrada (tabela rodadas vazia)"
    minutos = _minutos(agora, ultima_rodada)
    if agora - ultima_rodada <= timedelta(minutes=JANELA_COLETOR_MINUTOS):
        return True, f"ultima rodada ha {minutos:.1f} min"
    return False, f"ultima rodada ha {minutos:.1f} min (limite {JANELA_COLETOR_MINUTOS} min)"


def avaliar_cemaden(
    ultima_coleta: datetime | None, ultima_rodada: datetime | None, agora: datetime
) -> tuple[bool, str]:
    """(saudável?, mensagem) — pure. Says whose problem a failure is."""
    if ultima_coleta is not None and agora - ultima_coleta <= timedelta(
        minutes=JANELA_CEMADEN_MINUTOS
    ):
        return True, f"ultima coleta CEMADEN ha {_minutos(agora, ultima_coleta):.1f} min"
    desde = (
        "sem coleta bem-sucedida registrada"
        if ultima_coleta is None
        else f"desde {ultima_coleta:%Y-%m-%dT%H:%MZ} "
        f"(ha {_minutos(agora, ultima_coleta):.1f} min, limite {JANELA_CEMADEN_MINUTOS} min)"
    )
    coletor_vivo = ultima_rodada is not None and agora - ultima_rodada <= timedelta(
        minutes=JANELA_COLETOR_MINUTOS
    )
    if coletor_vivo:
        return False, f"CEMADEN falhando {desde}; o coletor esta rodando"
    return False, f"sem rodadas — ver o check do coletor; CEMADEN {desde}"


def url_do_ping(base: str, saudavel: bool) -> str:
    if not base.startswith("https://"):
        raise ValueError("URL de heartbeat precisa ser https://")
    return base.rstrip("/") + ("" if saudavel else "/fail")


def enviar(url: str, mensagem: str) -> None:
    pedido = Request(
        url,
        data=mensagem.encode("utf-8"),
        method="POST",
        headers={"User-Agent": "alertavida-heartbeat/2.0"},
    )
    with urlopen(pedido, timeout=TIMEOUT_SEGUNDOS) as resposta:  # noqa: S310 - https enforced
        resposta.read(1024)


def avaliar(instantes: Instantes | None, erro: str | None, agora: datetime) -> list[Resultado]:
    """Both checks. `erro` (database unreadable, table missing) fails both."""
    if instantes is None:
        motivo = erro or "banco ilegivel"
        return [Resultado("coletor", False, motivo), Resultado("CEMADEN", False, motivo)]
    return [
        Resultado("coletor", *avaliar_coletor(instantes.ultima_rodada, agora)),
        Resultado(
            "CEMADEN",
            *avaliar_cemaden(instantes.ultima_coleta_cemaden, instantes.ultima_rodada, agora),
        ),
    ]


def main() -> int:
    urls = {
        "coletor": os.getenv("HEARTBEAT_URL", "").strip(),
        "CEMADEN": os.getenv("HEARTBEAT_URL_CEMADEN", "").strip(),
    }
    if not urls["coletor"]:
        print("HEARTBEAT_URL ausente — configure /etc/alertavida/heartbeat.env", file=sys.stderr)
        return 1
    caminho = Path(os.getenv("ALERTAVIDA_DB_PATH") or DB_PATH_DEFAULT)
    agora = datetime.now(timezone.utc)
    try:
        instantes: Instantes | None = ler_instantes(caminho)
        erro = None
    except sqlite3.Error as exc:
        instantes, erro = None, f"banco ilegivel em {caminho}: {exc}"

    tudo_certo = True
    for resultado in avaliar(instantes, erro, agora):
        base = urls[resultado.nome]
        if not base:
            print(f"=== HEARTBEAT {resultado.nome} PULADO: URL nao configurada ===")
            continue
        estado = "OK" if resultado.saudavel else "FAIL"
        print(f"=== HEARTBEAT {resultado.nome} {estado}: {resultado.mensagem} ===")
        tudo_certo = tudo_certo and resultado.saudavel
        try:
            enviar(url_do_ping(base, resultado.saudavel), resultado.mensagem)
        except (OSError, ValueError) as exc:
            # One ping failing must not stop the other; healthchecks.io alerts
            # on the missing ping anyway.
            print(f"ping {resultado.nome} falhou: {exc}", file=sys.stderr)
            tudo_certo = False
    return 0 if tudo_certo else 1


if __name__ == "__main__":
    raise SystemExit(main())
