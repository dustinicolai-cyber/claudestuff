"""Betrag- und Datum-Parser (aus Steuerfuchs übernommen, nur Regex)."""
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


