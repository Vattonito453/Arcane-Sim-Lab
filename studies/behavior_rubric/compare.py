#!/usr/bin/env python3
"""Paired plan-vs-stock comparison, and arm-vs-base comparison.

Why paired. Every pod seats two plan pilots and two stock pilots in the SAME
game, so each game yields one plan measurement and one stock measurement on
one board, one shuffle, one set of opponents. Pooling all plan seats against
all stock seats throws that away and leaves deck and variance differences in
the estimate. Pairing removes them.

The test is a sign-flip permutation on the per-game differences. The null is
that the pilot label carries no information, so flipping the sign of a game's
difference is exchangeable under it. Exact when there are few enough games to
enumerate, sampled otherwise. This is a test of the DIFFERENCE, not of either
pilot's absolute rate.

Unfinished games are dropped and counted. They are dropped symmetrically: both
pilots sit in every pod, so a game killed on the wall clock removes a plan
measurement and a stock measurement together, which is the whole reason the
pods are mixed.

Usage:
  python studies/behavior_rubric/compare.py studies/behavior_rubric/runs_arms
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observer import load  # noqa: E402

PERMS = 20000
SEED = 20260827

# name -> (numerator key, denominator key, higher_is_better)
BLOCK_RATES = [
    ("engage", "blocked", "incoming", True),
    ("declined", "legalMissed", "declinable", False),
    ("chumpShare", "v0", "blocksMade", None),
    # Quality, not volume: of the profitable blocks that were actually on
    # offer, how many were taken. This is the axis that separates "blocks a
    # lot" from "understands which blocks are free".
    ("freeCap", "freeTaken", "freeOpp", True),
    ("safeCap", "safeTaken", "safeOpp", True),
]
ATTACK_RATES = [
    ("commit", "attackers", "committable", None),
    ("keptEnough", "keptEnough", "atkRecs", True),
]


def game_totals(path: Path):
    """Aggregate one game's records per pilot. None if the game never finished."""
    # The shim serialises without spaces; accept both so a formatting change
    # cannot silently drop every game as unfinished.
    text = path.read_text(encoding="utf-8", errors="replace")
    if '"rec":"result"' not in text and '"rec": "result"' not in text:
        return None
    per = {"plan": {}, "stock": {}}
    # A wall-clock kill truncates the game. Censoring is symmetric between
    # pilots (both sit in every pod) so the paired difference stays usable,
    # but arms censor at different rates, so arm-vs-arm needs a decided-only
    # sensitivity pass.
    for line in text.splitlines():
        if '"rec":"result"' in line or '"rec": "result"' in line:
            res = json.loads(line)
            per["_censored"] = bool(res.get("timedOut") or res.get("turnCapped"))
            break
    for pilot, r in load(path):
        if pilot not in per:
            continue
        t = per[pilot]
        if r["kind"] == "block":
            for k in ("incoming", "blocked", "v3", "v2", "v1", "v0",
                      "legalMissed", "lifeTaken", "freeTaken", "freeMissed",
                      "safeMissed"):
                t[k] = t.get(k, 0) + r.get(k, 0)
            t["blockRecs"] = t.get("blockRecs", 0) + 1
        else:
            for k in ("attackers", "held", "heldEligible", "defenders"):
                t[k] = t.get(k, 0) + r.get(k, 0)
            # Shim < 0.9.1 emits no heldEligible. Without this flag the
            # commitment denominator quietly collapses to `attackers` and every
            # stale game reports 100% commitment.
            if "heldEligible" not in r:
                per["_stale"] = True
            t["atkRecs"] = t.get("atkRecs", 0) + 1
            # Biggest single body kept home, not the sum.
            if r.get("heldBestTough", 0) > r.get("backBiggest", 0):
                t["keptEnough"] = t.get("keptEnough", 0) + 1
    for key in ("plan", "stock"):
        t = per[key]
        t["declinable"] = t.get("blocked", 0) + t.get("legalMissed", 0)
        t["blocksMade"] = sum(t.get(k, 0) for k in ("v3", "v2", "v1", "v0"))
        t["freeOpp"] = t.get("freeTaken", 0) + t.get("freeMissed", 0)
        # A survive-the-block chance taken shows up as v3 or v1.
        t["safeTaken"] = t.get("v3", 0) + t.get("v1", 0)
        t["safeOpp"] = t["safeTaken"] + t.get("safeMissed", 0)
        # Eligible bodies only. `held` includes summoning-sick creatures and
        # creatures with defender, which could not have attacked at all.
        t["committable"] = t.get("attackers", 0) + t.get("heldEligible", 0)
        t["dmgPerCombat"] = (t.get("lifeTaken", 0) / t["blockRecs"]
                             if t.get("blockRecs") else None)
    return per


def rate(t, num, den):
    d = t.get(den, 0)
    return t.get(num, 0) / d if d else None


def perm_p(diffs: list[float]) -> float:
    """Two-sided sign-flip permutation p-value on the mean difference."""
    n = len(diffs)
    if n == 0:
        return float("nan")
    obs = abs(sum(diffs) / n)
    if n <= 20:  # exact
        hits = sum(1 for signs in itertools.product((1, -1), repeat=n)
                   if abs(sum(s * d for s, d in zip(signs, diffs)) / n) >= obs - 1e-12)
        return hits / (2 ** n)
    rng = random.Random(SEED)
    hits = 0
    for _ in range(PERMS):
        if abs(sum(d if rng.random() < 0.5 else -d for d in diffs) / n) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (PERMS + 1)


def two_sample_p(a: list[float], b: list[float]) -> float:
    """Two-sided permutation test on a difference of means, labels shuffled.

    Arms are separate games, so arm-vs-base is a two-sample problem, not a
    paired one. Without this the arm-minus-base deltas are just arithmetic and
    cannot distinguish a real regression from noise.
    """
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return float("nan")
    obs = abs(sum(a) / na - sum(b) / nb)
    pool = list(a) + list(b)
    rng = random.Random(SEED)
    hits = 0
    for _ in range(PERMS):
        rng.shuffle(pool)
        if abs(sum(pool[:na]) / na - sum(pool[na:]) / nb) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (PERMS + 1)


def arm_diffs(arm_dir: Path, decided_only: bool = False):
    """Per-game plan-minus-stock differences for each metric in one arm."""
    diffs: dict[str, list[float]] = {}
    finished = dropped = 0
    for f in sorted(arm_dir.glob("*.jsonl")):
        per = game_totals(f)
        if per is None:
            dropped += 1
            continue
        if decided_only and per.get("_censored"):
            dropped += 1
            continue
        finished += 1
        for name, num, den, _ in BLOCK_RATES + ATTACK_RATES:
            if name in ("commit", "keptEnough") and per.get("_stale"):
                continue
            a, b = rate(per["plan"], num, den), rate(per["stock"], num, den)
            if a is not None and b is not None:
                diffs.setdefault(name, []).append(a - b)
        a, b = per["plan"]["dmgPerCombat"], per["stock"]["dmgPerCombat"]
        if a is not None and b is not None:
            diffs.setdefault("dmgPerCombat", []).append(a - b)
    return diffs, finished, dropped


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    root = Path(argv[0])
    decided_only = "--decided-only" in argv
    arms = sorted(d for d in root.iterdir() if d.is_dir() and d.name != "plans")
    if not arms:
        print("no arm directories found")
        return 2

    per_arm = {}
    print("PAIRED plan minus stock, within game"
          + (" (DECIDED GAMES ONLY)" if decided_only else ""))
    print(f"{'arm':10} {'games':>6} {'dropped':>8} {'metric':>13} "
          f"{'mean diff':>10} {'p':>8}")
    for arm in arms:
        diffs, fin, drop = arm_diffs(arm, decided_only)
        per_arm[arm.name] = diffs
        if not fin:
            print(f"{arm.name:10} {fin:>6} {drop:>8}  (no finished games)")
            continue
        first = True
        for name in [n for n, *_ in BLOCK_RATES + ATTACK_RATES] + ["dmgPerCombat"]:
            d = diffs.get(name)
            if not d:
                continue
            mean = sum(d) / len(d)
            label = arm.name if first else ""
            g = f"{fin:>6}" if first else " " * 6
            dr = f"{drop:>8}" if first else " " * 8
            first = False
            print(f"{label:10} {g} {dr} {name:>13} {mean:>+10.3f} "
                  f"{perm_p(d):>8.4f}")

    if "base" in per_arm and len(per_arm) > 1:
        print()
        print("ARM minus BASE, on the paired difference (did the change move it?)")
        print(f"{'arm':10} {'metric':>13} {'base':>9} {'arm':>9} "
              f"{'delta':>9} {'p':>8}")
        for name in [n for n, *_ in BLOCK_RATES + ATTACK_RATES] + ["dmgPerCombat"]:
            b = per_arm["base"].get(name)
            if not b:
                continue
            bm = sum(b) / len(b)
            for arm in per_arm:
                if arm == "base":
                    continue
                a = per_arm[arm].get(name)
                if not a:
                    continue
                am = sum(a) / len(a)
                print(f"{arm:10} {name:>13} {bm:>+9.3f} {am:>+9.3f} "
                      f"{am - bm:>+9.3f} {two_sample_p(a, b):>8.4f}")

    print()
    print("declined = share of blockable attackers let through (lower is more "
          "human).\nkeptEnough = attacks that left enough toughness home to "
          "survive the biggest\nuntapped creature the rest of the table had. "
          "p is a two-sided sign-flip\npermutation on the per-game paired "
          "differences.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
