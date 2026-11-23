"""Testes de alertavida/bootstrap.py (issue #131)."""

import logging
from unittest.mock import patch

from alertavida.bootstrap import FORMATO_LOG, configurar_logging, fontes_producao
from alertavida.sources.cemaden import CemadenSource
from alertavida.sources.nasa_eonet import NasaEonetSource


def test_fontes_producao_na_ordem_de_coleta():
    fontes = fontes_producao()
    assert [type(f) for f in fontes] == [CemadenSource, NasaEonetSource]


def test_fontes_producao_devolve_instancias_novas():
    """Cada rodada recebe objetos próprios — nada compartilhado entre chamadas."""
    primeira, segunda = fontes_producao(), fontes_producao()
    assert all(a is not b for a, b in zip(primeira, segunda))


def test_configurar_logging_usa_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    with patch("alertavida.bootstrap.logging.basicConfig") as basic_config:
        configurar_logging()
    basic_config.assert_called_once_with(level="DEBUG", format=FORMATO_LOG)


def test_configurar_logging_default_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    with patch("alertavida.bootstrap.logging.basicConfig") as basic_config:
        configurar_logging()
    assert basic_config.call_args.kwargs["level"] == "INFO"
    assert logging.getLevelName("INFO") == logging.INFO
