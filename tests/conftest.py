import pytest

from alertavida import database as db_module


@pytest.fixture(autouse=True)
def _guarda_db_path(tmp_path, monkeypatch):
    """Redireciona o banco para um tmp_path por padrão em todo teste.

    Guarda contra vazamento futuro: qualquer teste que acesse o banco sem
    apontar seu próprio caminho cai aqui em vez de tocar o arquivo real
    (issue #37). Desde a issue #22 o caminho é resolvido por `db_path()` a
    partir de `ALERTAVIDA_DB_PATH`, então a guarda seta a env var; testes que
    setam seu próprio caminho (ex.: db_temporario) sobrescrevem normalmente.
    """
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(tmp_path / "guarda.db"))


@pytest.fixture
def db_temporario(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv(db_module.ENV_DB_PATH, str(db_path))
    db_module.criar_banco()
    return db_path
