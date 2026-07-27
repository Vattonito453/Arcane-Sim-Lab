#!/usr/bin/env bash
# Four-pod evaluation tournament (12 distinct opponents) for any deck under test.
# Usage:  bash gauntlet_run.sh [deck_under_test.dck] [games_per_pod]
# Defaults: inspirit_b3_v2.dck, 16 games/pod (4 per seat rotation)
set -euo pipefail
cd "$(dirname "$0")"
DECK="${1:-inspirit_b3_v2.dck}"
N="${2:-16}"

run() {
  echo ""
  echo "=============================================================="
  echo "POD: $DECK vs $*"
  echo "=============================================================="
  python3 run_sim.py --decks "$DECK" "$@" --deck-dir ./decks \
      --games "$N" --clock 240 --rotate 2>&1 | tee -a sim_results/last_run.txt
}

: > sim_results/last_run.txt

# Pod 1 — the rematch: the B3 gauntlet that beat Omega 7-0
run atraxa_counters.dck meren_graveyard.dck urdragon_dragons.dck

# Pod 2 — the human-validated pod (real Friday-night power level)
run dnide_wildsear.dck nanman_felix.dck n3cro_raggadragga.dck

# Pod 3 — classic axes: aggro swarm / draw-go control / midrange
run krenko_goblins.dck talrand_control.dck drana_vampires.dck

# Pod 4 — new archetypes: burn race / zombie swarm / equipment voltron
run torbran_burn.dck wilhelt_zombies.dck wyleth_voltron.dck

echo ""
echo "All four pods complete. Results in sim_results/ (four sim_*.json files)."
