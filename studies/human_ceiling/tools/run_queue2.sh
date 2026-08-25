#!/bin/bash
# Second wave: the two Mid-Season Showdown pods. Waits for run_queue.sh's
# completion marker so only one JVM ever runs at a time.
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

until [ -f "$OUT/.queue_done" ]; do sleep 30; done
while pgrep -f "simlab.shim.SimShim" > /dev/null; do sleep 30; done

run_pod CxKMqO36DdM dallas_bluefarm.dck alan_tnt.dck sterling_bluefarm.dck joseph_ral.dck
run_pod sZA0KqXCGrY joseph_ral.dck tyler_bluefarm.dck ashton_bluefarm.dck natalie_magda.dck

echo "QUEUE2 COMPLETE $(date '+%H:%M:%S')" >> "$LOG"
touch "$OUT/.queue2_done"
