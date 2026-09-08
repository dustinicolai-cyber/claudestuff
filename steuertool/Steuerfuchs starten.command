#!/bin/bash
# Doppelklick im Finder startet Steuerfuchs in einem Terminal-Fenster.
cd "$(dirname "$0")"
chmod +x start.sh 2>/dev/null
PORT="${PORT:-8347}"
if curl -s --max-time 1 "http://127.0.0.1:$PORT/gesund" >/dev/null 2>&1; then
  echo "→ Ein Steuerfuchs läuft bereits – wird beendet und mit dieser Version neu gestartet."
  curl -s -X POST --max-time 2 "http://127.0.0.1:$PORT/api/beenden" >/dev/null 2>&1
  for i in $(seq 1 15); do sleep 0.3; curl -s --max-time 1 "http://127.0.0.1:$PORT/gesund" >/dev/null 2>&1 || break; done
  if curl -s --max-time 1 "http://127.0.0.1:$PORT/gesund" >/dev/null 2>&1; then
    PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null)"; [ -n "$PIDS" ] && kill $PIDS 2>/dev/null; sleep 1
  fi
fi
exec ./start.sh
