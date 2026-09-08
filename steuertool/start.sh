#!/bin/bash
# Startet das Steuertool: venv anlegen (einmalig), Abhängigkeiten installieren (einmalig,
# braucht dafür einmal Netz), Server auf 127.0.0.1 hochfahren, Browser öffnen.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null; then echo "python3 fehlt – bitte Python 3.12 installieren (z. B. brew install python@3.12)"; exit 1; fi

if [ ! -d .venv ]; then
  echo "→ Lege virtuelle Umgebung an …"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, sqlmodel, pdfplumber, pypdf, httpx, multipart" 2>/dev/null; then
  echo "→ Installiere Abhängigkeiten (einmalig) …"
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
fi

PORT="${PORT:-8347}"
export STEUERTOOL_HOME="${STEUERTOOL_HOME:-$HOME/Steuertool}"
echo "→ Daten liegen in $STEUERTOOL_HOME"
echo "→ Steuerfuchs läuft auf http://127.0.0.1:$PORT  (Beenden mit Ctrl+C)"

if [ -z "${STEUERFUCHS_KEIN_BROWSER:-}" ]; then
  ( for i in $(seq 1 240); do sleep 0.5; curl -s --max-time 1 "http://127.0.0.1:$PORT/gesund" >/dev/null 2>&1 && break; done
    if command -v open >/dev/null; then open "http://127.0.0.1:$PORT"; elif command -v xdg-open >/dev/null; then xdg-open "http://127.0.0.1:$PORT"; fi ) &
fi
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
