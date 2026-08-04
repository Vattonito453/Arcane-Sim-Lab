#!/usr/bin/env python3
"""Analyze the precon correlation study.

Runs the pre-registered outcomes from STUDY_PLAN.md §5, plus the post-hoc
checks recorded in §7a (clearly labelled as post-hoc).

Reads `runs/results.jsonl` for per-cell win rates and the per-game
`runs/shim_raw_*.jsonl` records for censoring and game-length analysis.

Rows are filtered to one (clock, shim) configuration by default, because the
shim jar was rebuilt mid-session once and passes at different clocks must never
be pooled (STUDY_PLAN.md §3c).

Stdlib only.

Usage:
    python3 studies/precon_correlation/analyze.py
    python3 studies/precon_correlation/analyze.py --clock 900
    python3 studies/precon_correlation/analyze.py --runs-dir runs --boot 10000
"""

import argparse
import json
import math
import random
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("shim_stock", "agent_v3")

# Coarse archetype tags for the post-hoc residual check (§7a). Hand-assigned
# from each precon's commander and theme; "creature" means a straightforward
# creatures-and-combat plan, which is the archetype Forge's AI handles best.
ARCHETYPE = {
    "Planeswalker Party": "planeswalker",
    "Tricky Terrain": "lands-counters",
    "Explorers of the Deep": "creature",
    "Doom Prevails": "creature",
    "Blight Curse": "enchantment-curse",
    "Mutant Menace": "counters-value",
    "Grand Larceny": "theft-value",
    "Deadly Disguise": "cloak-creature",
}


def rank(vals):
    """Average-tied ranks, ascending."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def pearson(x, y, w=None):
    n = len(x)
    if n < 3:
        return None
    if w is None:
        w = [1.0] * n
    sw = sum(w)
    mx = sum(wi * xi for wi, xi in zip(w, x)) / sw
    my = sum(wi * yi for wi, yi in zip(w, y)) / sw
    cov = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y))
    vx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x))
    vy = sum(wi * (yi - my) ** 2 for wi, yi in zip(w, y))
    den = math.sqrt(vx * vy)
    return cov / den if den else None


def spearman(x, y):
    if len(x) < 3:
        return None
    return pearson(rank(x), rank(y))


def ols_slope(x, y):
    """Slope of y on x: calibration slope of sim against human."""
    if len(x) < 3:
        return None
    mx, my = st.mean(x), st.mean(y)
    den = sum((xi - mx) ** 2 for xi in x)
    if not den:
        return None
    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / den


def wilson_se(p, n):
    return 100.0 * math.sqrt(max(p * (1 - p), 0.0) / n) if n else float("nan")


def load_cells(runs_dir, clock, shim):
    path = runs_dir / "results.jsonl"
    if not path.exists():
        raise SystemExit(f"no results at {path}")
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("win_rate_clean") is not None]
    if clock:
        rows = [r for r in rows if r["clock"] == clock]
    if shim:
        rows = [r for r in rows if r.get("shim_sha256_16") == shim]
    return rows


def load_games(runs_dir):
    """Per-game records, tagged with the cell they came from."""
    games = []
    for p in sorted(runs_dir.glob("shim_raw_study_*_rot*.jsonl")):
        stem = p.name[len("shim_raw_"):].rsplit("_rot", 1)[0]
        arm = "agent_v3" if "_agent_v3_" in stem else (
            "shim_stock" if "_shim_stock_" in stem else "?")
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"rec":"result"' not in line.replace(" ", ""):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("rec") != "result" or not d.get("ms"):
                continue
            secs = d["ms"] / 1000.0
            turns = d.get("turns") or 0
            games.append({
                "arm": arm, "cell": stem, "secs": secs, "turns": turns,
                "tps": turns / secs if secs else 0.0,
                "timed_out": bool(d.get("timedOut")),
            })
    return games


def pct(vals, q):
    if not vals:
        return float("nan")
    s = sorted(vals)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(HERE / "runs"))
    ap.add_argument("--clock", type=int, default=900)
    ap.add_argument("--shim", default=None, help="shim_sha256_16 to filter on")
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260803)
    args = ap.parse_args()

    runs = Path(args.runs_dir)
    shim = args.shim
    cells = load_cells(runs, args.clock, shim)
    if not shim:
        shas = {c.get("shim_sha256_16") for c in cells}
        if len(shas) > 1:
            raise SystemExit(f"multiple shim builds present {shas}; pass --shim")

    print("=" * 74)
    print("PRECON CORRELATION STUDY - ANALYSIS")
    print("=" * 74)
    print(f"cells {len(cells)}  clock {args.clock}s  "
          f"shim {next(iter({c.get('shim_sha256_16') for c in cells}), '?')}")

    by_arm = {a: {c["precon"]: c for c in cells if c["arm"] == a} for a in ARMS}
    for a in ARMS:
        print(f"  {a:<11} {len(by_arm[a])} decks")

    # ---- per-arm correlations (pre-registered secondary 1, 2) --------------
    print("\n" + "-" * 74)
    print("PER-ARM CORRELATION")
    print("-" * 74)
    for a in ARMS:
        rows = list(by_arm[a].values())
        if len(rows) < 3:
            print(f"{a}: n={len(rows)}, too few to correlate")
            continue
        h = [r["human_win_rate"] for r in rows]
        s = [r["win_rate_clean"] * 100 for r in rows]
        w = [1.0 / max(wilson_se(r["human_win_rate"] / 100, r["human_games"]) ** 2, 1e-9)
             for r in rows]
        rho = spearman(h, s)
        rp = pearson(h, s)
        rpw = pearson(h, s, w)
        slope = ols_slope(h, s)
        print(f"{a}: n={len(rows)}")
        print(f"  Spearman            {rho: .3f}" if rho is not None else "  Spearman  n/a")
        print(f"  Pearson             {rp: .3f}" if rp is not None else "")
        print(f"  Pearson (wtd by 1/SE^2) {rpw: .3f}" if rpw is not None else "")
        print(f"  calibration slope   {slope: .3f}   (1.0 = sim tracks human 1:1)"
              if slope is not None else "")
        print(f"  sim spread          {min(s):.1f}-{max(s):.1f} "
              f"({max(s)-min(s):.1f} pp)   human {min(h):.1f}-{max(h):.1f} "
              f"({max(h)-min(h):.1f} pp)")
        print(f"  mean |gap|          {st.mean([abs(si-hi) for si,hi in zip(s,h)]):.1f} pp")

    # ---- paired primary outcome ------------------------------------------
    print("\n" + "-" * 74)
    print("PRIMARY OUTCOME: paired delta-r (agent minus stock)")
    print("-" * 74)
    shared = sorted(set(by_arm["shim_stock"]) & set(by_arm["agent_v3"]),
                    key=lambda n: -by_arm["shim_stock"][n]["human_win_rate"])
    print(f"decks in both arms: {len(shared)}")
    print(f"  {'precon':<23}{'human':>7}{'stock':>9}{'agent':>9}   {'gap_s':>7}{'gap_a':>7}")
    for n in shared:
        c1, c2 = by_arm["shim_stock"][n], by_arm["agent_v3"][n]
        h = c1["human_win_rate"]
        s1, s2 = c1["win_rate_clean"] * 100, c2["win_rate_clean"] * 100
        print(f"  {n:<23}{h:>6.2f}%{s1:>8.1f}%{s2:>8.1f}%   "
              f"{s1-h:>+6.1f} {s2-h:>+6.1f}")

    if len(shared) >= 4:
        h = [by_arm["shim_stock"][n]["human_win_rate"] for n in shared]
        a1 = [by_arm["shim_stock"][n]["win_rate_clean"] * 100 for n in shared]
        a2 = [by_arm["agent_v3"][n]["win_rate_clean"] * 100 for n in shared]
        r1, r2 = spearman(h, a1), spearman(h, a2)
        if r1 is not None and r2 is not None:
            print(f"\n  Spearman stock {r1: .3f}   agent {r2: .3f}   "
                  f"delta {r2-r1:+.3f}")
            rng = random.Random(args.seed)
            deltas = []
            idx = range(len(shared))
            for _ in range(args.boot):
                pick = [rng.choice(idx) for _ in idx]
                bh = [h[i] for i in pick]
                b1 = [a1[i] for i in pick]
                b2 = [a2[i] for i in pick]
                x, y = spearman(bh, b1), spearman(bh, b2)
                if x is not None and y is not None:
                    deltas.append(y - x)
            if deltas:
                deltas.sort()
                lo = deltas[int(0.025 * (len(deltas) - 1))]
                hi = deltas[int(0.975 * (len(deltas) - 1))]
                frac = sum(1 for d in deltas if d > 0) / len(deltas)
                print(f"  paired bootstrap 95% CI on delta: [{lo:+.3f}, {hi:+.3f}]")
                print(f"  P(delta > 0) = {frac:.3f}   ({len(deltas)} resamples)")
                verdict = ("agent better" if lo > 0 else
                           "stock better" if hi < 0 else
                           "NULL - interval includes 0")
                print(f"  => {verdict}")
        # mean absolute gap comparison
        g1 = st.mean([abs(x - y) for x, y in zip(a1, h)])
        g2 = st.mean([abs(x - y) for x, y in zip(a2, h)])
        print(f"\n  mean |gap|: stock {g1:.1f} pp, agent {g2:.1f} pp "
              f"({'agent better' if g2 < g1 else 'stock better'})")

    # ---- pre-registered secondary 3: direction accuracy ------------------
    print("\n" + "-" * 74)
    print("SECONDARY: side-of-baseline accuracy (25% four-player baseline)")
    print("-" * 74)
    for a in ARMS:
        rows = list(by_arm[a].values())
        if not rows:
            continue
        ok = sum(1 for r in rows
                 if (r["win_rate_clean"] * 100 >= 25) == (r["human_win_rate"] >= 25))
        print(f"  {a:<11} {ok}/{len(rows)} correct side")

    # ---- censoring, and the clock recommendation ------------------------
    print("\n" + "-" * 74)
    print("CENSORING AND GAME LENGTH (per-game records)")
    print("-" * 74)
    games = [g for g in load_games(runs) if g["arm"] in ARMS]
    for a in ARMS:
        gs = [g for g in games if g["arm"] == a]
        if not gs:
            continue
        to = [g for g in gs if g["timed_out"]]
        nat = [g for g in gs if not g["timed_out"]]
        print(f"  {a:<11} n={len(gs):>4}  censored {len(to):>3} ({len(to)/len(gs):>5.1%})")
        if nat:
            secs = [g["secs"] for g in nat]
            print(f"              natural: median {st.median(secs):>5.0f}s  "
                  f"p95 {pct(secs,0.95):>5.0f}s  p99 {pct(secs,0.99):>5.0f}s  "
                  f"max {max(secs):>5.0f}s")
            print(f"              turns/sec: min {min(g['tps'] for g in nat):.3f}  "
                  f"median {st.median([g['tps'] for g in nat]):.3f}")
        if to:
            print(f"              censored turns/sec: max "
                  f"{max(g['tps'] for g in to):.3f}")
    if games:
        agent_nat = [g["secs"] for g in games
                     if g["arm"] == "agent_v3" and not g["timed_out"]]
        if agent_nat:
            rec = int(math.ceil(pct(agent_nat, 0.99) * 1.5 / 60.0) * 60)
            print(f"\n  Recommended full-run clock (agent p99 x 1.5): {rec}s")
            print(f"  Rationale: set the clock from the arm with the longer games,")
            print(f"  so censoring is comparable across arms (STUDY_PLAN.md §7a.2).")

    # ---- post-hoc: archetype residuals ---------------------------------
    print("\n" + "-" * 74)
    print("POST-HOC (not pre-registered, added 2026-08-03): archetype residuals")
    print("-" * 74)
    for a in ARMS:
        rows = list(by_arm[a].values())
        if not rows:
            continue
        print(f"  {a}:")
        buckets = defaultdict(list)
        for r in rows:
            tag = ARCHETYPE.get(r["precon"], "?")
            buckets[tag].append(r["win_rate_clean"] * 100 - r["human_win_rate"])
        for tag, gaps in sorted(buckets.items(), key=lambda kv: -st.mean(kv[1])):
            print(f"    {tag:<20} n={len(gaps)}  mean gap {st.mean(gaps):>+6.1f} pp")
        creature = [g for t, gs in buckets.items() if t == "creature" for g in gs]
        other = [g for t, gs in buckets.items() if t != "creature" for g in gs]
        if creature and other:
            print(f"    creature {st.mean(creature):+.1f} pp vs "
                  f"non-creature {st.mean(other):+.1f} pp  "
                  f"(difference {st.mean(creature)-st.mean(other):+.1f} pp)")

    print("\n" + "=" * 74)
    print("Interpretation limits: see STUDY_PLAN.md §1 (ground-truth reliability")
    print("0.463, so even a perfect predictor caps near r=0.68), §3d (control")
    print("gauntlet too weak), §7a.2 (arm-dependent censoring).")


if __name__ == "__main__":
    main()
