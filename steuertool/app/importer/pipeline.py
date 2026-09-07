"""Import-Pipeline: Stufe 1 (E-Rechnung) → 2 (PDF-Text) → 3 (Vision-OCR) → 4 (Klassifizierung).
Die erste Stufe, die greift, gewinnt. Ergebnis ist immer ein Vorschlag, nie eine Buchung
ohne Bestätigung.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session, select

from .. import config
from ..models import Beleg, Buchung
from ..steuerlogik import betraege_vervollstaendigen, erkenne_reverse_charge, konfidenz_aus_feldern
from . import klassifizierung, ocr, pdftext, zugferd
from .textfelder import extrahiere_felder

BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".heic", ".webp", ".tif", ".tiff"}


@dataclass
class ImportErgebnis:
    status: str                      # neu | duplikat | fehler
    stufe: str = ""                  # zugferd | pdf | ocr | keine
    beleg_id: int | None = None
    buchung_id: int | None = None
    meldung: str = ""
    konfidenz: float = 0.0
    felder: dict = field(default_factory=dict)


def sha256(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def _sicherer_name(name: str) -> str:
    name = re.sub(r"[^\w.\-() ]+", "_", name, flags=re.UNICODE).strip() or "beleg"
    return name[:120]


def beleg_ablegen(daten: bytes, original_name: str, datum: date | None) -> Path:
    """Belegordner: ~/Steuertool/Belege/<Jahr>/<YYYY-MM-DD>_<name>"""
    jahr = (datum or date.today()).year
    ziel_dir = config.beleg_dir() / str(jahr)
    ziel_dir.mkdir(parents=True, exist_ok=True)
    praefix = (datum or date.today()).isoformat()
    ziel = ziel_dir / f"{praefix}_{_sicherer_name(original_name)}"
    n = 1
    while ziel.exists():
        ziel = ziel_dir / f"{praefix}_{n}_{_sicherer_name(original_name)}"
        n += 1
    ziel.write_bytes(daten)
    return ziel


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def extrahiere(daten: bytes, name: str, cfg: dict, ki_erlaubt: bool = True) -> tuple[str, dict, str]:
    """Stufen 1–3. Gibt (stufe, felder, volltext)."""
    endung = Path(name).suffix.lower()
    ist_pdf = endung == ".pdf" or daten[:5] == b"%PDF-"

    if endung == ".xml":
        f = zugferd.lese_erechnung_xml_datei(daten)
        if f:
            f["konfidenz"] = 1.0
            return "zugferd", f, ""

    if ist_pdf:
        f = zugferd.lese_erechnung(daten)
        if f:
            f["konfidenz"] = 1.0
            return "zugferd", f, ""
        text = pdftext.pdf_text(daten)
        if pdftext.hat_textebene(text):
            f = extrahiere_felder(text, cfg)
            f["konfidenz"] = konfidenz_aus_feldern(f)
            return "pdf", f, text
        if ki_erlaubt:
            bilder = pdftext.pdf_seiten_als_png(daten)
            f = ocr.lese_bilder(bilder, cfg)
            if f:
                return "ocr", f, f.get("volltext", "")
        return "keine", {"konfidenz": 0.0}, text

    if endung in BILD_ENDUNGEN and ki_erlaubt:
        f = ocr.lese_bilder([daten], cfg)
        if f:
            return "ocr", f, f.get("volltext", "")
    return "keine", {"konfidenz": 0.0}, ""


def importiere_datei(s: Session, daten: bytes, original_name: str, herkunft: str = "upload",
                     ki_erlaubt: bool = True) -> ImportErgebnis:
    cfg = config.regeln()
    h = sha256(daten)
    vorhanden = s.exec(select(Beleg).where(Beleg.sha256 == h)).first()
    if vorhanden:
        b = s.exec(select(Buchung).where(Buchung.beleg_id == vorhanden.id)).first()
        return ImportErgebnis(status="duplikat", beleg_id=vorhanden.id, buchung_id=b.id if b else None,
                              stufe=vorhanden.quelle, meldung=f"Bereits importiert am {vorhanden.importiert_am:%d.%m.%Y}")

    stufe, felder, text = extrahiere(daten, original_name, cfg, ki_erlaubt)
    datum = felder.get("datum") or date.today()
    pfad = beleg_ablegen(daten, original_name, felder.get("datum"))
    mime = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    beleg = Beleg(dateipfad=str(pfad), original_name=original_name, sha256=h,
                  quelle=stufe if stufe != "keine" else "manuell", mime=mime, herkunft=herkunft)
    s.add(beleg)
    s.commit()
    s.refresh(beleg)

    if stufe == "keine":
        b = Buchung(beleg_id=beleg.id, datum=datum, status="vorschlag", konfidenz=0.0,
                    extraktion_stufe="manuell", klassifizierung_weg="-",
                    extraktion_json=json.dumps({"hinweis": "keine Stufe hat gegriffen", "text": text[:2000]}, default=_json_default),
                    hinweise_json=json.dumps(["Keine automatische Erkennung möglich – bitte Felder von Hand ausfüllen."]))
        s.add(b)
        s.commit()
        s.refresh(b)
        return ImportErgebnis(status="neu", stufe="keine", beleg_id=beleg.id, buchung_id=b.id,
                              meldung="Abgelegt, aber keine Felder erkannt", konfidenz=0.0)

    netto, satz, ust, brutto = betraege_vervollstaendigen(
        felder.get("betrag_netto"), felder.get("ust_satz"), felder.get("ust_betrag"), felder.get("betrag_brutto"))
    lieferant = (felder.get("lieferant") or "").strip()
    rc, rc_gruende = erkenne_reverse_charge(text or felder.get("volltext", ""), felder.get("ust_idnr", ""), lieferant, ust, cfg)
    if felder.get("reverse_charge_hinweis") and ust == 0:
        rc = True
        if not rc_gruende:
            rc_gruende = ["Reverse-Charge-Kennzeichen (AE) im E-Rechnungs-XML" if stufe == "zugferd" else "Hinweis auf Umkehr der Steuerschuld"]
    if rc and satz == 0 and netto == 0 and brutto:
        netto = brutto

    richtung = "ausgabe"
    felder["richtung"] = richtung
    kategorie, weg, k_konf = klassifizierung.klassifiziere(s, {**felder, "lieferant": lieferant}, cfg, text) \
        if ki_erlaubt or True else (None, "-", 0.0)

    hinweise = list(rc_gruende)
    if brutto == 0:
        hinweise.append("Kein Betrag erkannt.")
    if not felder.get("datum"):
        hinweise.append("Kein Datum erkannt – heutiges Datum eingesetzt.")
    konf = round(min(felder.get("konfidenz", 0.0), 1.0) * 0.7 + k_konf * 0.3, 2)

    b = Buchung(
        beleg_id=beleg.id, datum=datum, richtung=richtung,
        betrag_netto=netto, ust_satz=satz, ust_betrag=ust, betrag_brutto=brutto,
        lieferant=lieferant, beschreibung=felder.get("beschreibung") or "",
        rechnungsnummer=felder.get("rechnungsnummer") or "", ust_idnr=felder.get("ust_idnr") or "",
        kategorie_id=kategorie.id if kategorie else None, eur_zeile=kategorie.eur_zeile if kategorie else None,
        reverse_charge=rc, status="vorschlag", konfidenz=konf,
        extraktion_stufe=stufe, klassifizierung_weg=weg,
        extraktion_json=json.dumps({k: v for k, v in felder.items() if k != "volltext"}, default=_json_default, ensure_ascii=False),
        hinweise_json=json.dumps(hinweise, ensure_ascii=False),
    )
    s.add(b)
    s.commit()
    s.refresh(b)
    return ImportErgebnis(status="neu", stufe=stufe, beleg_id=beleg.id, buchung_id=b.id, konfidenz=konf,
                          meldung=f"Stufe {stufe}, Kategorie {kategorie.name if kategorie else '–'} ({weg})", felder=felder)


def importiere_pfad(s: Session, pfad: Path, herkunft: str = "ordner", ki_erlaubt: bool = True) -> ImportErgebnis:
    return importiere_datei(s, pfad.read_bytes(), pfad.name, herkunft, ki_erlaubt)
