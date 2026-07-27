#!/bin/bash
# Double-click me: starts the MTG Engine and opens the dashboard in your browser.
cd "$(dirname "$0")/engine"
if curl -s -m 1 http://127.0.0.1:8484/health > /dev/null 2>&1; then
  echo "Engine already running."
else
  echo "Starting MTG Engine..."
  python3 mtg_engine.py serve 8484 &
  sleep 1.5
fi
open "http://127.0.0.1:8484"
echo
echo "Dashboard: http://127.0.0.1:8484  (leave this window open; close it to stop the engine)"
wait
