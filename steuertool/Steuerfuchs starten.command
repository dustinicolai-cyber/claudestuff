#!/bin/bash
# Doppelklick im Finder startet Steuerfuchs in einem Terminal-Fenster.
cd "$(dirname "$0")"
chmod +x start.sh 2>/dev/null
PORT="${PORT:-8347}"
if curl -s --max-time 1 "http://127.0.0.1:$PORT/gesund" >/dev/null 2>&1; then
  echo "→ Ein Steuerfuchs läuft bereits – wird beendet und mit dieser Version neu gestartet."
  curl -s -X POST "http://127.0.0.1:$PORT/api/beenden" >/dev/null 2>&1; sleep 1.5
fi
exec ./start.sh
