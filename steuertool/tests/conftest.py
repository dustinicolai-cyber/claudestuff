import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isoliertes_home(tmp_path, monkeypatch):
    """Jeder Test bekommt ein eigenes STEUERTOOL_HOME mit frischer DB."""
    monkeypatch.setenv("STEUERTOOL_HOME", str(tmp_path / "home"))
    from app import config, db
    config.regeln.cache_clear()
    db._engine = None
    db.init_db()
    yield
    db._engine = None
    config.regeln.cache_clear()


@pytest.fixture
def cfg():
    from app import config
    return config.regeln()


@pytest.fixture
def session():
    from app.db import engine
    from sqlmodel import Session
    with Session(engine()) as s:
        yield s


@pytest.fixture
def kats(session):
    from sqlmodel import select
    from app.models import Kategorie
    return {k.schluessel: k for k in session.exec(select(Kategorie)).all()}
