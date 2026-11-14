"""Shared ISO datetime parsing — domain invariant (UTC consistency).

Extracted from three copies (`alerta.py` `data_criacao`/`ult_atualizacao`,
`nasa_eonet.py` `_fix_mais_recente`) that each repeated the same rule: parse
an ISO 8601 string; if the result is naive (no tzinfo), assume UTC. See
wiki/decisions/utc-timestamps-consistency.md.
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo


def parse_iso_utc(valor: str, *, fuso_se_naive: tzinfo = timezone.utc) -> datetime:
    """Parses an ISO 8601 string and returns it as an aware UTC datetime.

    A naive result (no offset in the string) is read as `fuso_se_naive` —
    UTC by default. A source that publishes local wall-clock time without an
    offset passes its own zone (CEMADEN: UTC-3, issue #127); a string that
    carries its own offset is always respected. The result is normalized to
    UTC either way, so `.isoformat()` has one shape for every source — the
    detector compares that string against the stored snapshot.

    Raises ValueError (via `datetime.fromisoformat`) on unparseable input —
    callers decide whether that propagates or falls back.
    """
    resultado = datetime.fromisoformat(valor)
    if resultado.tzinfo is None:
        resultado = resultado.replace(tzinfo=fuso_se_naive)
    return resultado.astimezone(timezone.utc)
