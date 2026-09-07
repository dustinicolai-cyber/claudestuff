"""Regelwerk: Lieferantenmuster → Kategorie. Prüft vor jeder KI. Jede manuelle
Korrektur erzeugt eine neue Regel (oder schärft die vorhandene).
"""
from __future__ import annotations

import re

from sqlmodel import Session, select

from .models import Regel


def passende_regel(s: Session, lieferant: str, beschreibung: str = "") -> Regel | None:
    text = f"{lieferant} {beschreibung}".strip().lower()
    if not text:
        return None
    regeln = s.exec(select(Regel).order_by(Regel.prioritaet, Regel.id)).all()
    for r in regeln:
        if r.ist_regex:
            try:
                if re.search(r.muster, text, re.I):
                    return r
            except re.error:
                continue
        elif r.muster.lower() in text:
            return r
    return None


def _muster_aus_lieferant(lieferant: str) -> str:
    """„Adobe Systems Software Ireland Ltd“ → „adobe systems“: die ersten zwei aussagekräftigen Wörter."""
    woerter = [w for w in re.split(r"[\s,.*]+", lieferant.lower()) if len(w) > 2 and w not in
               ("gmbh", "ltd", "inc", "llc", "the", "und", "and", "co", "kg", "ag", "ug", "limited", "ireland")]
    return " ".join(woerter[:2]) if woerter else lieferant.lower().strip()


def regel_aus_korrektur(s: Session, lieferant: str, kategorie_id: int) -> Regel | None:
    """Nach einer Nutzerkorrektur: Regel anlegen oder bestehende auf die neue Kategorie ziehen."""
    muster = _muster_aus_lieferant(lieferant)
    if len(muster) < 3:
        return None
    vorhanden = s.exec(select(Regel).where(Regel.muster == muster, Regel.ist_regex == False)).first()  # noqa: E712
    if vorhanden:
        vorhanden.kategorie_id = kategorie_id
        vorhanden.erstellt_aus_korrektur = True
        vorhanden.prioritaet = min(vorhanden.prioritaet, 50)
        s.add(vorhanden)
        s.commit()
        return vorhanden
    r = Regel(muster=muster, kategorie_id=kategorie_id, prioritaet=50, erstellt_aus_korrektur=True)
    s.add(r)
    s.commit()
    s.refresh(r)
    return r
