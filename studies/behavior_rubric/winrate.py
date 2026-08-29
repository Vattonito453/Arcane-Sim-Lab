#!/usr/bin/env python3
"""Head-to-head win tally for mixed pods: did the plan side WIN the game?

Each mixed-pod game seats 2 plan pilots and 2 stock pilots, so every decided
game is one Bernoulli observation with null 50%. This is the number the whole
agent effort answers to: behaviour metrics say it plays differently, this says
whether it wins.

Also reports: win turn by pilot, per-seat survival, censoring, wall time
(median / p90 / max), and an exact two-sided binomial p against 50%.

Usage:
  python studies/behavior_rubric/winrate.py <arm-dir> [<arm-dir> ...]
"""

from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path


def scan(root: Path):
    plan_w = stock_w = draws = censored = 0
    turns = {"plan": [], "stock": []}
    alive = {"plan": [0, 0], "stock": [0, 0]}
    ms_all = []
    for f in sorted(root.rglob("*.jsonl")):
        if "plans" in f.parts:
            continue
        # EVERY result record counts. A production shim JSONL holds N games
        # per rotation, and keeping only the last line silently discarded
        # (N-1)/N of them. A torn trailing line (shim killed mid-write) is
        # skipped rather than crashing the whole tally.
        pilots, results = {}, []
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                if '"rec":"meta"' in line or '"rec": "meta"' in line:
                    m = json.loads(line)
                    pilots = dict(zip(m.get("players", []), m.get("agents", [])))
                elif '"rec":"result"' in line or '"rec": "result"' in line:
                    results.append(json.loads(line))
            except ValueError:
                continue
        for res in results:
            ms_all.append(res.get("ms", 0))
            if res.get("timedOut") or res.get("turnCapped"):
                censored += 1
                continue
            for s in res.get("seats", []):
                p = pilots.get(s["name"], "?")
                if p in alive:
                    alive[p][1] += 1
                    if s.get("alive"):
                        alive[p][0] += 1
            w = res.get("winner")
            if not w or res.get("draw"):
                draws += 1
                continue
            p = pilots.get(w, "?")
            if p == "plan":
                plan_w += 1
                turns["plan"].append(res.get("turns", 0))
            elif p == "stock":
                stock_w += 1
                turns["stock"].append(res.get("turns", 0))
    return plan_w, stock_w, draws, censored, turns, alive, ms_all


def binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return float("nan")
    return sum(comb(n, i) for i in range(n + 1)
               if abs(i - n / 2) >= abs(k - n / 2) - 1e-12) / 2 ** n


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    for a in argv:
        root = Path(a)
        pw, sw, dr, ce, turns, alive, ms = scan(root)
        n = pw + sw
        if not n:
            print(f"{root.name}: no decided games")
            continue
        med = lambda x: sorted(x)[len(x) // 2] if x else 0
        ms.sort()
        print(f"{root.name}: plan {pw} - stock {sw}  "
              f"({pw / n:.1%} of {n} decided, null 50%, "
              f"p = {binom_two_sided(pw, n):.4f})")
        print(f"  draws {dr}, censored {ce} of {n + dr + ce}")
        print(f"  win turn: plan med {med(turns['plan'])}, "
              f"stock med {med(turns['stock'])}")
        for p in ("plan", "stock"):
            al, t = alive[p]
            if t:
                print(f"  {p} seats alive at end: {al}/{t} ({al / t:.1%})")
        if ms:
            print(f"  game wall: med {ms[len(ms) // 2] / 1000:.0f}s, "
                  f"p90 {ms[int(len(ms) * .9)] / 1000:.0f}s, "
                  f"max {ms[-1] / 1000:.0f}s")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
