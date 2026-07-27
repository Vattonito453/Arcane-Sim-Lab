#!/usr/bin/env bash
# Friday-table simulation: 4 pods of bracket-3-heavy archetypes, seat-rotated.
# Pod 1 is the "fuckery pod" (hand-punisher / ooze snowball / drain-taxes).
# Usage: bash fuckery_gauntlet.sh [deck_under_test.dck] [games_per_pod]
set -euo pipefail
cd "$(dirname "$0")"
DECK="${1:-kilo_helm_final.dck}"
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

# Pod 1 — THE FUCKERY POD: Nekusar hand-punisher / Slurrk ooze snowball / Kambal drain-taxes
run nekusar_punisher.dck slurrk_oozes.dck kambal_taxes.dck

# Pod 2 — real human decklists (most predictive of an actual table)
run dnide_wildsear.dck nanman_felix.dck n3cro_raggadragga.dck

# Pod 3 — wipe-heavy value (the historical nemesis pod)
run atraxa_counters.dck meren_graveyard.dck urdragon_dragons.dck

# Pod 4 — pressure mix: token grind / voltron / midrange
run wilhelt_zombies.dck wyleth_voltron.dck drana_vampires.dck

echo ""
echo "All four pods complete."
