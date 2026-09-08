#!/bin/bash
# Doppelklick im Finder startet Steuerfuchs in einem Terminal-Fenster.
cd "$(dirname "$0")"
chmod +x start.sh 2>/dev/null
exec ./start.sh
