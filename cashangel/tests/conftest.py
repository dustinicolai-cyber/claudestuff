import os

import pytest


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    """Jeder Test bekommt einen leeren Datenordner; Engine und Konfig-Cache werden zurückgesetzt."""
    monkeypatch.setenv("CASHANGEL_HOME", str(tmp_path / "home"))
    from app import config, db
    config.konfig.cache_clear()
    db.engine.cache_clear()
    db.init_db()
    yield
    db.engine.cache_clear()
    config.konfig.cache_clear()
