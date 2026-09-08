"""Pfade und Laden der Regel-Konfiguration.

Alles liegt im Nutzerverzeichnis unter ~/Steuertool (überschreibbar per
STEUERTOOL_HOME). Die steuerregeln.json wird beim ersten Start dorthin kopiert,
damit der Nutzer Grenzwerte anpassen kann, ohne im Code zu wühlen.
"""
from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_REGELN = APP_DIR / "steuerregeln.json"


@lru_cache(maxsize=1)
def version() -> str:
    """Build-Kennung aus der Datei VERSION (beim Packen geschrieben), sonst „dev“. Einmal beim Start gelesen,
    damit ein laufender Server die Version meldet, mit der er gestartet wurde."""
    p = APP_DIR.parent / "VERSION"
    try:
        return p.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def home_dir() -> Path:
    d = Path(os.environ.get("STEUERTOOL_HOME", Path.home() / "Steuertool"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def beleg_dir() -> Path:
    d = home_dir() / "Belege"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return home_dir() / "steuertool.db"


def regeln_path() -> Path:
    p = home_dir() / "steuerregeln.json"
    if not p.exists():
        shutil.copy(DEFAULT_REGELN, p)
    return p


# Frühere Standardwerte, die eine neuere Version korrigiert hat: steht in der Nutzerdatei noch genau der alte Wert,
# hat die Nutzerin ihn nicht bewusst geändert – dann gilt der neue Standard. Eigene Anpassungen bleiben erhalten.
_ALTE_STANDARDWERTE = {"fahrtkosten": {"eur_zeile": 59}}


def _kategorie_zusammenfuehren(standard: dict, nutzer: dict) -> dict:
    out = dict(standard)
    alt = _ALTE_STANDARDWERTE.get(standard.get("schluessel"), {})
    for k, v in nutzer.items():
        if k in alt and v == alt[k] and k in standard:
            continue  # alter Standard, nicht bewusst geändert → neuer Standard gilt
        out[k] = v
    return out


def _zusammenfuehren(standard, nutzer):
    """Nutzerdatei gewinnt; was dort fehlt, kommt aus der mitgelieferten Datei (neue Schlüssel, neue Kategorien, Beispiele)."""
    if isinstance(standard, dict) and isinstance(nutzer, dict):
        out = dict(standard)
        for k, v in nutzer.items():
            out[k] = _zusammenfuehren(standard.get(k), v) if k in standard else v
        return out
    if isinstance(standard, list) and isinstance(nutzer, list) and standard and isinstance(standard[0], dict) and "schluessel" in standard[0]:
        # Kategorien: je Schlüssel zusammenführen (Nutzerwerte gewinnen, fehlende Felder wie „beispiele“ kommen aus dem Standard),
        # Nutzer-eigene Kategorien bleiben, neue Standard-Kategorien werden ergänzt – Reihenfolge des Standards
        nutzer_map = {d.get("schluessel"): d for d in nutzer if isinstance(d, dict)}
        out = [_kategorie_zusammenfuehren(d, nutzer_map[d["schluessel"]]) if d.get("schluessel") in nutzer_map else d for d in standard]
        std_keys = {d.get("schluessel") for d in standard}
        return out + [d for d in nutzer if isinstance(d, dict) and d.get("schluessel") not in std_keys]
    return nutzer


@lru_cache(maxsize=1)
def regeln() -> dict:
    """Die einzige Quelle für Grenzwerte, Kategorien und EÜR-Zeilen (Nutzerdatei, ergänzt um neue Standardwerte)."""
    with open(regeln_path(), encoding="utf-8") as f:
        nutzer = json.load(f)
    try:
        with open(DEFAULT_REGELN, encoding="utf-8") as f:
            standard = json.load(f)
    except (OSError, json.JSONDecodeError):
        return nutzer
    return _zusammenfuehren(standard, nutzer)


def regeln_setzen(**werte) -> dict:
    """Einzelne Einstellungen in der Nutzerdatei ändern (z. B. aus den Einstellungen) und neu laden."""
    pfad = regeln_path()
    with open(pfad, encoding="utf-8") as f:
        daten = json.load(f)
    daten.update(werte)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    return regeln_neu_laden()


def regeln_neu_laden() -> dict:
    regeln.cache_clear()
    return regeln()


def kategorie_definition(schluessel: str) -> dict | None:
    for k in regeln()["kategorien"]:
        if k["schluessel"] == schluessel:
            return k
    return None
