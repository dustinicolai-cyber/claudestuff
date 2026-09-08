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
    _spalten_nachziehen()
    with Session(engine()) as s:
        kategorien_synchronisieren(s)


def _spalten_nachziehen() -> None:
    """Neue Spalten in bestehenden Tabellen ergänzen (create_all ändert vorhandene Tabellen nicht).
    Bewusst ohne Migrationswerkzeug: nur ADD COLUMN mit Standardwert, nie destruktiv."""
    from sqlalchemy import inspect, text
    insp = inspect(engine())
    with engine().begin() as conn:
        for tabelle, spalten in SQLModel.metadata.tables.items():
            if tabelle not in insp.get_table_names():
                continue
            vorhanden = {c["name"] for c in insp.get_columns(tabelle)}
            for col in spalten.columns:
                if col.name in vorhanden:
                    continue
                typ = col.type.compile(engine().dialect)
                default = ""
                if col.default is not None and getattr(col.default, "arg", None) is not None and not callable(col.default.arg):
                    v = col.default.arg
                    default = f" DEFAULT {1 if v is True else 0 if v is False else repr(v)}"
                conn.execute(text(f'ALTER TABLE "{tabelle}" ADD COLUMN "{col.name}" {typ}{default}'))


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
