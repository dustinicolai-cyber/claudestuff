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


def verfuegbar(cfg: dict) -> dict:
    """{'online': bool, 'modelle': [...]}"""
    try:
        r = httpx.get(_basis(cfg) + "/api/tags", timeout=2.0)
        r.raise_for_status()
        return {"online": True, "modelle": [m.get("name", "") for m in r.json().get("models", [])]}
    except Exception:
        return {"online": False, "modelle": []}


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
