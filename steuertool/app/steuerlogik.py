"""Steuerlogik. Alle Sonderregeln stehen hier, alle Grenzwerte kommen aus
steuerregeln.json. Nichts in diesem Modul redet mit der Datenbank oder mit
einem KI-Modell — reine Funktionen, damit sie testbar bleiben.

Grundsatz Kleinunternehmer (§19 UStG): kein Vorsteuerabzug, also ist der
Bruttobetrag die Betriebsausgabe. Netto und USt werden nur für die
Darstellung und den Was-wäre-wenn-Rechner mitgeführt.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from .models import Anlagegut, Buchung, Kategorie

RC_HINWEISE = re.compile(
    r"reverse[\s-]?charge|steuerschuldnerschaft des leistungsempf|umkehr der steuerschuld|"
    r"vat reverse|tax to be paid by the recipient|art(?:icle|\.)?\s*196|§\s*13\s*b|"
    r"vat 0%|0 % vat|vat exempt|steuerfreie innergemeinschaftliche|innergemeinschaftliche leistung",
    re.IGNORECASE,
)


def runde(x: float) -> float:
    return round(x + 0.0, 2)


def quartal(d: date) -> int:
    return (d.month - 1) // 3 + 1


def meta(b: Buchung) -> dict:
    try:
        return json.loads(b.meta_json or "{}")
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- Beträge

def betraege_vervollstaendigen(netto: float | None, ust_satz: float | None,
                               ust_betrag: float | None, brutto: float | None) -> tuple[float, float, float, float]:
    """Aus den bekannten Teilen die restlichen ableiten. Gibt (netto, satz, ust, brutto)."""
    if netto is None and brutto is None:
        return 0.0, ust_satz or 0.0, ust_betrag or 0.0, 0.0
    if netto is not None and ust_betrag is not None:
        brutto = netto + ust_betrag if brutto is None else brutto
        satz = ust_satz if ust_satz is not None else (runde(ust_betrag / netto * 100) if netto else 0.0)
        return runde(netto), satz, runde(ust_betrag), runde(brutto)
    if netto is not None and ust_satz is not None:
        ust = netto * ust_satz / 100
        return runde(netto), ust_satz, runde(ust), runde(brutto if brutto is not None else netto + ust)
    if brutto is not None and ust_satz is not None:
        netto_ = brutto / (1 + ust_satz / 100)
        return runde(netto_), ust_satz, runde(brutto - netto_), runde(brutto)
    if brutto is not None and netto is not None:
        ust = brutto - netto
        satz = runde(ust / netto * 100) if netto else 0.0
        return runde(netto), satz, runde(ust), runde(brutto)
    if brutto is not None:
        return runde(brutto), 0.0, 0.0, runde(brutto)
    return runde(netto), 0.0, 0.0, runde(netto)


# ------------------------------------------------------- Reverse Charge

def ist_eu_ustid(ust_idnr: str, cfg: dict) -> bool:
    return bool(ust_idnr) and ust_idnr[:2].upper() in set(cfg["eu_laender"])


def erkenne_reverse_charge(text: str, ust_idnr: str, lieferant: str, ust_betrag: float, cfg: dict) -> tuple[bool, list[str]]:
    """§13b: ausländische USt-IdNr, kein deutscher USt-Ausweis, Hinweistext oder bekannter Anbieter."""
    gruende: list[str] = []
    ust_idnr = (ust_idnr or "").replace(" ", "").upper()
    if ust_idnr and not ust_idnr.startswith("DE"):
        gruende.append(f"ausländische USt-IdNr {ust_idnr}")
    if text and RC_HINWEISE.search(text):
        gruende.append("Hinweis auf Umkehr der Steuerschuld im Belegtext")
    l = (lieferant or "").lower()
    for name in cfg.get("reverse_charge_lieferanten", []):
        if name in l:
            gruende.append(f"bekannter Auslandsanbieter „{name}“")
            break
    treffer = bool(gruende) and (ust_betrag or 0) == 0
    if gruende and (ust_betrag or 0) > 0:
        gruende.append("aber USt ist auf dem Beleg ausgewiesen – kein §13b, bitte prüfen")
        treffer = False
    return treffer, gruende


def ust_basis(cfg: dict) -> str:
    """Woraus Zeile 48 gebildet wird: 'zahlung' (Zahlungen ans Finanzamt, Abfluss) oder 'rechnung' (§13b je Rechnung)."""
    return "rechnung" if str(cfg.get("ust_zeile48_basis", "zahlung")).lower() == "rechnung" else "zahlung"


def _enthaelt(text: str, muster: Iterable[str]) -> bool:
    t = f" {text.lower()} "
    return any(m in t for m in muster)


def erkenne_finanzamt(gegenkonto: str, zweck: str, richtung: str, cfg: dict) -> tuple[str | None, str]:
    """Zahlungen an das / vom Finanzamt einordnen.

    Rückgabe: (Kategorie-Schlüssel oder None, Begründung). Umsatzsteuer → ust_zahlung / ust_erstattung,
    Einkommensteuer, Soli, Kirchensteuer → privat (einkommensteuer / steuererstattung_privat).
    """
    fm = cfg.get("finanzamt_muster") or {}
    beides = f"{gegenkonto} {zweck}"
    if not _enthaelt(beides, fm.get("gegenkonto", ["finanzamt"])):
        return None, ""
    ausgabe = richtung == "ausgabe"
    if _enthaelt(beides, fm.get("einkommensteuer", [])):
        return ("einkommensteuer" if ausgabe else "steuererstattung_privat"), "Finanzamt: Einkommensteuer/Soli/Kirchensteuer ist privat, keine Betriebsausgabe."
    if _enthaelt(beides, fm.get("umsatzsteuer", [])):
        return ("ust_zahlung" if ausgabe else "ust_erstattung"), ("Finanzamt: gezahlte Umsatzsteuer → Zeile 48." if ausgabe else "Finanzamt: erstattete Umsatzsteuer → Zeile 17.")
    return None, "Zahlung vom/ans Finanzamt – Steuerart aus dem Verwendungszweck nicht erkennbar, bitte Kategorie wählen."


def erkenne_vorsorge(gegenkonto: str, zweck: str, cfg: dict) -> bool:
    """Beiträge an KSK, Krankenkasse, Rentenversicherung: Sonderausgaben, nicht EÜR."""
    return _enthaelt(f"{gegenkonto} {zweck}", cfg.get("vorsorge_muster") or [])


def ksk_uebersicht(buchungen: Iterable[Buchung], kategorien: dict[int, Kategorie], anlagegueter: list[Anlagegut], jahr: int, cfg: dict) -> dict:
    """Zahlen für Künstlersozialkasse und Einkommensteuer: Arbeitseinkommen (= Gewinn), gezahlte Vorsorgebeiträge,
    abgabepflichtige Entgelte an selbständige Künstler und die daraus folgende Künstlersozialabgabe."""
    buchungen = list(buchungen)
    gewinn = next((z["betrag"] for z in eur_zeilen(buchungen, kategorien, anlagegueter, jahr, cfg) if z["bezeichnung"].startswith("Gewinn")), 0.0)
    vorsorge = erstattet = entgelte = 0.0
    for b in buchungen:
        if b.datum.year != jahr or b.status != "bestaetigt" or getattr(b, "storniert", False):
            continue
        k = kategorien.get(b.kategorie_id or -1)
        if not k:
            continue
        if k.sonderfall == "vorsorge":
            vorsorge += b.betrag_brutto
        elif k.sonderfall == "vorsorge_erstattung":
            erstattet += b.betrag_brutto
        elif k.sonderfall == "fremdleistung" and str(meta(b).get("ksk_kuenstler", "")) in ("1", "true", "True"):
            entgelte += b.betrag_netto if b.betrag_netto else b.betrag_brutto
    satz = float(cfg.get("ksk_abgabesatz_prozent", 5.0))
    bagatell = float(cfg.get("ksk_bagatellgrenze", 1000.0))
    return {"arbeitseinkommen": runde(gewinn), "vorsorge": runde(vorsorge - erstattet), "vorsorge_gezahlt": runde(vorsorge), "vorsorge_erstattet": runde(erstattet),
            "entgelte_kuenstler": runde(entgelte),
            "abgabe": runde(entgelte * satz / 100) if entgelte > bagatell else 0.0, "satz": satz, "bagatell": bagatell,
            "mindestverdienst": float(cfg.get("ksk_mindestverdienst", 3900.0))}


def erkenne_kapitalanlage(gegenkonto: str, zweck: str, cfg: dict) -> bool:
    """Wertpapier-, Depot- und Dividendenbuchungen: privates Kapitalvermögen (Anlage KAP), gehört nicht in die EÜR."""
    return _enthaelt(f"{gegenkonto} {zweck}", cfg.get("kapitalanlage_muster") or [])


def ust_abgleich(buchungen: Iterable[Buchung], kategorien: dict[int, Kategorie], jahr: int, cfg: dict) -> dict:
    """§13b-Steuer, die im Jahr entstanden ist, gegen das, was tatsächlich ans Finanzamt floss."""
    entstanden = gezahlt = erstattet = 0.0
    for b in buchungen:
        if b.datum.year != jahr or b.status != "bestaetigt" or getattr(b, "storniert", False):
            continue
        entstanden += ust_13b(b, cfg)
        k = kategorien.get(b.kategorie_id or -1)
        if k and k.sonderfall == "ust_zahlung":
            gezahlt += b.betrag_brutto
        elif k and k.sonderfall == "ust_erstattung":
            erstattet += b.betrag_brutto
    basis = ust_basis(cfg)
    return {"entstanden": runde(entstanden), "gezahlt": runde(gezahlt), "erstattet": runde(erstattet),
            "offen": runde(entstanden - gezahlt + erstattet), "basis": basis,
            "zeile48": runde(gezahlt if basis == "zahlung" else entstanden)}


def ust_13b(b: Buchung, cfg: dict) -> float:
    """Steuer, die der Leistungsempfänger nach §13b selbst schuldet."""
    if not b.reverse_charge or b.richtung != "ausgabe":
        return 0.0
    return runde(b.betrag_netto * cfg["regelsteuersatz"] / 100)


def ustva_kennzahlen_fuer(b: Buchung, cfg: dict) -> tuple[str, str]:
    kz = cfg["ustva_kennzahlen"]
    if b.ust_idnr and not ist_eu_ustid(b.ust_idnr, cfg) and not b.ust_idnr.upper().startswith("DE"):
        return kz["reverse_charge_drittland_basis"], kz["reverse_charge_drittland_steuer"]
    return kz["reverse_charge_eu_basis"], kz["reverse_charge_eu_steuer"]


# ------------------------------------------------------------ Bewertung

@dataclass
class Bewertung:
    """Was von einer Buchung tatsächlich als Betriebsausgabe/-einnahme zählt."""
    basis: float                       # Bruttobetrag (bei §19) bzw. Netto (Regelbesteuerung)
    abzugsfaehig: float                # Betrag, der in die EÜR-Zeile fließt
    eur_zeile: int | None
    hinweise: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    ust_13b: float = 0.0
    umwandeln_in: str | None = None    # Kategorie-Schlüssel, falls die Buchung anders zu behandeln ist
    afa_vorschlag: dict | None = None  # {"nutzungsdauer_jahre": .., "anschaffungskosten": ..}


def bewerte(b: Buchung, k: Kategorie | None, cfg: dict,
            jahres_kontext: dict | None = None) -> Bewertung:
    """Wendet die Sonderregel der Kategorie an.

    jahres_kontext (optional, aus der DB zusammengestellt):
      homeoffice_tage_bisher: int      – bereits gebuchte Tage im Jahr (ohne diese Buchung)
      geschenke_je_empfaenger: dict    – {empfaenger: summe im Jahr ohne diese Buchung}
    """
    ctx = jahres_kontext or {}
    m = meta(b)
    basis = b.betrag_brutto if cfg["kleinunternehmer"] else b.betrag_netto
    bw = Bewertung(basis=basis, abzugsfaehig=basis, eur_zeile=k.eur_zeile if k else None)
    sonderfall = k.sonderfall if k else None

    if b.richtung == "einnahme":
        bw.eur_zeile = k.eur_zeile if k else 11
        if sonderfall == "privat":
            bw.abzugsfaehig = 0.0
            bw.eur_zeile = None
            bw.hinweise.append("Private Einnahme (z. B. Steuererstattung) – keine Betriebseinnahme.")
            return bw
        if sonderfall == "ust_erstattung":
            bw.hinweise.append("Vom Finanzamt erstattete Umsatzsteuer ist Betriebseinnahme (Zeile 17).")
            return bw
        if sonderfall == "vorsorge_erstattung":
            bw.abzugsfaehig = 0.0
            bw.eur_zeile = None
            bw.hinweise.append("Erstattung von KSK/Krankenkasse/Rentenversicherung: keine Betriebseinnahme – mindert die Sonderausgaben in der Anlage Vorsorgeaufwand.")
            return bw
        if b.ust_betrag:
            bw.warnungen.append("Einnahme mit USt-Ausweis – als Kleinunternehmer darf keine USt ausgewiesen werden (§19 UStG).")
        return bw

    if b.reverse_charge:
        bw.ust_13b = ust_13b(b, cfg)
        bw.hinweise.append(
            f"§13b: {bw.ust_13b:.2f} € Umsatzsteuer an das Finanzamt abzuführen (UStVA), "
            f"bei §19 ohne Vorsteuerabzug – echte Zusatzbelastung.")

    if sonderfall == "privat":
        bw.abzugsfaehig = 0.0
        bw.eur_zeile = None
        return bw

    if sonderfall == "vorsorge":
        bw.abzugsfaehig = 0.0
        bw.eur_zeile = None
        bw.hinweise.append("Vorsorgebeitrag (KSK, Kranken-/Rentenversicherung): keine Betriebsausgabe, sondern Sonderausgabe – Anlage Vorsorgeaufwand der Einkommensteuer.")
        return bw

    if sonderfall == "fremdleistung":
        if str(m.get("ksk_kuenstler", "")) in ("1", "true", "True"):
            satz = float(cfg.get("ksk_abgabesatz_prozent", 5.0))
            bw.hinweise.append(f"Entgelt an selbständigen Künstler/Publizisten: zählt für die Künstlersozialabgabe ({satz:g} % auf {b.betrag_netto:.2f} € netto, Meldung bis 31. März).")
        return bw

    if sonderfall == "ust_zahlung":
        if ust_basis(cfg) == "rechnung":
            bw.abzugsfaehig = 0.0
            bw.eur_zeile = None
            bw.hinweise.append("Zeile 48 wird aus der §13b-Steuer je Rechnung gebildet – diese Zahlung zählt nicht noch einmal (Einstellung „Zeile 48“).")
        else:
            bw.hinweise.append("An das Finanzamt gezahlte Umsatzsteuer: Betriebsausgabe im Jahr der Zahlung (Zeile 48).")
        return bw

    if sonderfall == "bewirtung":
        prozent = cfg["bewirtung_abzug_prozent"]
        bw.abzugsfaehig = runde(basis * prozent / 100)
        bw.hinweise.append(f"Bewirtung: {prozent} % abziehbar ({bw.abzugsfaehig:.2f} € von {basis:.2f} €).")
        fehlend = [f for f in ("anlass", "teilnehmer") if not str(m.get(f, "")).strip()]
        if fehlend:
            bw.warnungen.append("Pflichtangaben fehlen: " + ", ".join(fehlend) + " (auf dem Beleg vermerken).")
        if basis > 0 and not m.get("bewirtungsbeleg_maschinell", True):
            bw.warnungen.append("Bewirtungsbeleg muss maschinell erstellt und registriert sein.")

    elif sonderfall == "gwg":
        grenze = cfg["gwg_grenze_netto"]
        if b.betrag_netto > grenze:
            nd = int(m.get("nutzungsdauer_jahre") or cfg["afa_nutzungsdauer_standard_jahre"])
            bw.umwandeln_in = "anlagevermoegen"
            bw.eur_zeile = None
            bw.abzugsfaehig = 0.0
            bw.afa_vorschlag = {"nutzungsdauer_jahre": nd, "anschaffungskosten": basis}
            bw.hinweise.append(
                f"Netto {b.betrag_netto:.2f} € liegt über der GWG-Grenze von {grenze:.0f} € – "
                f"kein Sofortabzug, AfA über {nd} Jahre (Zeile 30).")
        else:
            bw.hinweise.append(f"GWG bis {grenze:.0f} € netto: Sofortabzug in Zeile {k.eur_zeile}.")

    elif sonderfall == "afa":
        # Die Anschaffung selbst ist keine Betriebsausgabe; abgeschrieben wird über Anlagegut.
        bw.abzugsfaehig = 0.0
        bw.eur_zeile = None
        bw.hinweise.append("Anlagevermögen: Abzug erfolgt über die jährliche AfA, nicht über diese Buchung.")

    elif sonderfall == "fahrtkosten":
        km = float(m.get("km") or 0)
        if km > 0:
            bw.abzugsfaehig = runde(km * cfg["km_pauschale"])
            bw.hinweise.append(f"{km:g} km × {cfg['km_pauschale']:.2f} € = {bw.abzugsfaehig:.2f} €.")
        else:
            bw.warnungen.append("Keine Kilometer erfasst – Fahrtkosten werden mit 0,30 €/km berechnet, nicht aus dem Belegbetrag.")

    elif sonderfall == "homeoffice":
        tage = int(m.get("tage") or 0)
        bisher = int(ctx.get("homeoffice_tage_bisher", 0))
        pausch = cfg["homeoffice_tagespauschale"]
        maximum = cfg["homeoffice_max_jahr"]
        if tage <= 0:
            bw.warnungen.append("Keine Homeoffice-Tage erfasst.")
        gesamt_vorher = min(bisher * pausch, maximum)
        gesamt_nachher = min((bisher + tage) * pausch, maximum)
        bw.abzugsfaehig = runde(gesamt_nachher - gesamt_vorher)
        bw.hinweise.append(f"{tage} Tage × {pausch:.2f} € = {tage * pausch:.2f} €, Jahresdeckel {maximum:.0f} €.")
        if (bisher + tage) * pausch > maximum:
            bw.warnungen.append(f"Jahresdeckel von {maximum:.0f} € erreicht – nur noch {bw.abzugsfaehig:.2f} € wirksam.")

    elif sonderfall == "privatanteil":
        prozent = float(m.get("privatanteil_prozent", cfg["privatanteil_standard_prozent"]))
        bw.abzugsfaehig = runde(basis * (100 - prozent) / 100)
        bw.hinweise.append(f"Privatanteil {prozent:g} % abgezogen – betrieblich {bw.abzugsfaehig:.2f} €.")

    elif sonderfall == "geschenk":
        empf = str(m.get("empfaenger", "")).strip()
        grenze = cfg["geschenk_grenze_je_empfaenger"]
        if not empf:
            bw.warnungen.append("Empfänger fehlt – bei Geschenken Pflichtangabe (Grenze gilt je Empfänger und Jahr).")
        bisher = float(ctx.get("geschenke_je_empfaenger", {}).get(empf, 0.0))
        if bisher + basis > grenze:
            bw.abzugsfaehig = 0.0
            bw.eur_zeile = None
            bw.warnungen.append(
                f"Geschenke an „{empf or '?'}“ im Jahr {bisher + basis:.2f} € > {grenze:.0f} € – vollständig nicht abziehbar.")
        else:
            bw.hinweise.append(f"Geschenk innerhalb der {grenze:.0f}-€-Grenze (bisher {bisher:.2f} €).")

    return bw


# ---------------------------------------------------------------- AfA

def afa_fuer_jahr(a: Anlagegut, jahr: int) -> float:
    """Lineare AfA, im Anschaffungsjahr monatsgenau (§7 Abs. 1 S. 4 EStG)."""
    if not a.aktiv or a.nutzungsdauer_jahre <= 0:
        return 0.0
    start = a.anschaffung
    if jahr < start.year:
        return 0.0
    jahres_afa = a.anschaffungskosten / a.nutzungsdauer_jahre
    monate_erstes_jahr = 12 - start.month + 1
    erstes = jahres_afa * monate_erstes_jahr / 12
    if jahr == start.year:
        return runde(erstes)
    # Restwert nach dem ersten Jahr, dann volle Jahre, dann Rest im letzten Jahr
    rest = a.anschaffungskosten - erstes
    volle_jahre = jahr - start.year - 1
    rest -= jahres_afa * volle_jahre
    if rest <= 0.005:
        return 0.0
    return runde(min(jahres_afa, rest))


# ---------------------------------------------------------- Aggregation

def jahres_kontext(buchungen: Iterable[Buchung], kategorien: dict[int, Kategorie], jahr: int,
                   ausser_id: int | None = None) -> dict:
    """Sammelt, was Sonderregeln über das Jahr hinweg brauchen."""
    tage = 0
    geschenke: dict[str, float] = {}
    for b in buchungen:
        if b.datum.year != jahr or b.id == ausser_id or b.status != "bestaetigt":
            continue
        k = kategorien.get(b.kategorie_id or -1)
        if not k:
            continue
        m = meta(b)
        if k.sonderfall == "homeoffice":
            tage += int(m.get("tage") or 0)
        elif k.sonderfall == "geschenk":
            e = str(m.get("empfaenger", "")).strip()
            geschenke[e] = geschenke.get(e, 0.0) + b.betrag_brutto
    return {"homeoffice_tage_bisher": tage, "geschenke_je_empfaenger": geschenke}


@dataclass
class Zelle:
    brutto: float = 0.0
    netto: float = 0.0
    ust: float = 0.0            # ausgewiesene USt + §13b-Steuer = entgangene Vorsteuer
    abzugsfaehig: float = 0.0
    anzahl: int = 0

    def add(self, other: "Zelle") -> None:
        self.brutto += other.brutto
        self.netto += other.netto
        self.ust += other.ust
        self.abzugsfaehig += other.abzugsfaehig
        self.anzahl += other.anzahl


def quartalsuebersicht(buchungen: list[Buchung], kategorien: dict[int, Kategorie],
                       anlagegueter: list[Anlagegut], jahr: int, cfg: dict) -> dict:
    """Zeilen = Kategorien, Spalten = Q1..Q4 + Jahr. Nur bestätigte Buchungen.

    Rückgabe: {"zeilen": [{"kategorie": Kategorie, "q": [Zelle x4], "jahr": Zelle}], "summe_ausgaben": [...], ...}
    """
    zeilen: dict[int, list[Zelle]] = {}
    jahres = [b for b in buchungen if b.datum.year == jahr and b.status == "bestaetigt"]
    homeoffice_tage = 0
    geschenke: dict[str, float] = {}
    for b in sorted(jahres, key=lambda x: (x.datum, x.id or 0)):
        k = kategorien.get(b.kategorie_id or -1)
        if k is None:
            continue
        ctx = {"homeoffice_tage_bisher": homeoffice_tage, "geschenke_je_empfaenger": dict(geschenke)}
        bw = bewerte(b, k, cfg, ctx)
        m = meta(b)
        if k.sonderfall == "homeoffice":
            homeoffice_tage += int(m.get("tage") or 0)
        if k.sonderfall == "geschenk":
            e = str(m.get("empfaenger", "")).strip()
            geschenke[e] = geschenke.get(e, 0.0) + b.betrag_brutto
        z = Zelle(brutto=b.betrag_brutto, netto=b.betrag_netto, ust=b.ust_betrag + bw.ust_13b,
                  abzugsfaehig=bw.abzugsfaehig, anzahl=1)
        zeilen.setdefault(k.id, [Zelle() for _ in range(5)])
        zeilen[k.id][quartal(b.datum) - 1].add(z)
        zeilen[k.id][4].add(z)

    # AfA als eigene Zeile: Jahresbetrag, gleichmäßig auf die Quartale verteilt (Darstellung)
    afa_summe = sum(afa_fuer_jahr(a, jahr) for a in anlagegueter)
    afa_kat = next((k for k in kategorien.values() if k.schluessel == "afa"), None)
    if afa_summe and afa_kat:
        zellen = zeilen.setdefault(afa_kat.id, [Zelle() for _ in range(5)])
        for i in range(4):
            zellen[i].add(Zelle(brutto=afa_summe / 4, netto=afa_summe / 4, abzugsfaehig=afa_summe / 4))
        zellen[4].add(Zelle(brutto=afa_summe, netto=afa_summe, abzugsfaehig=afa_summe, anzahl=len(anlagegueter)))

    reihen = []
    for kid, zellen in zeilen.items():
        k = kategorien[kid]
        reihen.append({"kategorie": k, "q": zellen[:4], "jahr": zellen[4]})
    reihen.sort(key=lambda r: (0 if r["kategorie"].richtung == "einnahme" else 1, r["kategorie"].eur_zeile or 999, r["kategorie"].name))

    def summe(richtung: str) -> list[Zelle]:
        s = [Zelle() for _ in range(5)]
        for r in reihen:
            if r["kategorie"].richtung == richtung:
                for i in range(4):
                    s[i].add(r["q"][i])
                s[4].add(r["jahr"])
        return s

    einnahmen, ausgaben = summe("einnahme"), summe("ausgabe")
    gewinn = [runde(einnahmen[i].abzugsfaehig - ausgaben[i].abzugsfaehig) for i in range(5)]
    return {"jahr": jahr, "zeilen": reihen, "einnahmen": einnahmen, "ausgaben": ausgaben, "gewinn": gewinn,
            "entgangene_vorsteuer": [runde(ausgaben[i].ust) for i in range(5)],
            "monate": monatsverlauf(jahres, kategorien, anlagegueter, jahr, cfg)}


def monatsverlauf(buchungen: list[Buchung], kategorien: dict[int, Kategorie],
                  anlagegueter: list[Anlagegut], jahr: int, cfg: dict) -> list[dict]:
    """12 Monate: Einnahmen, abzugsfähige Ausgaben, entgangene Vorsteuer, kumulierter Gewinn."""
    monate = [{"monat": m, "einnahmen": 0.0, "ausgaben": 0.0, "ust": 0.0} for m in range(1, 13)]
    homeoffice_tage, geschenke = 0, {}
    for b in sorted(buchungen, key=lambda x: (x.datum, x.id or 0)):
        if b.datum.year != jahr or b.status != "bestaetigt":
            continue
        k = kategorien.get(b.kategorie_id or -1)
        if k is None:
            continue
        bw = bewerte(b, k, cfg, {"homeoffice_tage_bisher": homeoffice_tage, "geschenke_je_empfaenger": dict(geschenke)})
        m = meta(b)
        if k.sonderfall == "homeoffice":
            homeoffice_tage += int(m.get("tage") or 0)
        if k.sonderfall == "geschenk":
            e = str(m.get("empfaenger", "")).strip()
            geschenke[e] = geschenke.get(e, 0.0) + b.betrag_brutto
        z = monate[b.datum.month - 1]
        if b.richtung == "einnahme":
            z["einnahmen"] += bw.abzugsfaehig
        else:
            z["ausgaben"] += bw.abzugsfaehig
            z["ust"] += b.ust_betrag + bw.ust_13b
    afa = sum(afa_fuer_jahr(a, jahr) for a in anlagegueter) / 12
    kum = 0.0
    for z in monate:
        z["ausgaben"] += afa
        for f in ("einnahmen", "ausgaben", "ust"):
            z[f] = runde(z[f])
        kum += z["einnahmen"] - z["ausgaben"]
        z["gewinn_kumuliert"] = runde(kum)
    return monate


def eur_zeilen(buchungen: list[Buchung], kategorien: dict[int, Kategorie],
               anlagegueter: list[Anlagegut], jahr: int, cfg: dict) -> list[dict]:
    """Abtippfertige Liste: Zeilennummer, Bezeichnung, Betrag."""
    summen: dict[int, float] = {}
    ue = quartalsuebersicht(buchungen, kategorien, anlagegueter, jahr, cfg)
    for r in ue["zeilen"]:
        z = r["kategorie"].eur_zeile
        if z is None:
            continue
        summen[z] = summen.get(z, 0.0) + r["jahr"].abzugsfaehig
    # Zeile 48: Standard sind die tatsächlichen Zahlungen ans Finanzamt (Kategorie ust_zahlung, fließt oben schon ein).
    # Alternativ (Einstellung „rechnung“) die §13b-Steuer je Rechnung – dann zählen die Zahlungen nicht (bewerte setzt sie auf 0).
    s13b = 0.0
    if ust_basis(cfg) == "rechnung":
        s13b = sum(ust_13b(b, cfg) for b in buchungen if b.datum.year == jahr and b.status == "bestaetigt")
        if s13b:
            summen[48] = summen.get(48, 0.0) + s13b
    # Geschenke-Zeile: nicht abziehbare Anteile sind bereits durch bewerte() auf 0 gesetzt
    bez = cfg["eur_zeilen"]
    out = [{"zeile": z, "bezeichnung": bez.get(str(z), f"Zeile {z}"), "betrag": runde(v)}
           for z, v in sorted(summen.items()) if abs(v) >= 0.005]
    out.append({"zeile": None, "bezeichnung": "Summe Betriebseinnahmen", "betrag": runde(ue["einnahmen"][4].abzugsfaehig)})
    out.append({"zeile": None, "bezeichnung": "Summe Betriebsausgaben", "betrag": runde(ue["ausgaben"][4].abzugsfaehig + s13b)})
    out.append({"zeile": None, "bezeichnung": "Gewinn / Verlust", "betrag": runde(ue["einnahmen"][4].abzugsfaehig - ue["ausgaben"][4].abzugsfaehig - s13b)})
    return out


def ustva(buchungen: list[Buchung], jahr: int, q: int, cfg: dict) -> dict:
    """UStVA je Quartal: nur die §13b-Positionen. Kennzahl → Betrag, plus Einzelpositionen."""
    kz: dict[str, float] = {}
    positionen = []
    for b in buchungen:
        if b.datum.year != jahr or quartal(b.datum) != q or b.status != "bestaetigt" or not b.reverse_charge:
            continue
        basis_kz, steuer_kz = ustva_kennzahlen_fuer(b, cfg)
        steuer = ust_13b(b, cfg)
        kz[basis_kz] = kz.get(basis_kz, 0.0) + b.betrag_netto
        kz[steuer_kz] = kz.get(steuer_kz, 0.0) + steuer
        positionen.append({"buchung": b, "kz_basis": basis_kz, "kz_steuer": steuer_kz, "steuer": steuer})
    return {"jahr": jahr, "quartal": q, "kennzahlen": {k: runde(v) for k, v in sorted(kz.items())},
            "positionen": positionen, "zahllast": runde(sum(p["steuer"] for p in positionen))}


def konfidenz_aus_feldern(felder: dict) -> float:
    """Konfidenz aus der Vollständigkeit der Felder ableiten, nicht vom Modell schätzen lassen."""
    gewichte = {"datum": 0.25, "betrag_brutto": 0.30, "lieferant": 0.20, "rechnungsnummer": 0.10,
                "ust_satz": 0.10, "ust_idnr": 0.05}
    score = 0.0
    for feld, g in gewichte.items():
        v = felder.get(feld)
        if v not in (None, "", 0, 0.0) or (feld == "ust_satz" and v == 0.0 and felder.get("reverse_charge")):
            score += g
    return runde(min(1.0, score))
