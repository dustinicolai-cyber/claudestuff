from __future__ import annotations

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine, select

from . import config
from .models import Kategorie

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{config.db_path()}", connect_args={"check_same_thread": False})
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(engine())
    with Session(engine()) as s:
        kategorien_synchronisieren(s)


def kategorien_synchronisieren(s: Session) -> None:
    """Kategorienkatalog aus steuerregeln.json in die DB spiegeln (idempotent)."""
    vorhanden = {k.schluessel: k for k in s.exec(select(Kategorie)).all()}
    for d in config.regeln()["kategorien"]:
        k = vorhanden.get(d["schluessel"])
        if k is None:
            k = Kategorie(schluessel=d["schluessel"])
            s.add(k)
        k.name = d["name"]
        k.richtung = d["richtung"]
        k.eur_zeile = d.get("eur_zeile")
        k.ustva_kennzahl = d.get("ustva_kennzahl")
        k.sonderfall = d.get("sonderfall")
        k.aktiv = True
    s.commit()


@contextmanager
def session():
    with Session(engine()) as s:
        yield s


def get_session():
    with Session(engine()) as s:
        yield s
