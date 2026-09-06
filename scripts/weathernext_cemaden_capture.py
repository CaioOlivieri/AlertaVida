"""High-frequency raw CEMADEN capture, gated by the surge-watch flag (issue #70).

Companion to `scripts/weathernext_surge_watch.py`. That script writes
`watch_mode` into the daily artifact; this one reads it and, only while
`watch_mode` is true, fetches the CEMADEN painel and archives the RAW payload
(no domain parsing) into `data/weathernext_cemaden_captures/`. Objective:
several distinct raw snapshots of the SAME municipality while a surge is
predicted, for the centroide-vs-ponto-de-risco discriminator
([[projects/layer-5-correlation]], Round 2) — the production ingestion path
(`ingestion/orquestrador.py`) only ever persists the CURRENT parsed `Alerta`
per `(fonte, cod_alerta)`, overwriting on every update; it cannot reconstruct
how a given alert's coordinates moved across successive CEMADEN payloads.

Deliberately outside the ingestion pipeline: reuses `fetch_com_retry` +
`parse_json` from `sources/_http.py` (transport + JSON decode only — the same
retry/backoff policy CemadenSource itself uses, invariant discipline
unchanged) but never calls `CemadenSource._montar_alerta` or touches
`domain/correlacao.py`. Nothing here is user-facing.

When `watch_mode` is false (or the artifact is missing/unreadable), this
script is a fast no-op — no network call at all, so an always-on timer
costs nothing outside an actual surge.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from alertavida.domain.enums import FonteDado
from alertavida.sources._http import fetch_com_retry, opener_padrao, parse_json
from alertavida.sources.base import FalhaDeColeta
from alertavida.sources.cemaden import URL_CEMADEN, CemadenSource
from scripts.weathernext_surge_watch import artifact_path

logger = logging.getLogger(__name__)

CAPTURE_DIR_DEFAULT: Final[Path] = (
    Path(__file__).resolve().parent.parent / "data" / "weathernext_cemaden_captures"
)
ENV_CAPTURE_DIR: Final[str] = "ALERTAVIDA_WEATHERNEXT_CAPTURE_DIR"

# Mesmo padrão de deploy/backup.py (retenção por mtime) — hygiene, não
# requisito da issue: uma vigilância que fica ligada por dias em cadência de
# minutos acumula muitos arquivos pequenos.
RETENTION_DAYS_DEFAULT: Final[int] = 30
ENV_RETENTION_DAYS: Final[str] = "ALERTAVIDA_WEATHERNEXT_CAPTURE_RETENTION_DAYS"


def capture_dir() -> Path:
    """Resolve o diretório de captura, mesma convenção de `database.db_path()`."""
    valor = os.getenv(ENV_CAPTURE_DIR)
    if valor is None or not valor.strip():
        return CAPTURE_DIR_DEFAULT
    return Path(valor)


def em_modo_vigilancia() -> bool:
    """Lê `watch_mode` do artefato diário do surge watch.

    Artefato ausente ou ilegível -> False, sem levantar: o job diário pode
    simplesmente não ter rodado ainda, e isso não é falha desta captura.
    """
    caminho = artifact_path()
    if not caminho.exists():
        return False
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Artefato %s ilegível; tratando como fora de vigilância.", caminho)
        return False
    return bool(dados.get("watch_mode", False))


def capturar_payload_bruto() -> Path:
    """Busca o payload CRU do CEMADEN e grava com timestamp. Sem `_montar_alerta`."""
    raw = fetch_com_retry(
        URL_CEMADEN,
        fonte=FonteDado.CEMADEN,
        opener=opener_padrao,
        user_agent=CemadenSource.USER_AGENT,
    )
    payload = parse_json(raw, fonte=FonteDado.CEMADEN)

    destino_dir = capture_dir()
    destino_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = destino_dir / f"cemaden_raw_{timestamp}.json"
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def podar_capturas_antigas(diretorio: Path, dias_retencao: int) -> list[Path]:
    """Mesma lógica de `deploy/backup.py::podar_backups_antigos`, por mtime."""
    limite = datetime.now(timezone.utc).timestamp() - dias_retencao * 86400
    removidos = []
    for caminho in diretorio.glob("cemaden_raw_*.json"):
        if caminho.stat().st_mtime < limite:
            caminho.unlink()
            removidos.append(caminho)
    return removidos


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not em_modo_vigilancia():
        logger.info("Fora de modo vigilância (watch_mode=false ou artefato ausente); nada a fazer.")
        return 0

    try:
        destino = capturar_payload_bruto()
    except FalhaDeColeta as exc:
        logger.error("Falha ao capturar payload CEMADEN: %s", exc.causa)
        return 1

    logger.info("Captura gravada em %s", destino)

    dias_retencao = int(os.getenv(ENV_RETENTION_DAYS, str(RETENTION_DAYS_DEFAULT)))
    for removido in podar_capturas_antigas(capture_dir(), dias_retencao):
        logger.info("Captura expirada removida: %s", removido)

    return 0


if __name__ == "__main__":
    sys.exit(main())
