#!/bin/bash
# Starts the engine API and the Sim Lab front end, then opens the browser.
# Double-click this file in Finder. See TESTING.md for what to try once it's up.
cd "$(dirname "$0")" || exit 1

API_PORT="${MTG_PORT_LOCAL:-8484}"
WEB_PORT="${SIMLAB_PORT:-3000}"

cleanup() { echo; echo "Shutting down…"; kill 0; }
trap cleanup EXIT INT TERM

# Preflight. Each of these fails in a way that is confusing later but obvious now.
command -v python3 >/dev/null || { echo "python3 not found."; read -r; exit 1; }
command -v node >/dev/null || { echo "node not found — install Node 20+."; read -r; exit 1; }
if ! command -v java >/dev/null; then
  echo "NOTE: java not found. Everything except running NEW simulations will work"
  echo "      (existing runs still replay). For sims: brew install openjdk@17"
  echo
fi
if ! ls "$HOME"/forge/forge-gui-desktop-*-jar-with-dependencies.jar >/dev/null 2>&1; then
  echo "NOTE: Forge not found in ~/forge. Replays of existing runs work; new"
  echo "      simulations need it: bash engine/setup_forge.sh"
  echo
fi

# Bind loopback explicitly. The engine refuses a public interface without
# MTG_API_KEYS on purpose (a sim is a 4 GB JVM); to share this with other people
# use deploy/HOSTING.md rather than widening the bind here.
echo "Starting engine API on :$API_PORT…"
MTG_BIND=127.0.0.1 python3 engine/mtg_engine.py serve "$API_PORT" &

# Wait for the corpus to actually load instead of guessing with sleep — a cold
# start parses the rules KB, and opening the browser early shows a dead engine.
printf "Waiting for the engine"
for _ in $(seq 1 60); do
  if curl -fs -m 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    echo " — ready."
    break
  fi
  printf "."
  sleep 1
done
curl -fs -m 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 || {
  echo; echo "Engine did not come up. Scroll up for the error."; read -r; exit 1; }

cd web || { echo "web/ not found"; exit 1; }
if [ ! -d node_modules ]; then
  echo "First run — installing front-end dependencies…"
  npm install || { echo "npm install failed"; exit 1; }
fi

echo "Starting Sim Lab on :$WEB_PORT…"
npm run dev -- -p "$WEB_PORT" &

printf "Waiting for the front end"
for _ in $(seq 1 90); do
  if curl -fs -m 2 -o /dev/null "http://localhost:$WEB_PORT/" 2>/dev/null; then
    echo " — ready."
    break
  fi
  printf "."
  sleep 1
done

open "http://localhost:$WEB_PORT"

cat <<EOF

Sim Lab is running.
  app     http://localhost:$WEB_PORT
  engine  http://127.0.0.1:$API_PORT

Check everything works, in another terminal:
  python3 engine/tests/smoke_test.py --sim

Close this window to stop both processes.
EOF
wait
