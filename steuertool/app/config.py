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


@lru_cache(maxsize=1)
def regeln() -> dict:
    """Die einzige Quelle für Grenzwerte, Kategorien und EÜR-Zeilen."""
    with open(regeln_path(), encoding="utf-8") as f:
        return json.load(f)


def regeln_neu_laden() -> dict:
    regeln.cache_clear()
    return regeln()


def kategorie_definition(schluessel: str) -> dict | None:
    for k in regeln()["kategorien"]:
        if k["schluessel"] == schluessel:
            return k
    return None
