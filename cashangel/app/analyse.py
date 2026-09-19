"""Die Auswertung: Kategorisierung, Abo-Erkennung, Monatsbilanz, Sparpotenzial und die Psychologie hinter den Ausgaben.
Alles deterministisch, keine KI – jede Zahl lässt sich per Hand nachrechnen."""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

from .models import Bewegung, Kategorie, Regel

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONATSNAMEN = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
RE_ZAHLEN = re.compile(r"\d{3,}")
RE_PAYPAL = re.compile(r"paypal[:\s\-]*(.*)", re.I)
# Kartenpräfixe der Bank („VISA ALDI SUED“, „MASTERCARD REWE“) gehören nicht zum Partner
KARTENWOERTER = ("visa", "mastercard", "maestro", "girocard", "kartenzahlung", "debitkarte")
FIRMEN_ENDUNGEN = ("gmbh", "ag", "kg", "se", "ltd", "inc", "llc", "co", "ug", "ohg", "e.v.", "ev", "sarl", "s.a.", "sa", "bv", "nv", "plc", "limited", "eu", "ab", "oy", "srl", "spa")


# ---------------------------------------------------------------- Partner-Normalisierung

def partner_schluessel(gegenkonto: str, zweck: str = "") -> str:
    """Stabiler Schlüssel für „derselbe Zahlungspartner“: Kleinschreibung, ohne Zahlenketten,
    Rechtsformen und Füllwörter, maximal drei Wörter. „REWE SAGT DANKE 1234“ → „rewe sagt danke“."""
    quelle = gegenkonto.strip() or zweck.strip()
    m = RE_PAYPAL.search(quelle)
    if m and m.group(1).strip():
        quelle = m.group(1)
    t = quelle.lower()
    t = RE_ZAHLEN.sub(" ", t)
    t = re.sub(r"[^a-zäöüß&.+\- ]", " ", t)
    woerter = [w.strip(".-") for w in t.split()]
    woerter = [w for w in woerter if w and w not in FIRMEN_ENDUNGEN and w not in KARTENWOERTER and len(w) > 1]
    return " ".join(woerter[:3]) or "unbekannt"


def partner_anzeigename(bewegungen: list[Bewegung]) -> str:
    """Der häufigste Original-Gegenkontoname einer Partnergruppe, hübsch gekürzt."""
    namen: dict[str, int] = defaultdict(int)
    for b in bewegungen:
        n = (b.gegenkonto or b.verwendungszweck[:40]).strip()
        namen[n] += 1
    bester = max(namen.items(), key=lambda kv: kv[1])[0]
    return bester[:60]


# ---------------------------------------------------------------- Kategorisierung

def _enthaelt(text: str, muster: Iterable[str]) -> str | None:
    t = f" {text.lower()} "
    for m in muster:
        if m and m.lower() in t:
            return m
    return None


def person_erkennen(text: str, personen: list[str]) -> str:
    t = text.lower()
    for p in personen:
        if p and p.lower() in t:
            return p
    return ""


def klassifiziere(b: Bewegung, kategorien: dict[str, Kategorie], regeln: list[Regel], cfg: dict) -> tuple[Kategorie | None, str, str]:
    """(Kategorie, Person, Weg). Reihenfolge: eigene IBAN → gelernte Regel → Gehalt → Umbuchung → Standardmuster → Rückfall."""
    text = f"{b.gegenkonto} {b.verwendungszweck}"
    personen = list(cfg.get("personen", []))
    eigene = [i.replace(" ", "").upper() for i in cfg.get("eigene_ibans", []) if i]
    if b.gegen_iban and b.gegen_iban.replace(" ", "").upper() in eigene:
        return kategorien.get("umbuchung"), "", "umbuchung"
    seite = "einnahme" if b.betrag > 0 else "ausgabe"
    for r in regeln:
        if r.art and r.art != seite:
            continue
        if r.muster and r.muster.lower() in text.lower():
            k = next((k for k in kategorien.values() if k.id == r.kategorie_id), None)
            if k and k.art in (seite, "umbuchung"):
                return k, r.person or (person_erkennen(text, personen) if k.schluessel == "gehalt" else ""), f"regel:{r.id}"
    if b.betrag > 0 and _enthaelt(text, cfg.get("gehalt_muster", [])):
        return kategorien.get("gehalt"), person_erkennen(text, personen), "gehalt"
    if _enthaelt(text, cfg.get("umbuchung_muster", [])):
        return kategorien.get("umbuchung"), "", "umbuchung"
    art = "einnahme" if b.betrag > 0 else "ausgabe"
    # längstes passendes Muster gewinnt (spezifischer schlägt allgemein: „amazon prime“ vor „amazon“)
    bester: tuple[int, Kategorie] | None = None
    for d in cfg["kategorien"]:
        if d.get("art") != art:
            continue
        treffer = _enthaelt(text, d.get("muster", []))
        if treffer and (bester is None or len(treffer) > bester[0]):
            k = kategorien.get(d["schluessel"])
            if k:
                bester = (len(treffer), k)
    if bester:
        return bester[1], "", "muster"
    return kategorien.get("sonstige_einnahmen" if art == "einnahme" else "sonstiges"), "", "-"


def heller(farbe: str, anteil: float) -> str:
    """Denselben Ton heller machen (Richtung Weiß) – für mehrere Reihen derselben Sache, z. B. Gehalt je Person."""
    t = farbe.strip().lstrip("#")
    if len(t) != 6:
        return farbe
    try:
        r, g, b = (int(t[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return farbe
    misch = lambda x: min(255, round(x + (255 - x) * max(0.0, min(1.0, anteil))))
    return "#%02x%02x%02x" % (misch(r), misch(g), misch(b))


# ---------------------------------------------------------------- Dubletten

def dubletten(bewegungen: Iterable[Bewegung]) -> list[list[Bewegung]]:
    """Gruppen mutmaßlich doppelter Buchungen: gleicher Partner, gleicher Betrag, Datum höchstens einen Tag
    auseinander (Buchungs- vs. Valutadatum, CSV vs. PDF desselben Auszugs). Innerhalb der Gruppe steht die
    zuerst importierte vorn – sie wird beim Bereinigen behalten."""
    sortiert = sorted(bewegungen, key=lambda b: ((b.partner or b.gegenkonto or "").lower(), round(b.betrag, 2), b.datum, b.importiert_am, b.id or 0))
    gruppen: list[list[Bewegung]] = []
    aktuell: list[Bewegung] = []
    for b in sortiert:
        if aktuell:
            a = aktuell[0]
            gleich = ((a.partner or a.gegenkonto or "").lower() == (b.partner or b.gegenkonto or "").lower()
                      and round(a.betrag, 2) == round(b.betrag, 2) and abs((b.datum - aktuell[-1].datum).days) <= 1)
            if gleich:
                aktuell.append(b)
                continue
            if len(aktuell) > 1:
                gruppen.append(sorted(aktuell, key=lambda x: (x.importiert_am, x.id or 0)))
        aktuell = [b]
    if len(aktuell) > 1:
        gruppen.append(sorted(aktuell, key=lambda x: (x.importiert_am, x.id or 0)))
    gruppen.sort(key=lambda g: (g[0].datum, g[0].partner), reverse=True)
    return gruppen


# ---------------------------------------------------------------- Zeiträume

def monat_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def monat_name(key: str) -> str:
    j, m = key.split("-")
    return f"{MONATSNAMEN[int(m) - 1]} {j}"


def monate_im_zeitraum(zeitraum: str, heute: date | None = None) -> list[str]:
    """zeitraum: '12m' (letzte 12 volle Monate inkl. aktuellem), 'jahr:2025', 'monat:2025-09'."""
    heute = heute or date.today()
    if zeitraum.startswith("monat:"):
        return [zeitraum[6:]]
    if zeitraum.startswith("jahr:"):
        j = int(zeitraum[5:])
        return [f"{j:04d}-{m:02d}" for m in range(1, 13)]
    n = int(zeitraum.rstrip("m") or 12)
    out = []
    j, m = heute.year, heute.month
    for _ in range(n):
        out.append(f"{j:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, j = 12, j - 1
    return list(reversed(out))


def zeitraum_beschriftung(zeitraum: str) -> str:
    if zeitraum.startswith("monat:"):
        return monat_name(zeitraum[6:])
    if zeitraum.startswith("jahr:"):
        return f"Jahr {zeitraum[5:]}"
    return f"letzte {zeitraum.rstrip('m')} Monate"


# ---------------------------------------------------------------- Abo-Erkennung

def _intervall_typ(tage: float) -> tuple[str, float] | None:
    """(Name, Monatsfaktor) für einen mittleren Abstand in Tagen."""
    if 6 <= tage <= 8:
        return "wöchentlich", 52 / 12
    if 13 <= tage <= 16:
        return "14-tägig", 26 / 12
    if 26 <= tage <= 35:
        return "monatlich", 1.0
    if 55 <= tage <= 66:
        return "zweimonatlich", 0.5
    if 84 <= tage <= 98:
        return "vierteljährlich", 1 / 3
    if 170 <= tage <= 195:
        return "halbjährlich", 1 / 6
    if 350 <= tage <= 380:
        return "jährlich", 1 / 12
    return None


def abos_finden(bewegungen: Iterable[Bewegung], kategorien: dict[int, Kategorie], heute: date | None = None) -> list[dict]:
    """Wiederkehrende Zahlungen: gleicher Partner, regelmäßiger Abstand, stabiler Betrag.
    Liefert je Partner: Intervall, typischer Betrag, Monatskosten, zuletzt, nächste Fälligkeit, aktiv/ausgelaufen."""
    heute = heute or date.today()
    gruppen: dict[str, list[Bewegung]] = defaultdict(list)
    for b in bewegungen:
        k = kategorien.get(b.kategorie_id or -1)
        if b.betrag < 0 and not b.ignoriert and b.partner and not (k and k.schluessel in ("bargeld", "umbuchung")):
            gruppen[b.partner].append(b)
    out = []
    for partner, liste in gruppen.items():
        liste.sort(key=lambda x: x.datum)
        if len(liste) < 2:
            continue
        # Mehrere Buchungen am selben Tag zusammenfassen (Teilzahlungen)
        tage: dict[date, float] = defaultdict(float)
        for b in liste:
            tage[b.datum] += -b.betrag
        daten = sorted(tage)
        betraege = [tage[d] for d in daten]
        if len(daten) < 2:
            continue
        abstaende = [(daten[i + 1] - daten[i]).days for i in range(len(daten) - 1)]
        med = statistics.median(abstaende)
        typ = _intervall_typ(med)
        if not typ:
            continue
        # Regelmäßigkeit: mindestens 2/3 der Abstände passen zum Intervall
        passend = sum(1 for a in abstaende if _intervall_typ(a) and _intervall_typ(a)[0] == typ[0])
        if passend < max(1, round(len(abstaende) * 2 / 3)):
            continue
        if typ[0] in ("jährlich", "halbjährlich") and len(daten) < 2:
            continue
        if typ[0] not in ("jährlich", "halbjährlich") and len(daten) < 3:
            continue
        med_betrag = statistics.median(betraege)
        streuung = max(abs(x - med_betrag) for x in betraege)
        kat = kategorien.get(liste[-1].kategorie_id or -1)
        # Fixkosten dürfen schwanken (Strom-Abschlag, Telefon nach Verbrauch); variable Kategorien wie Lebensmittel oder
        # Restaurants gelten nur bei praktisch gleichem Betrag als Abo – sonst ist es einfach der wöchentliche Einkauf
        toleranz = max(2.0, med_betrag * 0.15) if (kat and kat.fix) else max(1.0, med_betrag * 0.02)
        stabil = streuung <= toleranz
        if not stabil and not (kat and kat.fix):
            continue
        letztes = daten[-1]
        naechstes = letztes + timedelta(days=round(med))
        aktiv = (heute - letztes).days <= med * 1.6 + 5
        out.append({
            "partner": partner, "name": partner_anzeigename(liste), "kategorie": kat.name if kat else "–",
            "kategorie_schluessel": kat.schluessel if kat else "", "farbe": kat.farbe if kat else "#64748b",
            "intervall": typ[0], "betrag": round(med_betrag, 2), "monatlich": round(med_betrag * typ[1], 2),
            "jaehrlich": round(med_betrag * typ[1] * 12, 2), "anzahl": len(daten), "seit": daten[0], "zuletzt": letztes,
            "naechste": naechstes, "aktiv": aktiv, "stabil": stabil, "letzter_betrag": round(betraege[-1], 2),
            "art": "Abo" if kat and kat.schluessel in ("abos_streaming", "mobilfunk") else ("Fixkosten" if kat and kat.fix else "Dauerauftrag"),
        })
    out.sort(key=lambda a: (-a["aktiv"], -a["monatlich"]))
    return out


# ---------------------------------------------------------------- Monatsbilanz

def monatsbilanz(bewegungen: Iterable[Bewegung], kategorien: dict[int, Kategorie], monate: list[str]) -> dict:
    """Je Monat: Einnahmen, Ausgaben, Saldo, Sparquote, Fix/variabel, je Kategorie; plus Summen und Ø."""
    je: dict[str, dict] = {m: {"monat": m, "name": monat_name(m), "einnahmen": 0.0, "ausgaben": 0.0, "fix": 0.0, "variabel": 0.0, "gespart": 0.0,
                               "kategorien": defaultdict(float), "personen": defaultdict(float), "anzahl": 0} for m in monate}
    for b in bewegungen:
        m = monat_key(b.datum)
        if m not in je or b.ignoriert:
            continue
        k = kategorien.get(b.kategorie_id or -1)
        if k and k.art == "umbuchung":
            continue
        z = je[m]
        if b.betrag > 0:
            z["einnahmen"] += b.betrag
            quelle = (f"Gehalt {b.person}" if b.person else (k.name if k else "Sonstige Einnahmen"))
            z["personen"][quelle] += b.betrag
        elif k and k.schluessel == "sparen":
            z["gespart"] += -b.betrag          # Sparplan, Depot, Tagesgeld: kein Konsum, das Geld bleibt im Haushalt
        else:
            z["ausgaben"] += -b.betrag
            z["anzahl"] += 1
            z["kategorien"][k.schluessel if k else "sonstiges"] += -b.betrag
            if k and k.fix:
                z["fix"] += -b.betrag
            else:
                z["variabel"] += -b.betrag
    for z in je.values():
        z["saldo"] = round(z["einnahmen"] - z["ausgaben"], 2)
        z["sparquote"] = round(z["saldo"] / z["einnahmen"] * 100, 1) if z["einnahmen"] > 0 else None
        for k in ("einnahmen", "ausgaben", "fix", "variabel", "gespart"):
            z[k] = round(z[k], 2)
        z["kategorien"] = {k: round(v, 2) for k, v in z["kategorien"].items()}
        z["personen"] = {k: round(v, 2) for k, v in z["personen"].items()}
    liste = [je[m] for m in monate]
    mit_daten = [z for z in liste if z["einnahmen"] or z["ausgaben"]]
    n = max(1, len(mit_daten))
    summe = {"einnahmen": round(sum(z["einnahmen"] for z in liste), 2), "ausgaben": round(sum(z["ausgaben"] for z in liste), 2),
             "fix": round(sum(z["fix"] for z in liste), 2), "variabel": round(sum(z["variabel"] for z in liste), 2), "gespart": round(sum(z["gespart"] for z in liste), 2)}
    summe["saldo"] = round(summe["einnahmen"] - summe["ausgaben"], 2)
    summe["sparquote"] = round(summe["saldo"] / summe["einnahmen"] * 100, 1) if summe["einnahmen"] > 0 else None
    schnitt = {k: round(v / n, 2) for k, v in summe.items() if k != "sparquote"}
    kats: dict[str, float] = defaultdict(float)
    quellen: dict[str, float] = defaultdict(float)
    for z in liste:
        for k, v in z["kategorien"].items():
            kats[k] += v
        for k, v in z["personen"].items():
            quellen[k] += v
    return {"monate": liste, "summe": summe, "schnitt": schnitt, "monate_mit_daten": len(mit_daten),
            "kategorien": {k: round(v, 2) for k, v in sorted(kats.items(), key=lambda kv: -kv[1])},
            "einnahmequellen": {k: round(v, 2) for k, v in sorted(quellen.items(), key=lambda kv: -kv[1])}}


# ---------------------------------------------------------------- Psychologie & Sparpotenzial

def prozent(x: float) -> str:
    return f"{x:.1f}".replace(".", ",").rstrip("0").rstrip(",") + " %"


def eur(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def insights(bewegungen: list[Bewegung], kategorien: dict[int, Kategorie], monate: list[str], abos: list[dict], cfg: dict) -> dict:
    """Muster hinter den Ausgaben. Liefert Kennzahlen (für Charts) und Karten (Titel, Text, Betrag, Typ)."""
    grenze = float(cfg.get("kleinbetrag_grenze", 15.0))
    im_zeitraum = [b for b in bewegungen if monat_key(b.datum) in monate and not b.ignoriert]
    ausgaben = [b for b in im_zeitraum if b.betrag < 0 and not (kategorien.get(b.kategorie_id or -1) and kategorien[b.kategorie_id].art == "umbuchung")]
    n_monate = max(1, len({monat_key(b.datum) for b in im_zeitraum}) or 1)
    bilanz = monatsbilanz(im_zeitraum, kategorien, monate)
    einnahmen = bilanz["summe"]["einnahmen"]
    gesamt = bilanz["summe"]["ausgaben"]
    karten: list[dict] = []

    def karte(typ, titel, text, betrag=None, kat=None):
        karten.append({"typ": typ, "titel": titel, "text": text, "betrag": betrag, "kategorie": kat})

    # Wochentage (variable Ausgaben, ohne Fixkosten/Sparen/Bargeld)
    variabel = [b for b in ausgaben if not (kategorien.get(b.kategorie_id or -1) and kategorien[b.kategorie_id].fix)
                and (kategorien.get(b.kategorie_id or -1) is None or kategorien[b.kategorie_id].schluessel not in ("bargeld", "sparen", "kredit"))]
    wochentage = [0.0] * 7
    wochentage_n = [0] * 7
    for b in variabel:
        wochentage[b.datum.weekday()] += -b.betrag
        wochentage_n[b.datum.weekday()] += 1
    var_summe = sum(wochentage)
    we_anteil = (wochentage[5] + wochentage[6]) / var_summe * 100 if var_summe else 0
    # Monatsdrittel
    drittel = [0.0, 0.0, 0.0]
    for b in variabel:
        drittel[min(2, (b.datum.day - 1) // 10)] += -b.betrag
    # Kleinbeträge
    klein = [b for b in variabel if -b.betrag < grenze]
    klein_summe = sum(-b.betrag for b in klein)
    # Kauftage mit vielen Buchungen
    je_tag: dict[date, list[Bewegung]] = defaultdict(list)
    for b in variabel:
        je_tag[b.datum].append(b)
    serien = sorted([(d, l) for d, l in je_tag.items() if len(l) >= 3], key=lambda dl: -sum(-b.betrag for b in dl[1]))
    # Kategorie-Trend: letzter Monat vs Ø der Vormonate
    trend = []
    if len(monate) >= 3:
        letzter = bilanz["monate"][-1]
        vorher = [z for z in bilanz["monate"][:-1] if z["ausgaben"]]
        if vorher and letzter["ausgaben"]:
            for schl, wert in letzter["kategorien"].items():
                mittel = sum(z["kategorien"].get(schl, 0.0) for z in vorher) / len(vorher)
                if mittel >= 30 and wert > mittel * 1.25:
                    trend.append((schl, wert, mittel))
    # Häufigste Partner
    partner: dict[str, dict] = {}
    for b in ausgaben:
        p = partner.setdefault(b.partner, {"name": b.gegenkonto or b.verwendungszweck[:40], "summe": 0.0, "anzahl": 0, "kat": kategorien.get(b.kategorie_id or -1)})
        p["summe"] += -b.betrag
        p["anzahl"] += 1
    top_summe = sorted(partner.values(), key=lambda p: -p["summe"])[:8]
    top_anzahl = sorted(partner.values(), key=lambda p: -p["anzahl"])[:8]
    # Restaurants/Lieferdienste
    rest = [b for b in ausgaben if kategorien.get(b.kategorie_id or -1) and kategorien[b.kategorie_id].schluessel == "restaurants"]
    rest_summe = sum(-b.betrag for b in rest)
    # Abos
    abo_aktiv = [a for a in abos if a["aktiv"]]
    abo_monat = sum(a["monatlich"] for a in abo_aktiv)
    streaming = [a for a in abo_aktiv if a["kategorie_schluessel"] == "abos_streaming"]
    # Größte Einzelausgaben
    groesste = sorted(ausgaben, key=lambda b: b.betrag)[:5]
    fixquote = bilanz["summe"]["fix"] / einnahmen * 100 if einnahmen else None

    # ---- Karten
    if einnahmen:
        sq = bilanz["summe"]["sparquote"]
        if sq is not None:
            gespart = bilanz["summe"]["gespart"]
            if sq >= 20:
                karte("gut", f"Sparquote {prozent(sq)}", f"Von {eur(einnahmen)} Einnahmen bleiben {eur(bilanz['summe']['saldo'])} übrig" + (f", davon {eur(gespart)} schon per Sparplan angelegt" if gespart else "") + ". Über 20 % gilt als sehr solide.", bilanz["summe"]["saldo"])
            elif sq >= 5:
                karte("info", f"Sparquote {prozent(sq)}", f"Es bleiben {eur(bilanz['summe']['saldo'])} von {eur(einnahmen)}. Faustregel: 10–20 % zurücklegen, am besten per Dauerauftrag direkt nach Gehaltseingang.", bilanz["summe"]["saldo"])
            else:
                karte("warn", f"Sparquote {prozent(sq)}", f"Die Ausgaben ({eur(gesamt)}) fressen die Einnahmen ({eur(einnahmen)}) fast vollständig auf. Erst Fixkosten prüfen, dann die variablen Posten unten.", bilanz["summe"]["saldo"])
    if fixquote is not None:
        karte("warn" if fixquote > 60 else "info", f"Fixkostenquote {prozent(fixquote)}",
              f"{eur(bilanz['schnitt']['fix'])} im Monat gehen fest weg (Miete, Energie, Versicherungen, Abos, Raten). "
              + ("Über 60 % lässt wenig Spielraum – hier wirkt jede Kündigung dauerhaft." if fixquote > 60 else "Unter 50 % ist gesund; alles, was du hier senkst, spart jeden Monat automatisch."),
              bilanz["schnitt"]["fix"])
    if abo_aktiv:
        karte("tipp", f"{len(abo_aktiv)} laufende Abos & Verträge: {eur(abo_monat)} pro Monat",
              f"Das sind {eur(abo_monat * 12)} im Jahr. " + (f"Allein Streaming & Abos: {eur(sum(a['monatlich'] for a in streaming))} monatlich – welche davon hast du in den letzten 30 Tagen wirklich genutzt? " if streaming else "")
              + "Nicht genutzte Abos sind der einfachste Sparposten: einmal kündigen, dauerhaft gespart.", abo_monat * 12)
    if klein:
        karte("tipp", f"Latte-Faktor: {len(klein) / n_monate:.0f} Kleinbeträge unter {grenze:.0f} € pro Monat",
              f"Zusammen {eur(klein_summe / n_monate)} monatlich, {eur(klein_summe / n_monate * 12)} im Jahr. Kleine Beträge fühlen sich harmlos an – genau deshalb summieren sie sich unbemerkt. Ein Wochenbudget in bar macht sie sichtbar.",
              klein_summe / n_monate)
    if var_summe and we_anteil >= 40:
        karte("info", f"{we_anteil:.0f} % der variablen Ausgaben fallen am Wochenende",
              "Samstag und Sonntag sind die Tage mit den meisten Spontankäufen: Freizeit, Essen gehen, Shopping. Wer sich fürs Wochenende vorher einen Betrag festlegt, gibt messbar weniger aus.")
    if var_summe:
        anteil_erstes = drittel[0] / var_summe * 100
        if anteil_erstes >= 45:
            karte("info", f"Zahltag-Effekt: {anteil_erstes:.0f} % der variablen Ausgaben in den ersten 10 Tagen des Monats",
                  "Kurz nach dem Gehaltseingang sitzt das Geld lockerer. Gegenmittel: Sparbetrag und Rücklagen am 1. abbuchen lassen, dann bleibt nur der Rest zum Ausgeben.")
        elif drittel[2] / var_summe * 100 >= 45:
            karte("info", f"{drittel[2] / var_summe * 100:.0f} % der variablen Ausgaben am Monatsende",
                  "Das Geld wird gegen Ende knapp und trotzdem ausgegeben – ein Zeichen für Aufschieben (Einkäufe, Rechnungen). Ein festes Wochenbudget verteilt gleichmäßiger.")
    if rest:
        karte("tipp", f"Essen gehen & Lieferdienste: {eur(rest_summe / n_monate)} pro Monat, {len(rest) / n_monate:.1f} Bestellungen",
              f"Im Schnitt {eur(rest_summe / len(rest))} je Bestellung. Bestellen ist die klassische Bequemlichkeitsausgabe nach einem langen Tag. Zwei Bestellungen weniger im Monat sparen rund {eur(2 * rest_summe / len(rest) * 12)} im Jahr.",
              rest_summe / n_monate, "restaurants")
    for schl, wert, mittel in trend[:3]:
        k = next((k for k in kategorien.values() if k.schluessel == schl), None)
        karte("warn", f"{k.name if k else schl}: {eur(wert)} im letzten Monat, sonst Ø {eur(mittel)}",
              f"{(wert / mittel - 1) * 100:.0f} % über dem Durchschnitt der Vormonate. Einmaliger Ausreißer oder neue Gewohnheit? Die Buchungen dieser Kategorie zeigen es.", wert - mittel, schl)
    if serien:
        d, l = serien[0]
        karte("info", f"Kauf-Serien: {len(serien)} Tage mit drei oder mehr Käufen",
              f"Spitzenreiter ist der {d.strftime('%d.%m.%Y')} mit {len(l)} Buchungen über {eur(sum(-b.betrag for b in l))}. Kaufen löst Kaufen aus – der erste Kauf senkt die Hemmschwelle für den nächsten.")
    if not karten:
        karte("info", "Noch zu wenig Daten", "Lade Kontoauszüge von mindestens zwei bis drei Monaten, dann erscheinen hier die Muster.")

    return {
        "karten": karten,
        "wochentage": [{"tag": WOCHENTAGE[i], "summe": round(wochentage[i] / n_monate, 2), "anzahl": round(wochentage_n[i] / n_monate, 1)} for i in range(7)],
        "drittel": [round(x / n_monate, 2) for x in drittel],
        "kleinbetraege": {"anzahl": round(len(klein) / n_monate, 1), "summe": round(klein_summe / n_monate, 2), "grenze": grenze},
        "top_summe": [{"name": p["name"][:40], "summe": round(p["summe"], 2), "anzahl": p["anzahl"], "kategorie": p["kat"].name if p["kat"] else "–", "farbe": p["kat"].farbe if p["kat"] else "#64748b"} for p in top_summe],
        "top_anzahl": [{"name": p["name"][:40], "summe": round(p["summe"], 2), "anzahl": p["anzahl"], "kategorie": p["kat"].name if p["kat"] else "–", "farbe": p["kat"].farbe if p["kat"] else "#64748b"} for p in top_anzahl],
        "groesste": [{"datum": b.datum.isoformat(), "name": (b.gegenkonto or b.verwendungszweck)[:50], "betrag": round(-b.betrag, 2)} for b in groesste],
        "abo_monat": round(abo_monat, 2), "fixquote": round(fixquote, 1) if fixquote is not None else None,
        "n_monate": n_monate,
    }
