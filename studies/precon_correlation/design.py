#!/usr/bin/env python3
"""Experimental design + power analysis for the precon correlation study.

Question: does the humanized Sim Lab agent predict *human* precon win rates
better than stock Forge AI does?

Ground truth: Playgroup.gg's 66-precon tier list (studies/.../ground_truth.json),
10,982 tracked human games with stock decklists.

This script does no simulating. It sizes the experiment: how many sim games per
precon are needed before the correlation stops being drowned by sampling noise,
which precons are worth including, and what that costs in VM hours.

Stdlib only, consistent with engine/.

Usage:
    python3 studies/precon_correlation/design.py
    python3 studies/precon_correlation/design.py --min-games 150
"""

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Measured on the production VM (engine/SIM_PERFORMANCE.md, 2026-08-02).
# Steady-state gameplay: 8-game single-launch jobs summed 833-969 s -> ~110 s/game.
SEC_PER_GAME = 110.0
# Rotation launches one JVM per deck in the pod; warm single-launch overhead
# clustered 25-35 s. 40 s is a planning figure, deliberately not the 93 s
# cold-container outlier, which SIM_PERFORMANCE.md flags as needing a re-measure.
SEC_PER_JVM_LAUNCH = 40.0
POD_SIZE = 4  # 4-player Commander => rotations == 4

# Precon set release years (public set info, not Playgroup data). Forge
# implements cards over time, so recent sets are a card-coverage risk: a precon
# containing unimplemented cards produces an invalid sim, not a low win rate.
# Verify coverage against the deployed Forge release before trusting any cohort.
SET_YEAR = {
    "Streets of New Capenna": 2022,
    "Commander Legends: Battle for Baldur's Gate": 2022,
    "Dominaria United": 2022,
    "March of the Machine": 2023,
    "Tales of Middle-earth": 2023,
    "Commander Masters": 2023,
    "The Lost Caverns of Ixalan": 2023,
    "Murders at Karlov Manor": 2024,
    "Fallout": 2024,
    "Outlaws of Thunder Junction": 2024,
    "Modern Horizons 3": 2024,
    "Bloomburrow": 2024,
    "Duskmourn: House of Horror": 2024,
    "Tarkir Dragonstorm": 2025,
    "Final Fantasy": 2025,
    "Edge of Eternities": 2025,
    "Lorwyn Eclipsed": 2026,
    "Teenage Mutant Ninja Turtles": 2026,
    "Secrets of Strixhaven": 2026,
    "Goblin Storm": 2026,
    "Marvel Super Heroes": 2026,
}


def binom_se(p, n):
    """Standard error of a proportion, in percentage points."""
    return 100.0 * math.sqrt(max(p * (1.0 - p), 0.0) / n)


def mean(xs):
    return sum(xs) / len(xs)


def variance(xs):
    """Sample variance."""
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def reliability(var_observed, var_noise):
    """Fraction of observed variance that is real signal.

    var_observed = var_true + var_noise, so reliability = var_true/var_observed.
    Clamped to (0, 1]; a non-positive estimate means noise swamps the spread.
    """
    var_true = var_observed - var_noise
    if var_true <= 0:
        return 0.0
    return var_true / var_observed


def describe_cohort(decks, label):
    wrs = [d["human_win_rate"] for d in decks]
    games = [d["human_games"] for d in decks]
    # Per-deck sampling variance of the human estimate, averaged over the cohort.
    var_noise = mean([binom_se(d["human_win_rate"] / 100.0, d["human_games"]) ** 2
                      for d in decks])
    var_obs = variance(wrs)
    rel = reliability(var_obs, var_noise)

    print(f"\n{label}")
    print(f"  decks                     {len(decks)}")
    print(f"  human win rate range      {min(wrs):.2f}% .. {max(wrs):.2f}%  "
          f"(spread {max(wrs) - min(wrs):.1f} pp)")
    print(f"  observed SD               {math.sqrt(var_obs):.2f} pp")
    print(f"  mean human games/deck     {mean(games):.0f}  (min {min(games)}, max {max(games)})")
    print(f"  mean human SE/deck        {math.sqrt(var_noise):.2f} pp")
    print(f"  => true signal SD         {math.sqrt(max(var_obs - var_noise, 0)):.2f} pp")
    print(f"  => human reliability      {rel:.3f}")
    return {"decks": decks, "var_true": max(var_obs - var_noise, 0.0),
            "rel_human": rel, "n": len(decks)}


def sim_plan(cohort, sim_games_options, true_r=0.70):
    """For each candidate sim sample size, expected attenuation and cost."""
    var_true = cohort["var_true"]
    rel_h = cohort["rel_human"]
    n = cohort["n"]

    print(f"\n  Sim sizing (assumed latent correlation r_true = {true_r:.2f}, "
          f"cohort n = {n} decks)")
    print(f"  {'games':>6} {'sim SE':>8} {'rel_sim':>8} {'E[r_obs]':>9} "
          f"{'p<.05?':>7} {'VM hours':>9} {'both arms':>10}")
    for g in sim_games_options:
        # Sim win rates centre near 25% in a 4-player pod; use 25% for the SE
        # bound since p(1-p) is maximal near there among plausible values.
        se_sim = binom_se(0.25, g)
        var_noise_sim = se_sim ** 2
        rel_s = var_true / (var_true + var_noise_sim) if var_true > 0 else 0.0
        r_obs = true_r * math.sqrt(rel_h * rel_s)
        # Critical |r| for two-sided p<.05 at this n (Fisher z approximation).
        crit = 1.96 / math.sqrt(max(n - 3, 1))
        crit_r = math.tanh(crit)
        sig = "yes" if r_obs > crit_r else "NO"
        hours_one = n * (g * SEC_PER_GAME + POD_SIZE * SEC_PER_JVM_LAUNCH) / 3600.0
        print(f"  {g:>6} {se_sim:>7.2f}p {rel_s:>8.3f} {r_obs:>9.3f} "
              f"{sig:>7} {hours_one:>8.1f}h {hours_one * 2:>9.1f}h")
    print(f"  (critical |r| for p<.05 at n={n} decks: {math.tanh(1.96 / math.sqrt(max(n - 3, 1))):.3f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-games", type=int, default=150,
                    help="human-game threshold for the primary cohort")
    args = ap.parse_args()

    data = json.loads((HERE / "ground_truth.json").read_text())
    decks = data["precons"]

    total = sum(d["human_games"] for d in decks)
    print("=" * 74)
    print("PRECON CORRELATION STUDY - DESIGN / POWER ANALYSIS")
    print("=" * 74)
    print(f"\nGround truth: {data['source']} (captured {data['captured']})")
    print(f"  precons parsed            {len(decks)}  "
          f"(source claims {data['precon_count_claimed']})")
    print(f"  games summed              {total}  "
          f"(source claims {data['total_games_claimed']})")
    ok = (len(decks) == data["precon_count_claimed"]
          and total == data["total_games_claimed"])
    print(f"  integrity check           {'PASS' if ok else 'MISMATCH - investigate'}")

    for d in decks:
        d["year"] = SET_YEAR.get(d["set"])
    unmapped = [d["set"] for d in decks if d["year"] is None]
    if unmapped:
        print(f"  WARNING unmapped sets      {sorted(set(unmapped))}")

    full = describe_cohort(decks, "COHORT A - all 66")
    hi_n = [d for d in decks if d["human_games"] >= args.min_games]
    describe_cohort(hi_n, f"COHORT B - human_games >= {args.min_games}")
    pre25 = [d for d in decks if (d["year"] or 9999) <= 2024]
    c_pre25 = describe_cohort(pre25, "COHORT C - released 2024 or earlier "
                                     "(Forge coverage safest)")

    sim_plan(full, [16, 32, 64, 128])
    sim_plan(c_pre25, [16, 32, 64, 128])

    print("\n" + "=" * 74)
    print("COHORT SIZE BY RELEASE YEAR (Forge card-coverage risk)")
    print("=" * 74)
    by_year = {}
    for d in decks:
        by_year.setdefault(d["year"], []).append(d)
    cumulative = 0
    for y in sorted(by_year, key=lambda v: (v is None, v)):
        n = len(by_year[y])
        cumulative += n
        wrs = [x["human_win_rate"] for x in by_year[y]]
        print(f"  {y}  {n:>2} decks  win% {min(wrs):>5.1f}-{max(wrs):>5.1f}  "
              f"(cumulative {cumulative})")

    print("\n" + "=" * 74)
    print(f"COHORT C MEMBERS ({len(pre25)} decks, 2024 and earlier)")
    print("=" * 74)
    print(f"  {'win%':>7} {'games':>6} {'tier':>4} {'yr':>5}  {'precon':<26} {'set'}")
    for d in sorted(pre25, key=lambda x: -x["human_win_rate"]):
        print(f"  {d['human_win_rate']:>6.2f}% {d['human_games']:>6} "
              f"{d['tier']:>4} {d['year']:>5}  {d['name']:<26} {d['set']}")


if __name__ == "__main__":
    main()
