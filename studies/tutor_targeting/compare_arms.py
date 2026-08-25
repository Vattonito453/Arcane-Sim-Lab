#!/usr/bin/env python3
"""Compare sim arms on the human-ceiling behavioral metrics.

Three prior studies (precon_correlation, skill_headtohead, human_ceiling)
established that raw win rate is a weak discriminator between agents; the
signals that track human play are win ROUND, win METHOD, and whether the
deck's actual line shows up. This script reads rotated result JSONs (one or
more per arm; arms are labeled from meta.humanized) and reports exactly
those, plus battlefield arrivals of watch cards (default: the Magda pod's
human-verified fetch targets).

Usage:
  python3 studies/tutor_targeting/compare_arms.py <result.json> [...]
      [--watch "Portal to Phyrexia;God-Pharaoh's Gift"]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "engine"))
import analysis  # noqa: E402

DEFAULT_WATCH = "Portal to Phyrexia;God-Pharaoh's Gift"


def rounds_of(game: dict) -> int:
    seats = max(1, len(game.get("players") or []) or 4)
    player_turns = len(game.get("turns") or [])
    return (max(1, player_turns) - 1) // seats + 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", nargs="+", help="rotated result JSON files")
    ap.add_argument("--watch", default=DEFAULT_WATCH,
                    help="semicolon-separated card names to watch onto the battlefield")
    args = ap.parse_args()
    watch = [w.strip() for w in args.watch.split(";") if w.strip()]

    arms: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for p in args.results:
        r = json.loads(Path(p).read_text(encoding="utf-8"))
        label = "agent" if r.get("meta", {}).get("humanized") else "stock"
        arms[label].append((p, r))

    for label in sorted(arms):
        games_total = 0
        win_rounds: list[int] = []
        winners: dict[str, int] = defaultdict(int)
        methods: dict[str, int] = defaultdict(int)
        timeouts = 0
        sightings: list[str] = []
        agent_counts: dict[str, int] = defaultdict(int)
        print(f"=== arm: {label} ===")
        for path, r in arms[label]:
            for i, g in enumerate(r.get("games") or []):
                games_total += 1
                res = g.get("result") or {}
                rnd = rounds_of(g)
                m = analysis.win_method(g)
                if res.get("timedOut"):
                    timeouts += 1
                if res.get("draw"):
                    winners["(draw)"] += 1
                else:
                    w = analysis._bare(res.get("winner") or "?")
                    winners[w] += 1
                    win_rounds.append(rnd)
                methods[m.get("method", "?")] += 1
                print(f"  {Path(path).name} g{i}: winner={res.get('winner', '-'):32} "
                      f"round={rnd:>2} method={m.get('method')}"
                      f"{' TIMEOUT' if res.get('timedOut') else ''}")
                for z in g.get("zones") or []:
                    if z.get("to") == "Battlefield" and z.get("card") in watch:
                        seats = max(1, len(g.get("players") or []) or 4)
                        zr = (max(1, z.get("turn") or 1) - 1) // seats + 1
                        sightings.append(
                            f"{z['card']} -> battlefield of "
                            f"{z.get('toPlayer')} in g{i} round {zr} "
                            f"(from {z.get('from')})")
                for ev in g.get("agent_events") or []:
                    name = ev.get("event")
                    if name in ("combo_cast", "tutor_cast", "tutor_steer",
                                "combo_hold", "search_seen", "mull_take"):
                        agent_counts[name] += 1
        if win_rounds:
            mean = sum(win_rounds) / len(win_rounds)
            print(f"  decided {len(win_rounds)}/{games_total} "
                  f"(timeouts {timeouts}); win rounds "
                  f"{sorted(win_rounds)} mean {mean:.1f}")
        print(f"  winners: {dict(winners)}")
        print(f"  methods: {dict(methods)}")
        if agent_counts:
            print(f"  agent telemetry: {dict(agent_counts)}")
        if sightings:
            print("  watch-card arrivals:")
            for s in sightings:
                print("    " + s)
        else:
            print(f"  watch cards never hit the battlefield: {watch}")
        print()
    print("human target (n7WpsqsZtdQ trace): Magda wins both games, rounds 5"
          " and ~6, via Portal to Phyrexia / Liquimetal Torque toolbox.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
