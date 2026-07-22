"""Shared ISO datetime parsing — domain invariant (UTC consistency).

Extracted from three copies (`alerta.py` `data_criacao`/`ult_atualizacao`,
`nasa_eonet.py` `_fix_mais_recente`) that each repeated the same rule: parse
an ISO 8601 string; if the result is naive (no tzinfo), assume UTC. See
wiki/decisions/utc-timestamps-consistency.md.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso_utc(valor: str) -> datetime:
    """Parses an ISO 8601 string; a naive result is assumed to be UTC.

    Raises ValueError (via `datetime.fromisoformat`) on unparseable input —
    callers decide whether that propagates or falls back.
    """
    resultado = datetime.fromisoformat(valor)
    if resultado.tzinfo is None:
        resultado = resultado.replace(tzinfo=timezone.utc)
    return resultado
