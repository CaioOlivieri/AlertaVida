"""Testes de `parse_iso_utc` — domain/tempo.py."""

from datetime import datetime, timedelta, timezone

import pytest

from alertavida.domain.tempo import parse_iso_utc

BRASILIA = timezone(timedelta(hours=-3))


def test_naive_e_lido_como_utc_por_padrao() -> None:
    assert parse_iso_utc("2026-04-29T10:00:00") == datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc)


def test_naive_e_lido_no_fuso_informado_e_convertido_para_utc() -> None:
    resultado = parse_iso_utc("2026-04-29 10:00:00", fuso_se_naive=BRASILIA)
    assert resultado == datetime(2026, 4, 29, 13, 0, tzinfo=timezone.utc)
    assert resultado.utcoffset() == timedelta(0)


def test_offset_explicito_vence_o_fuso_informado() -> None:
    resultado = parse_iso_utc("2026-04-29T10:00:00+00:00", fuso_se_naive=BRASILIA)
    assert resultado == datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc)


def test_resultado_e_sempre_normalizado_para_utc() -> None:
    """Uma forma só de `.isoformat()` para toda fonte — o detector compara
    essa string contra o snapshot gravado."""
    resultado = parse_iso_utc("2026-04-29T10:00:00-03:00")
    assert resultado.isoformat() == "2026-04-29T13:00:00+00:00"


def test_sufixo_z_do_eonet_continua_igual() -> None:
    assert parse_iso_utc("2026-04-29T10:00:00Z").isoformat() == "2026-04-29T10:00:00+00:00"


def test_string_invalida_levanta_value_error() -> None:
    with pytest.raises(ValueError):
        parse_iso_utc("não é data")
