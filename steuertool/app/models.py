"""Datenmodell. Beträge immer Netto + USt-Betrag; Brutto ist abgeleitet, wird
aber mitgespeichert, damit Kontoauszug-Matching ohne Rechnen geht.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Beleg(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dateipfad: str
    original_name: str = ""
    sha256: str = Field(index=True, unique=True)
    importiert_am: datetime = Field(default_factory=datetime.now)
    quelle: str = "manuell"  # zugferd | pdf | ocr | manuell
    mime: str = ""
    herkunft: str = ""       # z.B. "upload", "mail:<absender>", "ordner"


class Kategorie(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    schluessel: str = Field(index=True, unique=True)
    name: str
    richtung: str = "ausgabe"          # einnahme | ausgabe
    eur_zeile: Optional[int] = None
    ustva_kennzahl: Optional[str] = None
    sonderfall: Optional[str] = None   # reverse_charge|bewirtung|gwg|fahrtkosten|homeoffice|privatanteil|geschenk|afa|privat
    aktiv: bool = True


class Buchung(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    beleg_id: Optional[int] = Field(default=None, foreign_key="beleg.id", index=True)
    datum: date = Field(index=True)
    richtung: str = "ausgabe"          # einnahme | ausgabe

    betrag_netto: float = 0.0
    ust_satz: float = 0.0
    ust_betrag: float = 0.0
    betrag_brutto: float = 0.0

    lieferant: str = ""
    beschreibung: str = ""
    rechnungsnummer: str = ""
    ust_idnr: str = ""

    kategorie_id: Optional[int] = Field(default=None, foreign_key="kategorie.id", index=True)
    eur_zeile: Optional[int] = None
    reverse_charge: bool = False

    status: str = "vorschlag"          # vorschlag | bestaetigt
    konfidenz: float = 0.0
    privat_verauslagt: bool = False    # bar/privat bezahlt – braucht keine Kontobewegung
    storniert: bool = False            # bestätigte Buchungen werden nie gelöscht, nur storniert

    # Nachvollziehbarkeit: welche Pipeline-Stufe, welche Rohfelder
    extraktion_stufe: str = "manuell"  # zugferd | pdf | ocr | manuell | kontoauszug
    extraktion_json: str = "{}"
    klassifizierung_weg: str = ""      # regel:<id> | ki:<modell> | manuell | -

    # Sonderfall-Metadaten (JSON): anlass, teilnehmer, km, tage, empfaenger, privatanteil_prozent
    meta_json: str = "{}"
    hinweise_json: str = "[]"

    erstellt_am: datetime = Field(default_factory=datetime.now)
    bestaetigt_am: Optional[datetime] = None

    @property
    def jahr(self) -> int:
        return self.datum.year

    @property
    def quartal(self) -> int:
        return (self.datum.month - 1) // 3 + 1


class Kontobewegung(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    datum: date = Field(index=True)
    betrag: float                      # negativ = Abgang
    verwendungszweck: str = ""
    gegenkonto: str = ""               # Name des Zahlungsempfängers/-pflichtigen
    gegen_iban: str = ""
    quelle_datei: str = ""
    fingerprint: str = Field(default="", index=True)  # zur Duplikatvermeidung
    buchung_id: Optional[int] = Field(default=None, foreign_key="buchung.id", index=True)
    ignoriert: bool = False            # z.B. Privatbuchungen auf gemischtem Konto


class Regel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    muster: str
    ist_regex: bool = False
    kategorie_id: int = Field(foreign_key="kategorie.id")
    prioritaet: int = 100              # kleiner = wichtiger
    erstellt_aus_korrektur: bool = False
    erstellt_am: datetime = Field(default_factory=datetime.now)
    treffer: int = 0


class Anlagegut(SQLModel, table=True):
    """Ein Wirtschaftsgut über der GWG-Grenze, das linear abgeschrieben wird."""
    id: Optional[int] = Field(default=None, primary_key=True)
    buchung_id: Optional[int] = Field(default=None, foreign_key="buchung.id")
    bezeichnung: str
    anschaffung: date
    anschaffungskosten: float          # bei §19: brutto
    nutzungsdauer_jahre: int = 3
    aktiv: bool = True


class MailFund(SQLModel, table=True):
    """Mails, die nur einen Link zur Rechnung enthalten: Liste „manuell holen"."""
    id: Optional[int] = Field(default=None, primary_key=True)
    absender: str
    datum: Optional[datetime] = None
    betreff: str = ""
    link: str = ""
    mail_id: str = Field(default="", index=True)
    art: str = "link"                  # link | vorschlag (Anhang, aber unbekannter Absender)
    status: str = "offen"              # offen | erledigt | ignoriert
    beleg_id: Optional[int] = None


class MailZustand(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    konto: str                         # imap:<host>/<user> oder emlx:<pfad>
    ordner: str
    letzte_uid: str = "0"
    zuletzt_gescannt: Optional[datetime] = None


class Fragebogen(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    jahr: int = Field(index=True)
    frage_key: str
    erledigt: bool = False
    notiz: str = ""


class DedupIgnoriert(SQLModel, table=True):
    """Paare, die der Nutzer als „sind unterschiedlich“ geprüft hat."""
    id: Optional[int] = Field(default=None, primary_key=True)
    a_id: int = Field(index=True)
    b_id: int = Field(index=True)


class Protokoll(SQLModel, table=True):
    """Nachvollziehbarkeit für Eingriffe: Zusammenführen, Stornieren, Privat verauslagt."""
    id: Optional[int] = Field(default=None, primary_key=True)
    zeitpunkt: datetime = Field(default_factory=datetime.now)
    aktion: str
    details: str = ""
    buchung_id: Optional[int] = None
