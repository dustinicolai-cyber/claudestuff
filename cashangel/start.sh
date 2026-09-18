#!/bin/bash
# Startet Cash Angel: venv anlegen (einmalig), Abhängigkeiten installieren (einmalig, braucht dafür einmal Netz),
# Server auf 127.0.0.1 hochfahren, Browser öffnen. Jede Zeile hier landet beim Start über die App in
# ~/CashAngel/server.log – wenn etwas schiefgeht, steht dort der Grund.
set -euo pipefail
cd "$(dirname "$0")"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') Start in $(pwd)"

# Python finden: erst die Wunschversion aus $PYTHON, dann Homebrew-/python.org-Versionen, zuletzt python3.
# Das mitgelieferte Apple-python3 (3.9) ist zu alt – die App braucht mindestens 3.10.
finde_python(){
  for k in "${PYTHON:-}" python3.12 python3.13 python3.11 python3.14 python3; do
    [ -n "$k" ] || continue
    command -v "$k" >/dev/null 2>&1 || continue
    if "$k" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then echo "$k"; return 0; fi
  done
  return 1
}
if ! PY="$(finde_python)"; then
  echo "FEHLER: Kein Python 3.10 oder neuer gefunden (gefunden: $(python3 --version 2>&1 || echo keins))."
  echo "        Bitte installieren: brew install python@3.12  – oder Installer von python.org."
  exit 1
fi
echo "→ Python: $("$PY" --version 2>&1) ($(command -v "$PY"))"

# Kaputte oder fremde venv (z. B. mit inzwischen gelöschtem Python angelegt) neu aufbauen.
if [ -d .venv ] && ! .venv/bin/python -c 'import sys' >/dev/null 2>&1; then
  echo "→ Vorhandene .venv ist defekt – lege sie neu an"
  rm -rf .venv
fi
if [ ! -d .venv ]; then
  echo "→ Lege virtuelle Umgebung an …"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, sqlmodel, pdfplumber, multipart" 2>/dev/null; then
  echo "→ Installiere Abhängigkeiten (einmalig, kann ein paar Minuten dauern) …"
  python -m pip install --disable-pip-version-check --progress-bar off --upgrade pip
  python -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt
  python -c "import fastapi, sqlmodel, pdfplumber, multipart" || { echo "FEHLER: Abhängigkeiten fehlen trotz Installation – Ausgabe oben prüfen."; exit 1; }
fi

PORT="${PORT:-8351}"
export CASHANGEL_HOME="${CASHANGEL_HOME:-$HOME/CashAngel}"
echo "→ Daten liegen in $CASHANGEL_HOME"

# Kurzer Selbsttest: lässt sich die App laden? Ein Fehler steht dann als Traceback hier im Log.
python -c "import app.main" || { echo "FEHLER: Die App lässt sich nicht laden (siehe Traceback oben)."; exit 1; }

echo "→ Cash Angel läuft auf http://127.0.0.1:$PORT  (Beenden mit Ctrl+C)"
if [ -z "${CASHANGEL_KEIN_BROWSER:-}" ]; then
  ( for i in $(seq 1 240); do sleep 0.5; curl -s --max-time 1 "http://127.0.0.1:$PORT/gesund" >/dev/null 2>&1 && break; done
    if command -v open >/dev/null; then open "http://127.0.0.1:$PORT"; elif command -v xdg-open >/dev/null; then xdg-open "http://127.0.0.1:$PORT"; fi ) &
fi
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
