#!/usr/bin/env python3
"""Is a win rate the best signal a sim can give us, or are we throwing away
most of the information?

A binary win/loss discards how a deck lost. A deck that consistently finishes
second is stronger than one that dies first, and both score zero wins. The
shim's result records carry every seat's final life and alive flag, so
placement-like signals cost nothing extra to compute.
"""
from __future__ import annotations
import collections, glob, json, os, re, statistics as st, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402
from run_cohort import pods_for_round  # noqa: E402

SEAT = re.compile(r"^Ai\((\d+)\)-")
CELL = re.compile(r"c_r(\d+)_p(\d+)_i(\d+)\.jsonl$")


def collect(arm):
    cohort = json.loads((HERE / "cohort.json").read_text(encoding="utf-8"))
    agg = collections.defaultdict(
        lambda: {"g": 0, "w": 0, "alive": 0, "life": 0.0, "liferank": 0.0})
    for f in sorted((HERE / arm).glob("c_r*.jsonl")):
        m = CELL.search(os.path.basename(f))
        if not m:
            continue
        rnd, pod_i, inv = int(m.group(1)), int(m.group(2)), int(m.group(3))
        pods = pods_for_round(cohort, rnd)
        if pod_i >= len(pods):
            continue
        pod = pods[pod_i]
        order = pod[inv:] + pod[:inv]
        names = [cohort[i]["name"] for i in order]
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") != "result":
                continue
            seats = r.get("seats") or []
            lives = [(s.get("life") if s.get("life") is not None else -99)
                     for s in seats]
            ranks = sorted(range(len(lives)), key=lambda i: -lives[i])
            rankof = {idx: pos for pos, idx in enumerate(ranks)}
            for i, nm in enumerate(names):
                a = agg[nm]
                a["g"] += 1
                if i < len(seats):
                    a["alive"] += 1 if seats[i].get("alive") else 0
                    a["life"] += max(-20, min(60, lives[i]))
                    a["liferank"] += (3 - rankof.get(i, 3)) / 3.0
            w = r.get("winner")
            if w and not r.get("draw"):
                mm = SEAT.match(w)
                if mm:
                    agg[names[int(mm.group(1)) - 1]]["w"] += 1
    return agg


def rows_for(arm, min_games=16):
    feats = {r["name"]: r for r in
             json.loads((HERE / "features.json").read_text(encoding="utf-8"))}
    out = []
    for nm, a in collect(arm).items():
        if a["g"] < min_games or nm not in feats:
            continue
        d = dict(feats[nm])
        g = a["g"]
        d.update(sim=100.0 * a["w"] / g, survival=100.0 * a["alive"] / g,
                 meanlife=a["life"] / g, liferank=a["liferank"] / g, n=g)
        out.append(d)
    return out


def main(arm="runs_stock"):
    rows = rows_for(arm)
    if len(rows) < 10:
        sys.exit(f"only {len(rows)} decks with data in {arm}")
    y = [r["human"] for r in rows]
    print(f"{arm}: {len(rows)} decks, median {st.median([r['n'] for r in rows]):.0f} games/deck\n")
    print("=== which sim signal tracks the human win rate best? ===")
    for k in ("sim", "survival", "meanlife", "liferank"):
        x = [r[k] for r in rows]
        print("  %-9s r %+.3f   rho %+.3f" % (k, model.pearson(x, y),
                                              model.spearman(x, y)))
    print("\n=== does a richer signal beat the win rate? (LOO) ===")
    print("  " + model.fmt(model.report("guess the mean",
                                        [sum(y) / len(y)] * len(y), y)))
    combos = [("decklist only", ["creatures", "avg_cmc"]),
              ("+ sim win rate", ["sim", "creatures", "avg_cmc"]),
              ("+ survival", ["survival", "creatures", "avg_cmc"]),
              ("+ liferank", ["liferank", "creatures", "avg_cmc"]),
              ("+ meanlife", ["meanlife", "creatures", "avg_cmc"]),
              ("+ every sim signal", ["sim", "survival", "liferank",
                                      "creatures", "avg_cmc"])]
    for label, fs in combos:
        X = [[r[f] for f in fs] for r in rows]
        print("  " + model.fmt(model.report(label, model.loo(X, y, 1.0), y)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "runs_stock"))
