"""Dünner Client für den lokalen Ollama-Server. Läuft nur gegen 127.0.0.1,
keine Telemetrie. Ist Ollama nicht erreichbar, liefern die Funktionen None und
die Pipeline arbeitet ohne KI weiter.
"""
from __future__ import annotations

import base64
import json

import httpx


def _basis(cfg: dict) -> str:
    return cfg["ollama"]["url"].rstrip("/")


_CACHE = {"zeit": 0.0, "wert": None}
CACHE_SEKUNDEN = 30


def verfuegbar(cfg: dict) -> dict:
    """{'online': bool, 'modelle': [...]} – gecacht, damit kein Seitenaufruf auf Ollama wartet."""
    import time
    jetzt = time.monotonic()
    if _CACHE["wert"] is not None and jetzt - _CACHE["zeit"] < CACHE_SEKUNDEN:
        return _CACHE["wert"]
    try:
        r = httpx.get(_basis(cfg) + "/api/tags", timeout=0.5)
        r.raise_for_status()
        wert = {"online": True, "modelle": [m.get("name", "") for m in r.json().get("models", [])]}
    except Exception:
        wert = {"online": False, "modelle": []}
    _CACHE.update(zeit=jetzt, wert=wert)
    return wert


def status(cfg: dict, ki_gewollt: bool) -> str:
    """aktiv | aus (bewusst deaktiviert) | nicht_erreichbar"""
    if not ki_gewollt:
        return "aus"
    return "aktiv" if verfuegbar(cfg)["online"] else "nicht_erreichbar"


def chat_json(cfg: dict, modell: str, system: str, prompt: str, bilder: list[bytes] | None = None) -> dict | None:
    """Ein Chat-Aufruf im JSON-Modus; Antwort als dict oder None bei Fehler."""
    nachricht = {"role": "user", "content": prompt}
    if bilder:
        nachricht["images"] = [base64.b64encode(b).decode("ascii") for b in bilder]
    body = {
        "model": modell,
        "messages": [{"role": "system", "content": system}, nachricht],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        r = httpx.post(_basis(cfg) + "/api/chat", json=body, timeout=cfg["ollama"]["timeout_sekunden"])
        r.raise_for_status()
        inhalt = r.json().get("message", {}).get("content", "")
        return json.loads(inhalt)
    except Exception:
        return None
