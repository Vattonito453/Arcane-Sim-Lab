#!/usr/bin/env python3
"""Analyze the engine-strength head-to-head. Pre-registered in PLAN.md section 3.

    python3 studies/skill_headtohead/analyze_h2h.py

Stdlib only, like the rest of the engine. Reads runs/results.jsonl, which
carries every field the pre-registered analysis needs, so the raw shim JSONL is
not required.

Three things this deliberately refuses to do:
  - infer a winner for a censored game. It has none. Survival is reported
    separately and never folded into a win rate.
  - present a result on clean games alone without also reporting whether it
    survives the worst-case censoring bound.
  - report a per-deck or archetype figure as if it were powered. At 96 games
    per deck the SE is 7.2 pp; those numbers are exploratory.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARM_ORDER = ["A", "B", "C", "D"]
ARM_DESC = {
    "A": "plan  + SimLabHuman  (ships today)",
    "B": "stock + Default      (stock Forge)",
    "C": "stock + SimLabHuman  (floodgate, no gate)",
    "D": "plan  + Default      (our policy, no floodgate)",
}
BOOTSTRAP = 10_000
SEED = 20260805


def load(results_path):
    rows = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"no rows in {results_path}")
    return rows


def flatten(rows):
    """One record per game, with the arm that won and per-arm seat state."""
    games = []
    for r in rows:
        for g in r["games"]:
            games.append({
                "precon": r["precon"],
                "rotation": r["rotation"],
                "seat_arms": r["seat_arms"],
                "timed_out": g["timed_out"],
                "winner_arm": g["winner_arm"],
                "turns": g["turns"],
                "ms": g["ms"],
                "seats": g.get("seats", {}),
            })
    return games


def shares(games):
    """Win share per arm over decided games. Censored and drawn games have no
    winner and are excluded here; section 4 handles them."""
    decided = [g for g in games if g["winner_arm"]]
    n = len(decided)
    out = {a: 0 for a in ARM_ORDER}
    for g in decided:
        out[g["winner_arm"]] += 1
    return out, n


def diff(games, x, y):
    """Win-share difference x - y over decided games."""
    w, n = shares(games)
    if not n:
        return 0.0
    return (w[x] - w[y]) / n


def boot_ci(games, x, y, n_boot=BOOTSTRAP, seed=SEED):
    """Paired bootstrap over games. Games are the resampling unit and each game
    contributes to every arm at once, which is what makes this paired."""
    rng = random.Random(seed)
    n = len(games)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.5
    point = diff(games, x, y)
    deltas = []
    for _ in range(n_boot):
        sample = [games[rng.randrange(n)] for _ in range(n)]
        deltas.append(diff(sample, x, y))
    deltas.sort()
    lo = deltas[int(0.025 * n_boot)]
    hi = deltas[int(0.975 * n_boot)]
    p_gt = sum(1 for d in deltas if d > 0) / n_boot
    return point, lo, hi, p_gt


def worst_case(games, x, y):
    """Assign EVERY censored game against whichever direction the data shows.

    If x leads, hand every censored game to y; if y leads, hand them to x. The
    adverse assignment has to follow the observed sign: handing censored games
    to an arm that is ALREADY trailing is flattering rather than adverse, and
    would stamp any negative result "censoring-proof" for free.

    A result that survives this is censoring-proof. One that does not is
    reported as not censoring-proof, not quietly shown on clean games only.
    Censored games are the LONG games, so excluding them drops a biased slice
    rather than a random one (PLAN.md section 4).
    """
    point = diff(games, x, y)
    w, n_decided = shares(games)
    censored = sum(1 for g in games if g["timed_out"])
    denom = n_decided + censored
    if not denom:
        return 0.0, censored, 0
    if point >= 0:
        return (w[x] - (w[y] + censored)) / denom, censored, denom
    return ((w[x] + censored) - w[y]) / denom, censored, denom


def survival(games):
    """Per-arm survival among censored games, plus mean life at termination.

    Reported separately from win share on purpose. Surviving is not winning.
    """
    cens = [g for g in games if g["timed_out"] and g.get("seats")]
    alive = defaultdict(int)
    life = defaultdict(list)
    for g in cens:
        for arm, st in g["seats"].items():
            if st.get("alive"):
                alive[arm] += 1
            if st.get("life") is not None:
                life[arm].append(st["life"])
    return cens, alive, life


def pct(x):
    return f"{100 * x:+.2f} pp"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=None)
    ap.add_argument("--exclude-deck", nargs="+", default=None,
                    help="POST-HOC. The pre-registered analysis (PLAN.md 3) "
                         "pools all decks; excluding any is a decision made "
                         "after seeing results and must be reported as such, "
                         "alongside the pre-registered version, never instead "
                         "of it.")
    args = ap.parse_args()
    path = Path(args.results) if args.results else HERE / "runs" / "results.jsonl"
    rows = load(path)
    if args.exclude_deck:
        dropped = {d for d in args.exclude_deck}
        kept = [r for r in rows if r["precon"] not in dropped]
        if len(kept) == len(rows):
            raise SystemExit(f"--exclude-deck matched nothing: {sorted(dropped)}")
        rows = kept
        print("*" * 74)
        print(f"POST-HOC: excluding {sorted(dropped)}. NOT the pre-registered")
        print("analysis. Report this beside the pooled result, not instead of it.")
        print("*" * 74)
    games = flatten(rows)

    shas = sorted({r["shim_sha256_16"] for r in rows})
    clocks = sorted({r["clock"] for r in rows})
    # ASCII only in console output: this runs on a cp1252 Windows console where
    # anything else arrives as mojibake.
    print("=" * 74)
    print("ENGINE STRENGTH HEAD-TO-HEAD: pre-registered analysis (PLAN.md 3)")
    print("=" * 74)
    print(f"cells {len(rows)}  games {len(games)}  decks {len({g['precon'] for g in games})}")
    print(f"shim  {shas}")
    print(f"clock {clocks}")
    if len(shas) > 1 or len(clocks) > 1:
        print("  WARNING: mixed shim builds or clocks pooled. STUDY_PLAN 3c "
              "requires filtering on both; these are NOT comparable.")

    w, n_decided = shares(games)
    censored = sum(1 for g in games if g["timed_out"])
    drawn = len(games) - n_decided - censored
    print(f"\ndecided {n_decided}  censored {censored} "
          f"({100 * censored / max(1, len(games)):.1f}%)  other draws {drawn}")

    print("\n--- win share per arm (decided games, null 25%) ---")
    for a in ARM_ORDER:
        share = w[a] / n_decided if n_decided else 0
        print(f"  {a}  {ARM_DESC[a]:<40} {w[a]:>4} wins  {100 * share:>6.2f}%")

    print("\n--- PRIMARY: A - B, does the engine we ship beat stock Forge ---")
    point, lo, hi, p_gt = boot_ci(games, "A", "B")
    print(f"  A - B = {pct(point)}   95% CI [{pct(lo)}, {pct(hi)}]   P(>0) = {p_gt:.3f}")
    verdict = ("SUPPORTED" if lo > 0 else
               "NEGATIVE, and the interval excludes 0" if hi < 0 else "NULL")
    print(f"  pre-registered directional hypothesis A - B > 0: {verdict}")
    wc, cens, denom = worst_case(games, "A", "B")
    # Only a directional conclusion can survive the bound. A null point
    # estimate has nothing to preserve, so it is neither proof nor failure.
    if point == 0:
        tag = "n/a, point estimate is 0"
    elif (point > 0 and wc > 0) or (point < 0 and wc < 0):
        tag = "censoring-proof"
    else:
        tag = "NOT censoring-proof"
    against = "B" if point >= 0 else "A"
    print(f"  worst-case bound (all {cens} censored games to {against}, "
          f"adverse to the observed direction): {pct(wc)}  -> {tag}")

    print("\n--- SECONDARY ---")
    for x, y, label in [("A", "D", "does SimLabHuman earn its keep inside our engine"),
                        ("B", "C", "what the floodgate does to an ungated stock AI"),
                        ("D", "B", "our policy alone vs stock Forge, both on Default")]:
        point, lo, hi, p_gt = boot_ci(games, x, y)
        wc, cens, _ = worst_case(games, x, y)
        print(f"  {x} - {y} = {pct(point):>10}  95% CI [{pct(lo)}, {pct(hi)}]"
              f"  worst-case {pct(wc)}")
        print(f"        {label}")

    # (A-D) - (C-B): does the profile's effect depend on the controller gating
    # it? The shim's own comment asserts this interaction by design.
    inter = diff(games, "A", "D") - diff(games, "C", "B")
    print(f"\n  interaction (A-D) - (C-B) = {pct(inter)}")
    print("        positive means the profile helps only when the plan "
          "controller gates it,")
    print("        which is what the shim's design comment claims.")

    print("\n--- SURVIVAL AT THE CLOCK (censored games only, never a win rate) ---")
    cens_games, alive, life = survival(games)
    if not cens_games:
        print("  no censored games carrying seat state")
    else:
        print(f"  {len(cens_games)} censored games with per-seat state")
        for a in ARM_ORDER:
            lifes = life.get(a, [])
            mean_life = sum(lifes) / len(lifes) if lifes else float("nan")
            print(f"  {a}  alive {alive.get(a, 0):>4}/{len(cens_games)} "
                  f"({100 * alive.get(a, 0) / len(cens_games):>5.1f}%)   "
                  f"mean life {mean_life:>6.1f}")

    print("\n--- EXPLORATORY: per deck (n=96/deck, SE 7.2 pp, NOT powered) ---")
    by_deck = defaultdict(list)
    for g in games:
        by_deck[g["precon"]].append(g)
    print(f"  {'precon':<24} {'A-B':>9} {'A':>7} {'B':>7} {'C':>7} {'D':>7} {'cens':>5}")
    for deck in sorted(by_deck):
        gs = by_deck[deck]
        dw, dn = shares(gs)
        dc = sum(1 for g in gs if g["timed_out"])
        cells_ = [f"{100 * dw[a] / dn:>6.1f}%" if dn else "     -" for a in ARM_ORDER]
        print(f"  {deck:<24} {pct(diff(gs, 'A', 'B')):>9} "
              f"{' '.join(cells_)} {dc:>5}")

    # If an arm genuinely plays better we would expect the spread across decks
    # to WIDEN, not compress. The correlation pilot measured the opposite
    # (slopes 0.167 agent vs 0.472 stock); this is the clean check.
    print("\n--- spread across decks per arm ---")
    for a in ARM_ORDER:
        vals = []
        for deck, gs in by_deck.items():
            dw, dn = shares(gs)
            if dn:
                vals.append(100 * dw[a] / dn)
        if vals:
            print(f"  {a}  min {min(vals):>5.1f}%  max {max(vals):>5.1f}%  "
                  f"spread {max(vals) - min(vals):>5.1f} pp")

    # Diagnostic, not an outcome: confirms the rotation actually balanced seats.
    # Forge's seat bias is measured at seat 1 ~11% and seat 4 ~36%, far larger
    # than any plausible skill effect, so balance is what makes this valid.
    print("\n--- diagnostic: seat balance and seat bias ---")
    seat_wins = defaultdict(int)
    seat_arm = defaultdict(int)
    for g in games:
        if g["winner_arm"]:
            for seat, arm in g["seat_arms"].items():
                if arm == g["winner_arm"]:
                    seat_wins[seat] += 1
        for seat, arm in g["seat_arms"].items():
            seat_arm[(seat, arm)] += 1
    tot = sum(seat_wins.values())
    for seat in sorted(seat_wins):
        print(f"  seat {seat} won {seat_wins[seat]:>4} "
              f"({100 * seat_wins[seat] / max(1, tot):>5.1f}% of decided)")
    counts = defaultdict(set)
    for (seat, arm), c in seat_arm.items():
        counts[arm].add(c)
    balanced = all(len(v) == 1 for v in counts.values())
    print(f"  each arm sat in every seat an equal number of games: {balanced}")
    if not balanced:
        print("  WARNING: rotation is UNBALANCED, so seat bias is not cancelled "
              "and no arm comparison above is trustworthy.")


if __name__ == "__main__":
    main()
