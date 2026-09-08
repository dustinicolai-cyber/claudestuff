"""Deterministische Feldextraktion aus Rechnungstext (Stufe 2, auch Nachbearbeitung
der OCR-Ausgabe). Nur Regex, keine KI – wiederholbar und nachvollziehbar.
"""
from __future__ import annotations

import re
from datetime import date

MONATE = {
    "januar": 1, "jan": 1, "february": 2, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mar": 3, "march": 3,
    "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "jun": 6, "june": 6, "juli": 7, "jul": 7, "july": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "oct": 10, "october": 10,
    "november": 11, "nov": 11, "dezember": 12, "dez": 12, "dec": 12, "december": 12,
}

RE_DATUM_NUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\b")
RE_DATUM_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_DATUM_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
RE_DATUM_WORT = re.compile(r"\b(\d{1,2})\.?\s+([A-Za-zäöüÄÖÜ]{3,9})\.?\s+(\d{4})\b")
RE_DATUM_WORT_EN = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
RE_DATUM_MON = re.compile(r"\b(\d{1,2})[-\s]([A-Za-z]{3})[-\s](\d{4})\b")   # 02-JAN-2025
DATUM_KEYWORDS = re.compile(r"rechnungsdatum|belegdatum|invoice date|date of issue|datum|date|ausgestellt|issued", re.I)

# Betrag: 1.234,56 | 1234,56 | 1,234.56 | 1234.56 | 12,- – immer mit Nachkommastellen oder „,-“.
# Bewusst KEINE Ganzzahlen mit Tausenderpunkten (114.103.475): das sind Steuer-, Kunden-
# oder Telefonnummern, keine Beträge. Ganzzahlen zählen nur direkt neben € / EUR.
RE_BETRAG = re.compile(r"(?<![\d,./-])(-?\d{1,3}(?:[.,]\d{3})+[.,]\d{2}|-?\d+[,.]\d{2}|-?\d+,-|"
                       r"(?<=€\s)\d{1,6}(?![\d,.])|(?<=EUR\s)\d{1,6}(?![\d,.])|\d{1,6}(?=\s?(?:€|EUR\b)))(?![\d])")
BETRAG_MAX_PLAUSIBEL = 1_000_000.0
RE_WAEHRUNG = re.compile(r"€|EUR\b|Euro\b", re.I)

BRUTTO_KEYS = re.compile(r"gesamtbetrag|rechnungsbetrag|zu zahlen|zahlbetrag|endbetrag|bruttobetrag|summe brutto|"
                         r"gesamtsumme|gesamt\b|total amount|amount due|grand total|total due|\btotal\b|betrag\b|"
                         r"amount paid|charged|summe\b", re.I)
NETTO_KEYS = re.compile(r"nettobetrag|summe netto|netto\b|zwischensumme|subtotal|net amount|net total|sub-total", re.I)
UST_KEYS = re.compile(r"umsatzsteuer|mehrwertsteuer|mwst|ust\b|u\.st|vat\b|tax\b|steuer\b", re.I)
RE_PROZENT = re.compile(r"(\d{1,2}(?:[,.]\d{1,2})?)\s?%")

RE_USTID = re.compile(r"\b(DE\s?\d{9}|ATU\s?\d{8}|NL\s?\d{9}\s?B\s?\d{2}|IE\s?\d{7}[A-Z]{1,2}|FR\s?[A-Z0-9]{2}\s?\d{9}|"
                      r"GB\s?\d{9}|LU\s?\d{8}|BE\s?0?\d{9}|ES\s?[A-Z0-9]\d{7}[A-Z0-9]|IT\s?\d{11}|PL\s?\d{10}|"
                      r"SE\s?\d{12}|DK\s?\d{8}|FI\s?\d{8}|CZ\s?\d{8,10}|EU\s?\d{9}|CHE[-\s]?\d{3}\.?\d{3}\.?\d{3})\b")
RE_USTID_KONTEXT = re.compile(r"(?i:ust[-.\s]?id(?:nr)?\.?|umsatzsteuer[-\s]?id(?:entifikationsnummer)?|vat[ \t]*(?:id|no|number|reg(?:istration)?)?\.?|uid)[ \t]*[:.]?[ \t]*"
                              r"((?=[A-Z0-9 -]*\d{2})[A-Z]{2,3}[ -]?[A-Z0-9]{7,14})\b")

RE_RECHNUNGSNR = re.compile(r"(?:rechnungs?[-\s]?(?:nummer|nr\.?|no\.?)|invoice\s*(?:no\.?|number|#|id)|beleg[-\s]?nr\.?|"
                            r"receipt\s*(?:no\.?|number|#)|order\s*(?:no\.?|number|#)|bestell[-\s]?nr\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_.]{2,30})", re.I)

FIRMEN_SUFFIX = re.compile(r"\b(GmbH|AG|UG|KG|OHG|GbR|e\.\s?K\.|e\.V\.|Inc\.?|Ltd\.?|LLC|B\.V\.|S\.A\.|S\.L\.|Limited|"
                           r"Co\.|Corp\.?|SE|SAS|SARL|Oy|AB|ApS|s\.r\.o\.|Sp\. z o\.o\.|PLC|LP|Ireland|International)\b")


def parse_betrag(s: str) -> float | None:
    s = s.strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-")
    s = s.lstrip("-")
    if s.endswith(",-"):
        s = s[:-2] + ",00"
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):     # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                                # 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        teile = s.split(",")
        if len(teile[-1]) == 3 and len(teile) > 1 and all(len(t) == 3 for t in teile[1:]):
            s = s.replace(",", "")           # 1,234 (englische Tausender)
        else:
            s = s.replace(",", ".")
    elif "." in s:
        teile = s.split(".")
        if len(teile[-1]) == 3 and len(teile) > 1 and all(len(t) == 3 for t in teile[1:]):
            s = s.replace(".", "")           # 1.234 (deutsche Tausender)
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_datum(text: str) -> date | None:
    for m in RE_DATUM_ISO.finditer(text):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue
    for m in RE_DATUM_NUM.finditer(text):
        t, mo, j = int(m[1]), int(m[2]), int(m[3])
        if j < 100:
            j += 2000
        try:
            return date(j, mo, t)
        except ValueError:
            continue
    for m in RE_DATUM_MON.finditer(text):
        mo = MONATE.get(m[2].lower())
        if mo:
            try:
                return date(int(m[3]), mo, int(m[1]))
            except ValueError:
                continue
    for m in RE_DATUM_WORT.finditer(text):
        mo = MONATE.get(m[2].lower().rstrip("."))
        if mo:
            try:
                return date(int(m[3]), mo, int(m[1]))
            except ValueError:
                continue
    for m in RE_DATUM_WORT_EN.finditer(text):
        mo = MONATE.get(m[1].lower().rstrip("."))
        if mo:
            try:
                return date(int(m[3]), mo, int(m[2]))
            except ValueError:
                continue
    for m in RE_DATUM_US.finditer(text):
        try:
            return date(int(m[3]), int(m[1]), int(m[2]))
        except ValueError:
            continue
    return None


def finde_datum(text: str) -> date | None:
    """Datum bevorzugt aus einer Zeile mit Datums-Schlüsselwort, sonst erstes plausibles."""
    zeilen = text.splitlines()
    for i, z in enumerate(zeilen):
        if DATUM_KEYWORDS.search(z):
            d = parse_datum(z) or (parse_datum(zeilen[i + 1]) if i + 1 < len(zeilen) else None)
            if d:
                return d
    kandidaten = [d for d in (parse_datum(z) for z in zeilen) if d and 2000 <= d.year <= 2100]
    return kandidaten[0] if kandidaten else None


def betraege_in_zeile(z: str) -> list[float]:
    out = []
    for m in RE_BETRAG.finditer(z):
        v = parse_betrag(m[1])
        if v is not None:
            out.append(v)
    return out


def finde_betrag_mit_keyword(text: str, keys: re.Pattern) -> float | None:
    """Betrag aus Zeilen mit Schlüsselwort. Gleiche Zeile schlägt Folgezeile; die letzte
    Treffer-Zeile gewinnt, weil Summen unten stehen (Tabellenköpfe oben tragen keine Zahl)."""
    zeilen = text.splitlines()
    gleiche: list[float] = []
    folge: list[float] = []
    for i, z in enumerate(zeilen):
        if not keys.search(z):
            continue
        b = betraege_in_zeile(z)
        if b:
            gleiche.append(b[-1])
        elif i + 1 < len(zeilen):
            b2 = betraege_in_zeile(zeilen[i + 1])
            if len(b2) == 1:
                folge.append(b2[0])
    if gleiche:
        return gleiche[-1]
    return folge[-1] if folge else None


SAETZE_GUELTIG = (0.0, 5.0, 7.0, 16.0, 19.0, 20.0, 21.0, 23.0)


def finde_ust(text: str) -> tuple[float | None, float | None]:
    """(Satz in %, Betrag) aus Zeilen mit USt-Schlüsselwort; Satz notfalls aus dem ganzen Text."""
    satz, betrag = _finde_ust_zeilen(text)
    if satz is None:
        for m in RE_PROZENT.finditer(text):
            try:
                v = float(m[1].replace(",", "."))
            except ValueError:
                continue
            if v in SAETZE_GUELTIG and v > 0:
                satz = v
                break
    return satz, betrag


def _finde_ust_zeilen(text: str) -> tuple[float | None, float | None]:
    satz = betrag = None
    for z in text.splitlines():
        if not UST_KEYS.search(z):
            continue
        p = RE_PROZENT.search(z)
        if p:
            try:
                s = float(p[1].replace(",", "."))
                if s in SAETZE_GUELTIG:
                    satz = s if satz is None else satz
            except ValueError:
                pass
        # Betrag = letzte Zahl in der Zeile, die kein Prozentsatz ist
        z_ohne_prozent = RE_PROZENT.sub(" ", z)
        b = betraege_in_zeile(z_ohne_prozent)
        if len(b) == 1:            # eine Zahl in einer USt-Zeile = der USt-Betrag; Positionszeilen haben mehrere
            betrag = b[0]
    return satz, betrag


def finde_ust_idnr(text: str) -> list[str]:
    ids: list[str] = []
    for m in RE_USTID.finditer(text):
        v = re.sub(r"[\s.-]", "", m[1]).upper()
        if v not in ids:
            ids.append(v)
    for m in RE_USTID_KONTEXT.finditer(text):
        v = re.sub(r"[\s.-]", "", m[1]).upper()
        if re.fullmatch(r"[A-Z]{2,3}[A-Z0-9]{7,14}", v) and v not in ids:
            ids.append(v)
    return ids


def finde_rechnungsnummer(text: str) -> str:
    m = RE_RECHNUNGSNR.search(text)
    return m[1].strip(".") if m else ""


def finde_lieferant(text: str, bekannte: list[str]) -> str:
    unten = text.lower()
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    for name in bekannte:
        if name in unten:
            for z in zeilen[:30]:
                if name in z.lower() and FIRMEN_SUFFIX.search(z) and len(z) <= 80:
                    # Firmenzeile kann mit anderen Spalten verschmolzen sein: bis zum Suffix schneiden
                    start = z.lower().find(name)
                    treffer = [m for m in FIRMEN_SUFFIX.finditer(z) if m.end() - start <= 70]
                    return z[start:treffer[-1].end()].strip()
            return name.title()
    for z in zeilen[:25]:
        if FIRMEN_SUFFIX.search(z) and len(z) <= 80 and not RE_BETRAG.search(z):
            return z
    for z in zeilen[:5]:
        if 2 < len(z) <= 60 and not RE_BETRAG.search(z) and not parse_datum(z) and not DATUM_KEYWORDS.search(z) \
                and not re.search(r"rechnung|invoice|seite|page", z, re.I):
            return z
    return ""


def extrahiere_felder(text: str, cfg: dict) -> dict:
    """Alle Felder als dict; fehlende Felder sind None. Rohdaten für extraktion_json."""
    from ..steuerlogik import RC_HINWEISE
    text = text or ""
    ids = finde_ust_idnr(text)
    fremd = [i for i in ids if not i.startswith("DE")]
    ust_idnr = fremd[0] if fremd else (ids[0] if ids else "")
    satz, ust_betrag = finde_ust(text)
    brutto = finde_betrag_mit_keyword(text, BRUTTO_KEYS)
    netto = finde_betrag_mit_keyword(text, NETTO_KEYS)
    if brutto is None or abs(brutto) > BETRAG_MAX_PLAUSIBEL:
        alle = [v for z in text.splitlines() for v in betraege_in_zeile(z) if abs(v) <= BETRAG_MAX_PLAUSIBEL]
        brutto = max(alle, key=abs) if alle else None
    if netto is not None and abs(netto) > BETRAG_MAX_PLAUSIBEL:
        netto = None
    if brutto is not None and netto is not None and abs(netto) > abs(brutto):
        netto, brutto = brutto, netto
    rc_hinweis = bool(RC_HINWEISE.search(text))
    if rc_hinweis and ust_betrag in (None, 0.0) and satz is None:
        satz, ust_betrag = 0.0, 0.0
    return {
        "datum": finde_datum(text),
        "betrag_brutto": brutto,
        "betrag_netto": netto,
        "ust_satz": satz,
        "ust_betrag": ust_betrag,
        "ust_idnr": ust_idnr,
        "alle_ust_idnr": ids,
        "rechnungsnummer": finde_rechnungsnummer(text),
        "lieferant": finde_lieferant(text, cfg.get("reverse_charge_lieferanten", [])),
        "reverse_charge_hinweis": rc_hinweis,
        "waehrung_eur": bool(RE_WAEHRUNG.search(text)),
    }
