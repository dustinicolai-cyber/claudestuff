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
    import json
    import shutil
    from app import config, db
    # Die Servertests rechnen im §19-Modus. Das Testjahr 2025 ist im Auslieferungsstand regelbesteuert,
    # deshalb wird es hier bewusst auf Kleinunternehmer gestellt; die Regelbesteuerung hat eigene Tests.
    heim = tmp_path / "home"
    heim.mkdir(parents=True, exist_ok=True)
    ziel = heim / "steuerregeln.json"
    shutil.copy(config.DEFAULT_REGELN, ziel)
    daten = json.loads(ziel.read_text(encoding="utf-8"))
    daten["kleinunternehmer_je_jahr"] = {str(j): True for j in range(2020, 2031)}
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    config.regeln.cache_clear()
    db._engine = None
    db.init_db()
    yield
    db._engine = None
    config.regeln.cache_clear()


@pytest.fixture
def cfg():
    """Standardfall §19 für alle Jahre. Die Regelbesteuerung hat eigene Tests, die das Jahr gezielt umstellen."""
    from app import config
    r = dict(config.regeln())
    r["kleinunternehmer_je_jahr"] = {}
    return r


@pytest.fixture
def cfg_regel(cfg):
    """Regelbesteuert im Testjahr 2025: Netto ist Betriebsausgabe, Vorsteuer wird abgezogen."""
    r = dict(cfg)
    r["kleinunternehmer_je_jahr"] = {"2025": False}
    return r


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
