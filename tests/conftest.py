import pytest

from alertavida import database as db_module


@pytest.fixture(autouse=True)
def _guarda_db_path(tmp_path, monkeypatch):
    """Redireciona DB_PATH para um tmp_path por padrão em todo teste.

    Guarda contra vazamento futuro: qualquer teste que acesse o banco sem
    fazer patch/monkeypatch próprio de DB_PATH cai aqui em vez de tocar o
    arquivo real (issue #37). Testes que já fazem seu próprio monkeypatch
    de DB_PATH (ex.: db_temporario) sobrescrevem este valor normalmente.
    """
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "guarda.db")


@pytest.fixture
def db_temporario(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.criar_banco()
    return db_path
