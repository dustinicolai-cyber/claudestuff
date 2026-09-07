"""Kontoauszüge: CSV (deutsche Bankexporte, Spalten heuristisch erkannt) und CAMT.053."""
from __future__ import annotations

import csv
import hashlib
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

from .textfelder import parse_betrag, parse_datum


@dataclass
class Bewegung:
    datum: date
    betrag: float
    verwendungszweck: str = ""
    gegenkonto: str = ""
    gegen_iban: str = ""

    def fingerprint(self) -> str:
        roh = f"{self.datum.isoformat()}|{self.betrag:.2f}|{self.verwendungszweck.strip().lower()}|{self.gegenkonto.strip().lower()}"
        return hashlib.sha1(roh.encode("utf-8")).hexdigest()


SPALTEN = {
    "datum": ["buchungstag", "buchungsdatum", "buchung", "datum", "valutadatum", "wertstellung", "valuta", "date", "booking date", "transaction date"],
    "betrag": ["betrag", "umsatz", "amount", "betrag (eur)", "betrag eur", "amount (eur)", "value"],
    "soll": ["soll", "debit", "ausgang", "lastschrift"],
    "haben": ["haben", "credit", "eingang", "gutschrift"],
    "zweck": ["verwendungszweck", "buchungstext", "beschreibung", "description", "purpose", "reference", "payment reference", "text", "vorgang"],
    "gegen": ["beguenstigter/zahlungspflichtiger", "begünstigter/zahlungspflichtiger", "auftraggeber / begünstigter", "auftraggeber/empfänger",
              "name zahlungsbeteiligter", "zahlungsbeteiligter", "empfänger", "empfaenger", "auftraggeber", "beguenstigter", "begünstigter",
              "payee", "payer", "counterparty", "name", "partner name", "gegenpartei", "beneficiary"],
    "iban": ["iban zahlungsbeteiligter", "kontonummer/iban", "iban", "kontonummer", "account number", "partner iban"],
}


def _finde_spalte(header: list[str], kandidaten: list[str]) -> int | None:
    norm = [h.strip().lower().strip('"') for h in header]
    for k in kandidaten:
        for i, h in enumerate(norm):
            if h == k:
                return i
    for k in kandidaten:
        for i, h in enumerate(norm):
            if k in h:
                return i
    return None


def _decode(daten: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return daten.decode(enc)
        except UnicodeDecodeError:
            continue
    return daten.decode("latin-1", errors="replace")


def lese_csv(daten: bytes) -> list[Bewegung]:
    text = _decode(daten)
    zeilen = [z for z in text.splitlines() if z.strip()]
    if not zeilen:
        return []
    # Kopfzeile finden: erste Zeile, die eine Datumsspalte benennt (viele Banken haben Metadaten oben)
    start = 0
    for i, z in enumerate(zeilen[:30]):
        u = z.lower()
        if any(k in u for k in ("buchungstag", "buchungsdatum", "datum", "date", "valuta")) and \
                any(k in u for k in ("betrag", "umsatz", "amount", "soll", "haben", "debit", "credit")):
            start = i
            break
    probe = "\n".join(zeilen[start:start + 5])
    try:
        dialekt = csv.Sniffer().sniff(probe, delimiters=";,\t|")
        trenner = dialekt.delimiter
    except csv.Error:
        trenner = ";" if probe.count(";") >= probe.count(",") else ","
    reader = csv.reader(io.StringIO("\n".join(zeilen[start:])), delimiter=trenner, quotechar='"')
    rows = list(reader)
    if len(rows) < 2:
        return []
    header = rows[0]
    i_datum = _finde_spalte(header, SPALTEN["datum"])
    i_betrag = _finde_spalte(header, SPALTEN["betrag"])
    i_soll = _finde_spalte(header, SPALTEN["soll"])
    i_haben = _finde_spalte(header, SPALTEN["haben"])
    i_zweck = _finde_spalte(header, SPALTEN["zweck"])
    i_gegen = _finde_spalte(header, SPALTEN["gegen"])
    i_iban = _finde_spalte(header, SPALTEN["iban"])
    if i_datum is None or (i_betrag is None and i_soll is None and i_haben is None):
        return []

    out: list[Bewegung] = []
    for r in rows[1:]:
        if len(r) <= i_datum:
            continue
        d = parse_datum(r[i_datum])
        if not d:
            continue
        betrag = None
        if i_betrag is not None and i_betrag < len(r):
            betrag = parse_betrag(r[i_betrag].replace("€", "").replace("EUR", ""))
        if betrag is None and (i_soll is not None or i_haben is not None):
            soll = parse_betrag(r[i_soll]) if i_soll is not None and i_soll < len(r) and r[i_soll].strip() else None
            haben = parse_betrag(r[i_haben]) if i_haben is not None and i_haben < len(r) and r[i_haben].strip() else None
            if soll is not None:
                betrag = -abs(soll)
            elif haben is not None:
                betrag = abs(haben)
        if betrag is None:
            continue
        # Manche Exporte kennzeichnen Soll/Haben in einer Extraspalte
        i_sh = _finde_spalte(header, ["soll/haben", "s/h", "debit/credit", "dc"])
        if i_sh is not None and i_sh < len(r) and r[i_sh].strip().upper() in ("S", "D", "SOLL", "DEBIT") and betrag > 0:
            betrag = -betrag
        out.append(Bewegung(
            datum=d, betrag=round(betrag, 2),
            verwendungszweck=(r[i_zweck].strip() if i_zweck is not None and i_zweck < len(r) else ""),
            gegenkonto=(r[i_gegen].strip() if i_gegen is not None and i_gegen < len(r) else ""),
            gegen_iban=(r[i_iban].strip() if i_iban is not None and i_iban < len(r) else ""),
        ))
    return out


def _lokal(tag: str) -> str:
    return tag.split("}")[-1]


def _alle(el: ET.Element, name: str):
    return [c for c in el.iter() if _lokal(c.tag) == name]


def _erst(el: ET.Element | None, *pfad: str) -> ET.Element | None:
    for name in pfad:
        if el is None:
            return None
        el = next((c for c in el if _lokal(c.tag) == name), None)
    return el


def _txt(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None and el.text else ""


def lese_camt053(daten: bytes) -> list[Bewegung]:
    try:
        root = ET.fromstring(daten)
    except ET.ParseError:
        return []
    out: list[Bewegung] = []
    for ntry in _alle(root, "Ntry"):
        amt = _erst(ntry, "Amt")
        betrag = parse_betrag(_txt(amt).replace(",", ".")) if amt is not None else None
        if betrag is None:
            continue
        if _txt(_erst(ntry, "CdtDbtInd")) == "DBIT":
            betrag = -abs(betrag)
        d = parse_datum(_txt(_erst(ntry, "BookgDt", "Dt")) or _txt(_erst(ntry, "ValDt", "Dt")) or _txt(_erst(ntry, "BookgDt", "DtTm")))
        if not d:
            continue
        zweck = " ".join(_txt(u) for u in _alle(ntry, "Ustrd") if _txt(u)) or _txt(_erst(ntry, "AddtlNtryInf"))
        gegen, iban = "", ""
        for tx in _alle(ntry, "TxDtls"):
            rltd = _erst(tx, "RltdPties")
            if rltd is None:
                continue
            partei = _erst(rltd, "Cdtr") if betrag < 0 else _erst(rltd, "Dbtr")
            # CAMT 2019+: Pty-Unterelement
            name = _txt(_erst(partei, "Nm")) or _txt(_erst(partei, "Pty", "Nm"))
            acct = _erst(rltd, "CdtrAcct") if betrag < 0 else _erst(rltd, "DbtrAcct")
            iban = _txt(_erst(acct, "Id", "IBAN"))
            gegen = name
            break
        out.append(Bewegung(datum=d, betrag=round(betrag, 2), verwendungszweck=zweck, gegenkonto=gegen, gegen_iban=iban))
    return out


def lese_kontoauszug(daten: bytes, name: str) -> list[Bewegung]:
    if name.lower().endswith(".xml") or daten.lstrip().startswith(b"<"):
        return lese_camt053(daten)
    return lese_csv(daten)
