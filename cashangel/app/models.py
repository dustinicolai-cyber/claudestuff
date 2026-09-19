"""Datenmodell von Cash Angel: Kontobewegungen, Kategorien, gelernte Zuordnungen, Abo-Entscheidungen."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Kategorie(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    schluessel: str = Field(index=True, unique=True)
    name: str
    art: str = "ausgabe"               # einnahme | ausgabe | umbuchung
    farbe: str = "#38bdf8"
    fix: bool = False                  # Fixkosten (Miete, Abos) vs. variable Ausgaben
    sortierung: int = 100
    aktiv: bool = True


class Bewegung(SQLModel, table=True):
    """Eine Zeile aus dem Kontoauszug. Kategorie und Person werden beim Import erkannt und lassen sich ändern."""
    id: Optional[int] = Field(default=None, primary_key=True)
    datum: date = Field(index=True)
    betrag: float                      # negativ = Ausgabe
    verwendungszweck: str = ""
    gegenkonto: str = ""
    gegen_iban: str = ""
    konto: str = ""                    # Name des Kontos (aus dem Import), z. B. „Gemeinschaftskonto“
    quelle_datei: str = ""
    fingerprint: str = Field(default="", index=True)
    partner: str = Field(default="", index=True)   # normalisierter Name für Abo-Erkennung und Gruppierung
    kategorie_id: Optional[int] = Field(default=None, foreign_key="kategorie.id", index=True)
    person: str = ""                   # bei Gehalt: wessen
    weg: str = "-"                     # regel:<id> | muster | gehalt | umbuchung | manuell | -
    ignoriert: bool = False
    notiz: str = ""
    importiert_am: datetime = Field(default_factory=datetime.now)


class Regel(SQLModel, table=True):
    """Gelernte Zuordnung: Partner/Muster → Kategorie (+ Person). Gewinnt vor den Standardmustern."""
    id: Optional[int] = Field(default=None, primary_key=True)
    muster: str = Field(index=True)
    kategorie_id: int = Field(foreign_key="kategorie.id")
    person: str = ""
    art: str = ""                      # einnahme | ausgabe | "" (beide Seiten)
    erstellt_am: datetime = Field(default_factory=datetime.now)
    treffer: int = 0


class AboStatus(SQLModel, table=True):
    """Entscheidung zu einem erkannten Abo: gekündigt (ab wann), kein Abo, Notiz."""
    id: Optional[int] = Field(default=None, primary_key=True)
    partner: str = Field(index=True, unique=True)
    status: str = "ok"                 # ok | gekuendigt | kein_abo
    notiz: str = ""
    name: str = ""                     # eigener Anbietername (überschreibt den erkannten)
    monatlich: Optional[float] = None  # eigener Monatsbetrag (überschreibt den erkannten)
    kategorie_id: Optional[int] = None # eigene Kategorie (überschreibt die erkannte)
    typ: str = ""                      # abo | vertrag | krankenkasse | depot | kredit | kein ("" = aus der Kategorie ableiten)
    geaendert_am: datetime = Field(default_factory=datetime.now)


class AboManuell(SQLModel, table=True):
    """Von Hand eingetragenes Abo oder Vertrag – z. B. wenn noch zu wenige Auszüge für die Erkennung da sind."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    betrag: float = 0.0
    intervall: str = "monatlich"       # monatlich | quartal | halbjahr | jaehrlich
    kategorie_id: Optional[int] = None
    typ: str = ""
    quelle_partner: str = ""           # aus den Zuordnungen übernommen: Schlüssel des Empfängers
    aktiv: bool = True
    erstellt_am: datetime = Field(default_factory=datetime.now)


class Geloescht(SQLModel, table=True):
    """Fingerabdrücke gelöschter Bewegungen – ein erneuter Import bringt sie nicht zurück."""
    id: Optional[int] = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)


class Einstellung(SQLModel, table=True):
    schluessel: str = Field(primary_key=True)
    wert: str = ""                     # JSON
