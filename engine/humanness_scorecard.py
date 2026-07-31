#!/usr/bin/env python3
"""Humanness scorecard: the four behavioral metrics from
training/ai_vs_human_analysis.md, computed from any adapted sim result.

  1. keep-7 rate (stock AI ~97%; humans mull ~15-25% of hands)
  2. attack-split rate (stock: 0% — 244/244 single-defender; humans split constantly)
  3. block rate (stock: ~14%; human games feature routine blocks)
  4. commander deploy turn, median PLAYER-turn (humans: ~turn 4-5 for synergy decks)

Usage:
  python3 humanness_scorecard.py <result.json> [more.json ...]

Works on stock and shim results (shim results also carry `zones` for a
precise commander-cast read; stock falls back to log text). Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

_KEPT = re.compile(r"kept a hand of (\d+) cards?")
_ATTACK = re.compile(r"assigned .+? to attack (.+?)\.?$")
_BLOCKED = re.compile(r"assigned .+? to block ")
_NOBLOCK = re.compile(r"didn't block ")
_SEAT = re.compile(r"^Ai\(\d+\)-")


def score(files: list[str]) -> dict:
    kept_sizes: list[int] = []
    attack_turns = 0          # (game, turn) buckets with any attack
    split_turns = 0           # buckets attacking 2+ distinct defenders
    blocks = 0
    declines = 0
    commander_turns: list[int] = []

    for path in files:
        data = json.load(open(path, encoding="utf-8"))
        for g in data.get("games", []):
            defenders_by_turn: dict[int, set] = defaultdict(set)
            # Mulligans resolve before turn 1 and land in events_pregame.
            pregame = [{"turn": 0, "events": g.get("events_pregame", [])}]
            for t in pregame + g.get("turns", []):
                for e in t.get("events", []):
                    raw = e.get("raw", "")
                    a = e.get("action")
                    if a == "mulligan":
                        m = _KEPT.search(raw)
                        if m:
                            kept_sizes.append(int(m.group(1)))
                    elif a == "combat":
                        m = _ATTACK.search(raw)
                        if m:
                            defenders_by_turn[t.get("turn", 0)].add(m.group(1))
                        elif _BLOCKED.search(raw):
                            blocks += 1
                        elif _NOBLOCK.search(raw):
                            declines += 1
            # Agent self-telemetry (shim runs): authoritative for splits and
            # added blocks — Forge's GameLog writes combat lines before the
            # agent's adjustments, so log text under-reports them.
            agent_split_turns = {(e.get("turn"), e.get("player"))
                                 for e in g.get("agent_events", [])
                                 if e.get("event") == "split"}
            agent_blocks = sum(1 for e in g.get("agent_events", [])
                               if e.get("event") == "added_block")
            blocks += agent_blocks
            for turn, defs in defenders_by_turn.items():
                attack_turns += 1
                if len(defs) >= 2 or any(t == turn for t, _ in agent_split_turns):
                    split_turns += 1
            # Commander deploy: zones ground truth when present, else log text.
            seen: set[str] = set()
            for z in g.get("zones", []):
                if z.get("from") == "Command" and z.get("to") == "Stack":
                    key = z.get("fromPlayer", "") + z.get("card", "")
                    if key not in seen:
                        seen.add(key)
                        commander_turns.append(z.get("turn", 0))

    kept7 = sum(1 for k in kept_sizes if k == 7)
    total_blocks = blocks + declines
    commander_turns.sort()
    med_cmd = commander_turns[len(commander_turns) // 2] if commander_turns else None
    return {
        "hands": len(kept_sizes),
        "keep7_rate": round(kept7 / len(kept_sizes), 3) if kept_sizes else None,
        "avg_kept_hand": round(sum(kept_sizes) / len(kept_sizes), 2) if kept_sizes else None,
        "attack_turns": attack_turns,
        "attack_split_rate": round(split_turns / attack_turns, 3) if attack_turns else None,
        "block_opportunities": total_blocks,
        "block_rate": round(blocks / total_blocks, 3) if total_blocks else None,
        "commander_casts": len(commander_turns),
        # game-turn counter (4 player-turns per table round in a pod)
        "median_commander_deploy_turn": med_cmd,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    s = score(sys.argv[1:])
    for k, v in s.items():
        print(f"{k:32} {v}")


if __name__ == "__main__":
    main()
