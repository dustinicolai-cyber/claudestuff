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
RE_WAEHRUNG = re.compile(r"€|EUR\b|Euro\b|\$|USD\b|US-?Dollar", re.I)
RE_EURO = re.compile(r"€|EUR\b|Euro\b", re.I)
RE_DOLLAR = re.compile(r"\$|USD\b|US-?Dollar", re.I)


def erkenne_waehrung(text: str) -> str:
    """USD nur, wenn Dollar-Zeichen klar überwiegen – Rechnungen nennen oft beide Währungen."""
    euro = len(RE_EURO.findall(text)); dollar = len(RE_DOLLAR.findall(text))
    return "USD" if dollar > euro else "EUR"

# Stark = eindeutig die Endsumme; schwach = kann auch Zwischensumme oder Tabellenkopf sein.
BRUTTO_STARK = re.compile(r"gesamtbetrag|rechnungsbetrag|zu zahlen(?:der betrag)?|zahlbetrag|endbetrag|bruttobetrag|summe brutto|"
                          r"gesamtsumme|gesamtpreis|total amount|amount due|grand total|total due|amount paid|invoice total|"
                          r"zahlungsbetrag|forderungsbetrag|einzugsbetrag", re.I)
BRUTTO_SCHWACH = re.compile(r"\bgesamt\b|\btotal\b|\bbetrag\b|\bsumme\b|charged", re.I)
BRUTTO_KEYS = re.compile(BRUTTO_STARK.pattern + "|" + BRUTTO_SCHWACH.pattern, re.I)
NETTO_STARK = re.compile(r"nettobetrag|summe netto|zwischensumme|subtotal|sub-total|net amount|net total|nettosumme", re.I)
NETTO_SCHWACH = re.compile(r"\bnetto\b|\bnet\b", re.I)
NETTO_KEYS = re.compile(NETTO_STARK.pattern + "|" + NETTO_SCHWACH.pattern, re.I)
# Zahlen mit Einheit sind keine Beträge (Datenvolumen, Prozent, Laufzeiten)
RE_EINHEIT_DANACH = re.compile(r"^\s?(?:GB|MB|KB|TB|kWh|Std\.?|Min\.?|min|km|%|Stk\.?|St\.|Monate?|Tage?|h)\b", re.I)
UST_KEYS = re.compile(r"umsatzsteuer|mehrwertsteuer|mwst|ust\b|u\.st|vat\b|tax\b|steuer\b", re.I)
RE_PROZENT = re.compile(r"(\d{1,2}(?:[,.]\d{1,2})?)\s?%")

RE_USTID = re.compile(r"\b(DE\s?\d{9}|ATU\s?\d{8}|NL\s?\d{9}\s?B\s?\d{2}|IE\s?\d{7}[A-Z]{1,2}|FR\s?[A-Z0-9]{2}\s?\d{9}|"
                      r"GB\s?\d{9}|LU\s?\d{8}|BE\s?0?\d{9}|ES\s?[A-Z0-9]\d{7}[A-Z0-9]|IT\s?\d{11}|PL\s?\d{10}|"
                      r"SE\s?\d{12}|DK\s?\d{8}|FI\s?\d{8}|CZ\s?\d{8,10}|EU\s?\d{9}|CHE[-\s]?\d{3}\.?\d{3}\.?\d{3})\b")
RE_USTID_KONTEXT = re.compile(r"(?i:ust[-.\s]?id(?:nr)?\.?|umsatzsteuer[-\s]?id(?:entifikationsnummer)?|vat[ \t]*(?:id|no|number|reg(?:istration)?)?\.?|uid)[ \t]*[:.]?[ \t]*"
                              r"((?=[A-Z0-9 -]*\d{2})[A-Z]{2,3}[ -]?[A-Z0-9]{7,14})\b")

RE_RECHNUNGSNR = re.compile(r"(?:rechnungs?[-\s]?(?:nummer|nr\.?|no\.?)|invoice\s*(?:no\.?|number|#|id)|beleg[-\s]?nr\.?|"
                            r"receipt\s*(?:no\.?|number|#)|order\s*(?:no\.?|number|#)|bestell[-\s]?nr\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_.]{2,30})", re.I)

FIRMEN_SUFFIX = re.compile(r"(?:\bGmbH\s*&\s*Co\.\s*KG|\bSE\s*&\s*Co\.\s*KG|S\.?\s?à\s?r\.?\s?l\.?|S\.?\s?a\.?\s?r\.?\s?[lL]\.?|"
                           r"\b(?:GmbH|AG|UG|KG|OHG|GbR|e\.\s?K\.|e\.V\.|Inc\.?|Ltd\.?|LLC|B\.V\.|S\.A\.|S\.L\.|Limited|"
                           r"Co\.|Corp\.?|SE|SAS|SARL|Oy|AB|ApS|s\.r\.o\.|Sp\. z o\.o\.|PLC|LP|Ireland|International)\b)")
VERKAEUFER_PREFIX = re.compile(r"(?:verkauft von|verkäufer|rechnungssteller|leistungserbringer|sold by|seller)\s*:?\s*", re.I)
KEIN_LIEFERANT = re.compile(r"mandat|kundennummer|kunden-nr|rechnung|invoice|seite\b|page\b|datum|date|vertrag|iban|ust|vat|steuer|"
                            r"zahlungsreferenz|bestell|order|lieferadresse|rechnungsadresse|telefon|e-mail|www\.|@", re.I)


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
    """Geldbeträge einer Zeile. Zahlen mit Einheit (GB, %, Std.) fallen raus; steht ein €/EUR in der
    Zeile, zählen nur Zahlen direkt neben einer Währungsangabe."""
    hat_waehrung = bool(RE_WAEHRUNG.search(z))
    out = []
    for m in RE_BETRAG.finditer(z):
        rest = z[m.end():]
        if RE_EINHEIT_DANACH.match(rest):
            continue
        if hat_waehrung:
            davor = z[max(0, m.start() - 5):m.start()]
            if not (RE_WAEHRUNG.search(rest[:5]) or RE_WAEHRUNG.search(davor)):
                continue
        v = parse_betrag(m[1])
        if v is not None:
            out.append(v)
    return out


def finde_betrag_mit_keyword(text: str, keys: re.Pattern, stark: re.Pattern | None = None) -> float | None:
    """Betrag aus Zeilen mit Schlüsselwort. Starke Schlüsselwörter (Zahlbetrag, Gesamtbetrag …) schlagen
    schwache (Summe, Gesamt …); innerhalb einer Stufe gewinnt die letzte Zeile, weil Summen unten stehen.
    Gleiche Zeile schlägt Folgezeile."""
    zeilen = text.splitlines()
    treffer: list[tuple[int, int, float]] = []   # (rang, zeilenindex, betrag)
    for i, z in enumerate(zeilen):
        if not keys.search(z):
            continue
        rang = 2 if (stark and stark.search(z)) else 1
        b = betraege_in_zeile(z)
        if b:
            treffer.append((rang * 2, i, b[-1]))
        elif i + 1 < len(zeilen):
            b2 = betraege_in_zeile(zeilen[i + 1])
            if len(b2) == 1:
                treffer.append((rang * 2 - 1, i, b2[0]))
    if not treffer:
        return None
    treffer.sort(key=lambda t: (t[0], t[1]))
    return treffer[-1][2]


RE_PROZENT_SPALTE = re.compile(r"(?:steuer|ust\.?|mwst\.?|vat|tax)[-\s]*(?:satz|%|\(%\)|rate)", re.I)
SPALTEN_KOPF = {
    "netto": re.compile(r"\bnetto\b|zwischensumme|\bnet\b|ohne ust|excl", re.I),
    "steuer": re.compile(r"\bsteuer\b|\bust\.?\b|mwst|\bvat\b|\btax\b", re.I),
    "brutto": re.compile(r"\bbrutto\b|inkl\.? ust|\bgross\b|\btotal\b|gesamt", re.I),
}


def tabelle_zuordnen(text: str) -> dict:
    """Steuertabellen: Kopfzeile mit Netto/Steuer/Brutto, darunter eine Zahlenzeile.
    Die Spaltenreihenfolge im Kopf bestimmt, welche Zahl was ist. Letzte passende Tabelle gewinnt."""
    zeilen = text.splitlines()
    ergebnis: dict = {}
    for i, z in enumerate(zeilen[:-1]):
        # Prozent-Spalten („Steuer %“, „UST-SATZ“, „MwSt (%)“) sind keine Betragsspalten
        kopf = RE_PROZENT_SPALTE.sub(" ", z)
        spalten = []
        for name, muster in SPALTEN_KOPF.items():
            m = muster.search(kopf)
            if m:
                spalten.append((m.start(), name))
        namen = [n for _, n in sorted(spalten)]
        if len(namen) < 2 or "steuer" not in namen or len(set(namen)) != len(namen):
            continue
        if betraege_in_zeile(z):
            continue                      # Kopfzeilen tragen keine Beträge
        for j in range(i + 1, min(i + 4, len(zeilen))):
            betraege = betraege_in_zeile(zeilen[j])
            if not betraege:
                continue
            if len(betraege) >= len(namen):
                kandidat = dict(zip(namen, betraege[-len(namen):]))
            elif len(betraege) == len(namen) - 1 and "brutto" in namen:
                kandidat = dict(zip([n for n in namen if n != "brutto"], betraege))
            else:
                break
            n, st, br = kandidat.get("netto"), kandidat.get("steuer"), kandidat.get("brutto")
            if n is not None and st is not None and st > n:
                break
            if n is not None and st is not None and br is not None and abs(n + st - br) > 0.05:
                break
            ergebnis = kandidat
            break
    return ergebnis


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


def _firma_aus_zeile(z: str, start: int = 0) -> str:
    """Firmenname aus einer (evtl. mit Spalten verschmolzenen) Zeile: bis zum Suffix, ab einem sinnvollen Anfang."""
    treffer = [m for m in FIRMEN_SUFFIX.finditer(z) if m.start() >= start]
    if not treffer:
        return ""
    m = treffer[0]
    ende = m.end()
    # Folgesuffixe mitnehmen: „Ireland Ltd“, „GmbH & Co. KG“
    while True:
        w = re.match(r"\s+", z[ende:])
        nxt = FIRMEN_SUFFIX.match(z, ende + (w.end() if w else 0)) if w else None
        if not nxt:
            break
        ende = nxt.end()
    kopf = z[start:m.start()]
    kopf = re.split(r"[•|:]|\s{3,}", kopf)[-1]
    kopf = kopf[-60:]
    kopf = re.sub(r"^[^A-Za-zÄÖÜäöü0-9]+", "", kopf)
    name = (kopf + z[m.start():ende]).strip(" ,-")
    return name if len(name) >= 4 else ""


def finde_lieferant(text: str, bekannte: list[str], weitere: list[str] | None = None) -> str:
    unten = text.lower()
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    # 1) „Verkauft von …“ / „Rechnungssteller …“
    for z in zeilen[:40]:
        m = VERKAEUFER_PREFIX.match(z)
        if m:
            rest = z[m.end():].strip()
            firma = _firma_aus_zeile(rest)
            if firma:
                # Zusatz wie „, Niederlassung Deutschland“ mitnehmen, wenn er direkt folgt
                nach = rest[rest.find(firma) + len(firma):]
                zusatz = re.match(r",\s*([A-ZÄÖÜ][\w .-]{2,40})", nach)
                return firma + (", " + zusatz.group(1).strip() if zusatz else "")
            firma = re.split(r"\s{2,}|,", rest)[0].strip()
            if 3 <= len(firma) <= 80 and not RE_BETRAG.search(firma):
                return firma
    # 2) bekannte Anbieter
    for name in list(bekannte) + list(weitere or []):
        if name in unten:
            for z in zeilen[:40]:
                if name in z.lower() and FIRMEN_SUFFIX.search(z):
                    firma = _firma_aus_zeile(z, z.lower().find(name))
                    if firma:
                        return firma
            return name.title()
    # 3) Firmenzeile mit Suffix oben im Dokument
    for z in zeilen[:30]:
        if FIRMEN_SUFFIX.search(z) and not RE_BETRAG.search(z) and not KEIN_LIEFERANT.search(z[:20]):
            firma = _firma_aus_zeile(z)
            if firma:
                return firma
    # 4) Zeile mit der USt-IdNr des Ausstellers (Fußzeile)
    for z in zeilen:
        if RE_USTID.search(z) and FIRMEN_SUFFIX.search(z):
            firma = _firma_aus_zeile(z)
            if firma:
                return firma
    # 5) erste unverdächtige Zeile
    for z in zeilen[:6]:
        if 2 < len(z) <= 60 and not RE_BETRAG.search(z) and not parse_datum(z) and not KEIN_LIEFERANT.search(z):
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
    brutto = finde_betrag_mit_keyword(text, BRUTTO_KEYS, BRUTTO_STARK)
    netto = finde_betrag_mit_keyword(text, NETTO_KEYS, NETTO_STARK)
    tabelle = tabelle_zuordnen(text)
    if tabelle:
        # Steuertabelle ist die verlässlichste Quelle für Netto und Steuer
        netto = tabelle.get("netto", netto)
        ust_betrag = tabelle.get("steuer", ust_betrag)
        stark_vorhanden = any(BRUTTO_STARK.search(z) and betraege_in_zeile(z) for z in text.splitlines())
        if brutto is None or (tabelle.get("brutto") is not None and not stark_vorhanden):
            brutto = tabelle.get("brutto", brutto)
    if brutto is not None and netto is not None and ust_betrag is not None and abs(netto + ust_betrag - brutto) < 0.05 and satz is None:
        satz = float(round(ust_betrag / netto * 100)) if netto else 0.0
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
        "lieferant": finde_lieferant(text, cfg.get("reverse_charge_lieferanten", []), cfg.get("bekannte_lieferanten", [])),
        "reverse_charge_hinweis": rc_hinweis,
        "waehrung_eur": bool(RE_EURO.search(text)),
        "waehrung": erkenne_waehrung(text),
    }
