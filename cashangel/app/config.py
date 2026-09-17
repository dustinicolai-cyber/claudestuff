"""Pfade und Konfiguration. Alles liegt in CASHANGEL_HOME (Standard ~/CashAngel), nichts verlässt den Rechner."""
from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_KATEGORIEN = APP_DIR / "kategorien.json"
STATIC = APP_DIR / "static"


def home_dir() -> Path:
    p = Path(os.environ.get("CASHANGEL_HOME", Path.home() / "CashAngel")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return home_dir() / "cashangel.db"


def kategorien_path() -> Path:
    p = home_dir() / "kategorien.json"
    if not p.exists():
        shutil.copy(DEFAULT_KATEGORIEN, p)
    return p


def _zusammenfuehren(standard, nutzer):
    """Nutzerdatei gewinnt; neue Standardschlüssel und -kategorien werden ergänzt, Muster vereinigt."""
    if isinstance(standard, dict) and isinstance(nutzer, dict):
        out = dict(standard)
        for k, v in nutzer.items():
            out[k] = _zusammenfuehren(standard.get(k), v) if k in standard else v
        return out
    if isinstance(standard, list) and isinstance(nutzer, list) and standard and isinstance(standard[0], dict) and "schluessel" in standard[0]:
        nutzer_map = {d.get("schluessel"): d for d in nutzer if isinstance(d, dict)}
        out = []
        for d in standard:
            n = nutzer_map.get(d.get("schluessel"))
            if n is None:
                out.append(d)
                continue
            m = dict(d)
            m.update(n)
            # Muster: eigene Ergänzungen behalten, neue Standardmuster dazu
            m["muster"] = list(dict.fromkeys(list(d.get("muster", [])) + list(n.get("muster", []))))
            out.append(m)
        std_keys = {d.get("schluessel") for d in standard}
        return out + [d for d in nutzer if isinstance(d, dict) and d.get("schluessel") not in std_keys]
    return nutzer


@lru_cache(maxsize=1)
def konfig() -> dict:
    with open(kategorien_path(), encoding="utf-8") as f:
        nutzer = json.load(f)
    with open(DEFAULT_KATEGORIEN, encoding="utf-8") as f:
        standard = json.load(f)
    return _zusammenfuehren(standard, nutzer)


def konfig_neu_laden() -> dict:
    konfig.cache_clear()
    return konfig()


def konfig_setzen(**werte) -> dict:
    pfad = kategorien_path()
    with open(pfad, encoding="utf-8") as f:
        daten = json.load(f)
    daten.update(werte)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    return konfig_neu_laden()


@lru_cache(maxsize=1)
def version() -> str:
    p = APP_DIR.parent / "VERSION"
    try:
        return p.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"
