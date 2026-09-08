"""Buchung ↔ Kontobewegung: Betrag exakt, Datum ±N Tage (Konfiguration)."""
from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from . import config
from .importer.kontoauszug import Bewegung
from .models import Buchung, DedupIgnoriert, Kontobewegung


def kontobewegungen_speichern(s: Session, bewegungen: list[Bewegung], quelle: str) -> tuple[int, int]:
    """Gibt (neu, duplikate)."""
    neu = dup = 0
    for bw in bewegungen:
        fp = bw.fingerprint()
        if s.exec(select(Kontobewegung).where(Kontobewegung.fingerprint == fp)).first():
            dup += 1
            continue
        s.add(Kontobewegung(datum=bw.datum, betrag=bw.betrag, verwendungszweck=bw.verwendungszweck,
                            gegenkonto=bw.gegenkonto, gegen_iban=bw.gegen_iban, quelle_datei=quelle, fingerprint=fp))
        neu += 1
    s.commit()
    return neu, dup


def _passt(b: Buchung, k: Kontobewegung, toleranz: int) -> bool:
    if b.richtung == "ausgabe" and k.betrag >= 0:
        return False
    if b.richtung == "einnahme" and k.betrag <= 0:
        return False
    if abs(abs(k.betrag) - abs(b.betrag_brutto)) > 0.005:
        return False
    return abs((k.datum - b.datum).days) <= toleranz


def matche(s: Session) -> int:
    """Automatisches Matching aller offenen Paare. Bei Mehrdeutigkeit nichts zuordnen."""
    toleranz = int(config.regeln().get("matching_tage_toleranz", 5))
    offen_k = s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id == None, Kontobewegung.ignoriert == False)).all()  # noqa: E711,E712
    belegt = {k.buchung_id for k in s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id != None)).all()}  # noqa: E711
    offen_b = [b for b in s.exec(select(Buchung)).all() if b.id not in belegt and b.betrag_brutto and not b.storniert]
    treffer = 0
    for k in offen_k:
        kandidaten = [b for b in offen_b if _passt(b, k, toleranz)]
        if len(kandidaten) == 1:
            b = kandidaten[0]
            k.buchung_id = b.id
            offen_b.remove(b)
            s.add(k)
            treffer += 1
        elif len(kandidaten) > 1:
            # nächstes Datum gewinnt nur bei eindeutigem Abstand
            kandidaten.sort(key=lambda b: abs((k.datum - b.datum).days))
            if abs((k.datum - kandidaten[0].datum).days) < abs((k.datum - kandidaten[1].datum).days):
                b = kandidaten[0]
                k.buchung_id = b.id
                offen_b.remove(b)
                s.add(k)
                treffer += 1
    s.commit()
    return treffer


def kandidaten_fuer(s: Session, k: Kontobewegung, toleranz_tage: int = 30) -> list[Buchung]:
    """Manuelle Zuordnung: Buchungen mit gleichem Betrag in weitem Fenster, dann nach Datum."""
    belegt = {x.buchung_id for x in s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id != None)).all()}  # noqa: E711
    alle = [b for b in s.exec(select(Buchung)).all() if b.id not in belegt]
    exakt = [b for b in alle if abs(abs(k.betrag) - b.betrag_brutto) < 0.005 and abs((k.datum - b.datum).days) <= toleranz_tage]
    exakt.sort(key=lambda b: abs((k.datum - b.datum).days))
    return exakt[:10]


def offene_punkte(s: Session) -> dict:
    """Beleg fehlt / Kontobewegung fehlt / mögliche Doppelbuchung."""
    ohne_beleg = s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id == None, Kontobewegung.ignoriert == False)  # noqa: E711,E712
                        .order_by(Kontobewegung.datum.desc())).all()
    belegt = {k.buchung_id for k in s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id != None)).all()}  # noqa: E711
    buchungen = [b for b in s.exec(select(Buchung).order_by(Buchung.datum.desc())).all() if not b.storniert]
    ohne_konto = [b for b in buchungen if b.id not in belegt and b.betrag_brutto and not b.privat_verauslagt]
    geprueft = {(min(x.a_id, x.b_id), max(x.a_id, x.b_id)) for x in s.exec(select(DedupIgnoriert)).all()}
    # Doppelbuchungen: gleicher Lieferant, gleicher Bruttobetrag, ±3 Tage oder gleiche Rechnungsnummer
    doppel: list[tuple[Buchung, Buchung]] = []
    for i, a in enumerate(buchungen):
        for b in buchungen[i + 1:]:
            if (min(a.id, b.id), max(a.id, b.id)) in geprueft:
                continue
            if a.betrag_brutto and abs(a.betrag_brutto - b.betrag_brutto) < 0.005 and (
                (a.rechnungsnummer and a.rechnungsnummer == b.rechnungsnummer) or
                (a.lieferant and a.lieferant.lower() == b.lieferant.lower() and abs((a.datum - b.datum).days) <= 3)
            ):
                doppel.append((a, b))
    return {"ohne_beleg": ohne_beleg, "ohne_konto": ohne_konto, "doppel": doppel}
