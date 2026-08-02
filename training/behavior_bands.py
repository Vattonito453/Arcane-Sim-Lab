#!/usr/bin/env python3
"""Aggregate behavior_tally.json files into human reference bands.

The output replaces the qualitative bands in ai_vs_human_analysis.md
("splits constantly", "routine blocks") with measured rates and 95%
Wilson intervals, plus the corpus size behind each number — a 5-game
band must never masquerade as a 50-game one.

Usage:
  python3 training/behavior_bands.py training/tallies/*.json

Stdlib only, like everything else in this repo.
"""
from __future__ import annotations

import json
import statistics
import sys
from math import sqrt


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion — behaves at small n,
    which is exactly where this corpus lives."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def band(label: str, successes: int, n: int, games: int) -> str:
    if n == 0:
        return f"{label:<28} no data yet"
    lo, hi = wilson(successes, n)
    rate = successes / n
    return (f"{label:<28} {rate:6.1%}  [{lo:.1%}–{hi:.1%}]"
            f"  ({successes}/{n} across {games} games)")


def main() -> int:
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 1

    tallies = [json.loads(open(p, encoding="utf-8").read()) for p in paths]
    games = len(tallies)

    mull_take = sum(t.get("mulligans", {}).get("taken", 0) for t in tallies)
    mull_n = sum(t.get("mulligans", {}).get("decisions", 0) for t in tallies)
    split = sum(t.get("attacks", {}).get("split_turns", 0) for t in tallies)
    atk_n = sum(t.get("attacks", {}).get("attack_turns", 0) for t in tallies)
    blocks = sum(t.get("blocks", {}).get("blocks_made", 0) for t in tallies)
    block_n = sum(t.get("blocks", {}).get("opportunities", 0) for t in tallies)
    # Video-game tallies may carry nulls for unobserved values — skip, don't crash.
    deploys = [d for t in tallies for d in (t.get("commander_deploys") or [])
               if d is not None]
    tutor_cast = sum(t.get("tutors", {}).get("cast", 0) or 0 for t in tallies)
    tutor_held = sum(t.get("tutors", {}).get("held_castable", 0) or 0
                     for t in tallies)
    combo_games = [t for t in tallies if t.get("combo", {}).get("lines_present")]
    jams = sum(t["combo"].get("jammed_into_open_mana", 0) for t in combo_games)
    waits = sum(t["combo"].get("waited_for_protection", 0) for t in combo_games)
    with_decks = sum(1 for t in tallies if t.get("decklists"))
    self_rec = sum(1 for t in tallies if t.get("source") == "self-recorded")

    print(f"Human reference bands — {games} games "
          f"({self_rec} self-recorded, {with_decks} with decklists)\n")
    print(band("mulligan rate", mull_take, mull_n, games))
    print(band("attack-split rate", split, atk_n, games))
    print(band("block rate", blocks, block_n, games))
    if deploys:
        print(f"{'commander deploy (median)':<28} player-turn "
              f"{statistics.median(deploys):.0f}"
              f"  (range {min(deploys)}–{max(deploys)}, n={len(deploys)})")
    else:
        print(f"{'commander deploy (median)':<28} no data yet")
    total_tutor = tutor_cast + tutor_held
    print(band("tutor cast-when-drawn", tutor_cast, total_tutor, games))
    total_last_piece = jams + waits
    print(band("combo jam vs wait (jams)", jams, total_last_piece,
               len(combo_games)))
    if len(combo_games) < 8:
        print(f"\nNOTE: only {len(combo_games)} combo-deck games — the "
              f"greed/hold bands need >=8 (BEHAVIOR_CAPTURE.md targets).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
