#!/bin/bash
# Sequential stock-Forge runs for the human_ceiling study.
# One JVM at a time, deliberately: --clock is wall-clock, so concurrent sims
# manufacture timeouts (see memory: 10-worker precon pilot contamination).
set -u
ENGINE="/Users/vincentattonito/Desktop/Personal/MtG Rules Engine/engine"
STUDY="/Users/vincentattonito/Desktop/Personal/MtG Rules Engine/studies/human_ceiling"
OUT="$STUDY/runs"
LOG="$STUDY/runs/queue.log"

run_pod () {
  local vid="$1"; shift
  echo "=== $(date '+%H:%M:%S') starting pod $vid ===" >> "$LOG"
  (cd "$ENGINE" && python3 run_sim.py \
      --decks "$@" \
      --deck-dir "$STUDY/decks/$vid/dck" \
      --games 4 --format Commander --agent shim --rotate --clock 900 \
      --out "$OUT" --run-id "hc_$vid") >> "$LOG" 2>&1
  echo "=== $(date '+%H:%M:%S') finished pod $vid (exit $?) ===" >> "$LOG"
}

# Wait for any already-running sim to finish before starting the queue.
while pgrep -f "simlab.shim.SimShim" > /dev/null; do sleep 30; done

run_pod 5A6o18Bra0Y rog_ishai.dck malcolm_kediss.dck cabbage_merchant.dck godo.dck
run_pod Bq-nFi0f1jA cabbage_merchant.dck yidris.dck rog_thrasios.dck kinnan.dck
run_pod 2iA_Jt0d6sM derevi.dck nadu.dck rograkh_silas.dck godo_archetype.dck
run_pod OuY6mdiXbHU winota_ian.dck winota_lua.dck winota_rachel.dck winota_mike.dck

echo "QUEUE COMPLETE $(date '+%H:%M:%S')" >> "$LOG"
touch "$OUT/.queue_done"
