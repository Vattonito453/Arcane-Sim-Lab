#!/usr/bin/env python3
"""Does a sim predict real playgroup win rates, and can we correct it?

Ground truth: playgroup.gg, 66 Commander precons, 10,982 human games, win
rates 12.0-40.9% (mean 24.2% against a 25% four-player null).

Three questions, in order of commercial importance:

 1. BASELINE. How well does the raw sim win rate predict the human win rate?
    Compared against two rivals a customer could use for free: guessing the
    mean, and a model built from decklist statistics alone.
 2. MECHANISM. Forge blocks ~15-21% of attacking creatures, so ~80% of
    attackers get through. If that is really distorting results, the
    sim-minus-human residual must correlate with how much a deck wants to
    attack. A curve fit would not predict its own sign in advance; this does.
 3. CORRECTION. Fit sim (+ features) -> human, leave-one-out. Every number
    reported is out-of-sample, because in-sample fit on 66 decks will happily
    report a moat that does not exist.

Usage:  python3 studies/precon_predict/analyze.py [--arm runs_stock]
"""
from __future__ import annotations

import argparse, json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402


def load(arm):
    feats = {r["name"]: r for r in
             json.loads((HERE / "features.json").read_text(encoding="utf-8"))}
    res = json.loads((HERE / arm / "cohort_results.json").read_text(encoding="utf-8"))
    rows = []
    for r in res:
        if not r["sim_games"]:
            continue
        f = feats.get(r["name"])
        if not f:
            continue
        d = dict(f)
        d.update(sim=100.0 * r["sim_rate"], sim_games=r["sim_games"],
                 human=r["human"], human_n=r["human_n"])
        rows.append(d)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="runs_stock")
    ap.add_argument("--min-games", type=int, default=8)
    args = ap.parse_args()

    rows = [r for r in load(args.arm) if r["sim_games"] >= args.min_games]
    if len(rows) < 10:
        sys.exit(f"only {len(rows)} decks have >= {args.min_games} games; wait for more")
    y = [r["human"] for r in rows]
    w = [r["human_n"] for r in rows]
    sim = [r["sim"] for r in rows]
    n = len(rows)
    gp = sorted(r["sim_games"] for r in rows)
    print(f"arm {args.arm}: {n} decks, median {gp[n//2]} sim games/deck, "
          f"{sum(r['sim_games'] for r in rows)} deck-games\n")

    print("=" * 78)
    print("1. BASELINE  -- how good is the raw sim, vs free alternatives?")
    print("=" * 78)
    print("  raw sim win rate vs human:  r %+.3f   rho %+.3f"
          % (model.pearson(sim, y), model.spearman(sim, y)))
    print("  " + model.fmt(model.report("raw sim used as-is", sim, y, w)))
    mean = [sum(y) / n] * n
    print("  " + model.fmt(model.report("rival: guess the mean", mean, y, w)))
    Xf = [[r["creatures"], r["avg_cmc"]] for r in rows]
    print("  " + model.fmt(model.report("rival: decklist stats (LOO)",
                                        model.loo(Xf, y, 1.0), y, w)))

    print()
    print("=" * 78)
    print("2. MECHANISM -- is Forge's under-blocking visible in the residual?")
    print("=" * 78)
    resid = [s - h for s, h in zip(sim, y)]
    print("  sim - human residual: mean %+.1f pp (sim inflates if positive)"
          % (sum(resid) / n))
    print("  PREDICTION: aggression correlates POSITIVELY with the residual")
    for f in ("aggression", "evasion", "creatures", "avg_power", "total_power",
              "interaction", "avg_cmc", "complexity"):
        x = [r[f] for r in rows]
        mark = ""
        if f in ("aggression", "evasion", "creatures", "avg_power", "total_power"):
            mark = "  <-- attack-y" 
        print("    %-12s r %+.3f  rho %+.3f%s"
              % (f, model.pearson(x, resid), model.spearman(x, resid), mark))

    print()
    print("=" * 78)
    print("3. CORRECTION -- can we turn the sim into a real prediction? (LOO)")
    print("=" * 78)
    cands = {
        "sim only (calibration)": ["sim"],
        "sim + aggression": ["sim", "aggression"],
        "sim + aggression + interaction": ["sim", "aggression", "interaction"],
        "sim + creatures + avg_cmc": ["sim", "creatures", "avg_cmc"],
        "sim + aggr + inter + cmc + creat": ["sim", "aggression", "interaction",
                                             "avg_cmc", "creatures"],
    }
    best = None
    for label, fs in cands.items():
        X = [[r[f] for f in fs] for r in rows]
        p = model.loo(X, y, 1.0)
        rep = model.report(label, p, y, w)
        print("  " + model.fmt(rep))
        if best is None or rep["mae"] < best[0]["mae"]:
            best = (rep, fs)
    print()
    rep, fs = best
    base = model.report("guess the mean", mean, y, w)
    raw = model.report("raw sim", sim, y, w)
    print(f"  BEST: {rep['name']}  ({', '.join(fs)})")
    print(f"    vs guessing the mean : MAE {base['mae']:.2f} -> {rep['mae']:.2f} pp "
          f"({100*(base['mae']-rep['mae'])/base['mae']:+.0f}%)")
    print(f"    vs raw sim           : MAE {raw['mae']:.2f} -> {rep['mae']:.2f} pp "
          f"({100*(raw['mae']-rep['mae'])/raw['mae']:+.0f}%)")

    X = [[r[f] for f in fs] for r in rows]
    fit = model.fit_ridge(X, y, 1.0)
    (HERE / f"model_{args.arm}.json").write_text(json.dumps({
        "features": fs, "weights": list(getattr(fit, "weights", [])),
        "mu": getattr(fit, "mu", []), "sd": getattr(fit, "sd", []),
        "intercept": getattr(fit, "intercept", 0.0),
        "loo": {k: rep[k] for k in ("mae", "wmae", "rmse", "pearson", "spearman")},
        "n_decks": n, "arm": args.arm,
    }, indent=1), encoding="utf-8")
    print(f"\n  fitted model -> model_{args.arm}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
