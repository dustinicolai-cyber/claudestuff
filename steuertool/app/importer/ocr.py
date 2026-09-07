"""Stufe 3: Bilder und gescannte PDFs über das lokale Vision-Modell.
Das Schema ist fest vorgegeben, Ollama läuft im JSON-Modus, fehlende Felder
bleiben null. Die Konfidenz wird aus der Vollständigkeit abgeleitet.
"""
from __future__ import annotations

from datetime import date

from .. import ollama
from ..steuerlogik import konfidenz_aus_feldern
from .textfelder import parse_betrag, parse_datum

SCHEMA = {
    "lieferant": "string|null",
    "rechnungsnummer": "string|null",
    "datum": "YYYY-MM-DD|null",
    "betrag_netto": "number|null",
    "ust_satz": "number|null",
    "ust_betrag": "number|null",
    "betrag_brutto": "number|null",
    "ust_idnr": "string|null",
    "reverse_charge": "boolean",
    "beschreibung": "string|null",
    "volltext": "string|null",
}

SYSTEM = (
    "Du liest deutsche und englische Rechnungen und Quittungen. Antworte ausschließlich mit einem JSON-Objekt "
    "exakt nach diesem Schema, ohne weitere Felder: " + str(SCHEMA).replace("'", '"') +
    " Beträge als Zahl mit Punkt als Dezimaltrenner. Wenn ein Feld nicht sicher lesbar ist: null. "
    "reverse_charge ist true, wenn die Steuerschuld auf den Leistungsempfänger übergeht (Reverse Charge, §13b, "
    "VAT reverse charged) oder eine ausländische USt-IdNr ohne deutschen USt-Ausweis steht. "
    "volltext: der erkennbare Text des Belegs, gekürzt auf 1500 Zeichen."
)


def _zahl(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return parse_betrag(str(v).replace("€", "").replace("EUR", ""))


def _datum(v) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return parse_datum(str(v))


def lese_bilder(bilder: list[bytes], cfg: dict) -> dict | None:
    """Vision-Modell befragen. None, wenn Ollama fehlt oder nichts Brauchbares zurückkommt."""
    if not bilder:
        return None
    antwort = ollama.chat_json(cfg, cfg["ollama"]["vision_modell"], SYSTEM,
                               "Extrahiere die Felder aus diesem Beleg.", bilder)
    if not isinstance(antwort, dict):
        return None
    felder = {
        "lieferant": (antwort.get("lieferant") or "").strip() if isinstance(antwort.get("lieferant"), str) else "",
        "rechnungsnummer": str(antwort.get("rechnungsnummer") or "").strip(),
        "datum": _datum(antwort.get("datum")),
        "betrag_netto": _zahl(antwort.get("betrag_netto")),
        "ust_satz": _zahl(antwort.get("ust_satz")),
        "ust_betrag": _zahl(antwort.get("ust_betrag")),
        "betrag_brutto": _zahl(antwort.get("betrag_brutto")),
        "ust_idnr": str(antwort.get("ust_idnr") or "").replace(" ", "").upper(),
        "reverse_charge_hinweis": bool(antwort.get("reverse_charge")),
        "beschreibung": str(antwort.get("beschreibung") or "").strip(),
        "volltext": str(antwort.get("volltext") or ""),
        "modell": cfg["ollama"]["vision_modell"],
    }
    if felder["betrag_brutto"] is None and felder["betrag_netto"] is None:
        return None
    felder["konfidenz"] = min(0.85, konfidenz_aus_feldern(felder))  # OCR nie über 0.85
    return felder
