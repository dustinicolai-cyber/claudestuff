"""Stufe 4: Kategorie und EÜR-Zeile. Erst Regelwerk, nur dann Textmodell."""
from __future__ import annotations

from sqlmodel import Session, select

from .. import ollama, regeln, steuerlogik
from ..models import Kategorie


def klassifiziere(s: Session, felder: dict, cfg: dict, text: str = "") -> tuple[Kategorie | None, str, float]:
    """(Kategorie, Weg, Konfidenz). Weg: 'regel:<id>' | 'ki:<modell>' | 'fallback'."""
    lieferant = felder.get("lieferant") or ""
    regel = regeln.passende_regel(s, lieferant, felder.get("beschreibung") or "")
    if regel:
        regel.treffer += 1
        s.add(regel)
        s.commit()
        k = s.get(Kategorie, regel.kategorie_id)
        return k, f"regel:{regel.id}", 0.95

    kategorien = s.exec(select(Kategorie).where(Kategorie.aktiv == True)).all()  # noqa: E712
    fa_schluessel, _ = steuerlogik.erkenne_finanzamt(lieferant, felder.get("beschreibung") or "", felder.get("richtung") or "ausgabe", cfg)
    if fa_schluessel:
        k = next((k for k in kategorien if k.schluessel == fa_schluessel), None)
        if k:
            return k, "finanzamt", 0.85
    if felder.get("richtung") == "einnahme":
        k = next((k for k in kategorien if k.schluessel == "einnahmen"), None)
        return k, "richtung", 0.8

    liste = "\n".join(f"- {k.schluessel}: {k.name}" for k in kategorien if k.richtung == "ausgabe")
    system = (
        "Du ordnest Belege eines freiberuflichen Designers (Kleinunternehmer, Deutschland) einer Kategorie zu. "
        "Antworte nur mit JSON: {\"kategorie\": \"<schluessel>\", \"begruendung\": \"<kurz>\"}. "
        "Erlaubte Schlüssel:\n" + liste
    )
    prompt = (
        f"Lieferant: {lieferant}\nBeschreibung: {felder.get('beschreibung') or ''}\n"
        f"Betrag brutto: {felder.get('betrag_brutto')}\nNetto: {felder.get('betrag_netto')}\n"
        f"Belegtext (Auszug):\n{(text or '')[:1500]}"
    )
    antwort = ollama.chat_json(cfg, cfg["ollama"]["text_modell"], system, prompt)
    if isinstance(antwort, dict):
        schluessel = str(antwort.get("kategorie", "")).strip().lower()
        k = next((k for k in kategorien if k.schluessel == schluessel), None)
        if k:
            return k, f"ki:{cfg['ollama']['text_modell']}", 0.6

    k = next((k for k in kategorien if k.schluessel == "sonstige"), None)
    return k, "fallback", 0.2
