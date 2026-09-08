"""Buchung ↔ Kontobewegung: Betrag exakt, Datum ±N Tage (Konfiguration)."""
from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from . import config
from .importer.kontoauszug import Bewegung
from .models import Buchung, DedupIgnoriert, IgnorRegel, Kontobewegung


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


FREMDWAEHRUNG_TOLERANZ = 0.08   # ±8 % um Kursschwankung und Bankgebühr abzudecken


def _passt(b: Buchung, k: Kontobewegung, toleranz: int) -> bool:
    if b.richtung == "ausgabe" and k.betrag >= 0:
        return False
    if b.richtung == "einnahme" and k.betrag <= 0:
        return False
    if abs((k.datum - b.datum).days) > toleranz:
        return False
    if abs(abs(k.betrag) - abs(b.betrag_brutto)) <= 0.005:
        return True
    if b.waehrung != "EUR" and b.betrag_fremd:
        # Fremdwährung: der Euro-Betrag ist noch unbekannt, der Kurs liegt grob bei 1 (USD) – Toleranzband
        return abs(abs(k.betrag) - b.betrag_fremd) / b.betrag_fremd <= FREMDWAEHRUNG_TOLERANZ
    return False


def euro_uebernehmen(b: Buchung, k: Kontobewegung) -> bool:
    """Bei Fremdwährungsrechnung den tatsächlich abgebuchten Euro-Betrag in die Buchung schreiben."""
    if b.waehrung == "EUR" or not b.betrag_fremd:
        return False
    eur = abs(k.betrag)
    if abs(eur - b.betrag_brutto) < 0.005:
        return False
    faktor = eur / b.betrag_brutto if b.betrag_brutto else 1.0
    b.betrag_brutto = round(eur, 2)
    b.betrag_netto = round(b.betrag_netto * faktor, 2) if b.ust_betrag else round(eur, 2)
    b.ust_betrag = round(b.betrag_brutto - b.betrag_netto, 2)
    return True


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
            if euro_uebernehmen(b, k):
                s.add(b)
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
    exakt = [b for b in alle if abs((k.datum - b.datum).days) <= toleranz_tage and (
        abs(abs(k.betrag) - b.betrag_brutto) < 0.005 or
        (b.waehrung != "EUR" and b.betrag_fremd and abs(abs(k.betrag) - b.betrag_fremd) / b.betrag_fremd <= FREMDWAEHRUNG_TOLERANZ))]
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


def ignorregeln_anwenden(s: Session, nur_ids: list[int] | None = None) -> int:
    """Kontobewegungen ohne Buchung gegen die Ignorier-Muster prüfen. Gibt Anzahl neu ignorierter."""
    regeln = s.exec(select(IgnorRegel)).all()
    if not regeln:
        return 0
    n = 0
    for k in s.exec(select(Kontobewegung).where(Kontobewegung.buchung_id == None, Kontobewegung.ignoriert == False)).all():  # noqa: E711,E712
        if nur_ids is not None and k.id not in nur_ids:
            continue
        text = f"{k.gegenkonto} {k.verwendungszweck}".lower()
        for r in regeln:
            if r.muster.lower() in text:
                k.ignoriert = True
                r.treffer += 1
                s.add(k)
                s.add(r)
                n += 1
                break
    s.commit()
    return n


def abgleich(s: Session, jahr: int | None = None) -> list[dict]:
    """Jede Kontobewegung mit Status: zugeordnet | rueckfrage | kein_beleg | ignoriert, plus Dubletten-Hinweis."""
    alle = s.exec(select(Kontobewegung).order_by(Kontobewegung.datum.desc(), Kontobewegung.id.desc())).all()
    if jahr:
        alle = [k for k in alle if k.datum.year == jahr]
    buchungen = {b.id: b for b in s.exec(select(Buchung)).all()}
    zeilen = []
    for k in alle:
        eintrag = {"k": k, "buchung": buchungen.get(k.buchung_id) if k.buchung_id else None, "kandidaten": [], "doppelt": None}
        if k.ignoriert:
            eintrag["status"] = "ignoriert"
        elif k.buchung_id:
            eintrag["status"] = "zugeordnet"
        else:
            kand = kandidaten_fuer(s, k)
            eintrag["kandidaten"] = kand
            eintrag["status"] = "rueckfrage" if kand else "kein_beleg"
        # evtl. doppelt: gleicher Betrag, gleiches Gegenkonto, ±2 Tage, andere Bewegung
        for o in alle:
            if o.id != k.id and abs(o.betrag - k.betrag) < 0.005 and o.gegenkonto.lower() == k.gegenkonto.lower() \
                    and abs((o.datum - k.datum).days) <= 2:
                eintrag["doppelt"] = o
                break
        zeilen.append(eintrag)
    return zeilen
