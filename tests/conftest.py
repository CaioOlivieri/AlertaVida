import pytest

import alertavida.events as events_module
from alertavida import database as db_module


@pytest.fixture
def db_temporario(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(events_module, "DB_PATH", db_path)
    db_module.criar_banco()
    return db_path
