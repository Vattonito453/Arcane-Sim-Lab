#!/usr/bin/env python3
"""How many games does a user actually have to wait for?

The product cannot ask someone to sit through a 20-minute-per-game gauntlet.
This subsamples the completed cohort to ask what the prediction is worth at
k games per deck, so the sample size is chosen from evidence rather than from
"more is better". Survival is used rather than win rate because it is not a
1-in-4 event and therefore converges faster.
"""
from __future__ import annotations
import collections, glob, json, os, random, re, statistics as st, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402
from run_cohort import pods_for_round  # noqa: E402

SEAT = re.compile(r"^Ai\((\d+)\)-")
CELL = re.compile(r"c_r(\d+)_p(\d+)_i(\d+)\.jsonl$")


def per_game(arm):
    """(won, survived) per deck per DECIDED game."""
    cohort = json.loads((HERE / "cohort.json").read_text(encoding="utf-8"))
    obs = collections.defaultdict(list)
    for f in sorted((HERE / arm).glob("c_r*.jsonl")):
        m = CELL.search(os.path.basename(f))
        if not m:
            continue
        rnd, pod_i, inv = int(m.group(1)), int(m.group(2)), int(m.group(3))
        pods = pods_for_round(cohort, rnd)
        if pod_i >= len(pods):
            continue
        order = pods[pod_i][inv:] + pods[pod_i][:inv]
        names = [cohort[i]["name"] for i in order]
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"result"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") != "result" or r.get("timedOut") or not r.get("winner"):
                continue
            seats = r.get("seats") or []
            mm = SEAT.match(r["winner"])
            ws = int(mm.group(1)) - 1 if mm else -1
            for i, nm in enumerate(names):
                alive = bool(seats[i].get("alive")) if i < len(seats) else False
                obs[nm].append((1 if i == ws else 0, 1 if alive else 0))
    return obs, cohort


def main(arm="runs_stock", draws=20):
    obs, cohort = per_game(arm)
    feats = {r["name"]: r for r in
             json.loads((HERE / "features.json").read_text(encoding="utf-8"))}
    truth = {c["name"]: c["human"] for c in cohort}
    decks = [n for n in obs if len(obs[n]) >= 30 and n in feats]
    print(f"{arm}: {len(decks)} decks with >=30 decided games\n")
    print("games/deck   rank corr with human truth   (mean of %d draws)" % draws)
    random.seed(9)
    for k in (4, 8, 12, 16, 24, 32, 40):
        rhos, maes = [], []
        for _ in range(draws):
            rows = []
            for n in decks:
                samp = random.sample(obs[n], min(k, len(obs[n])))
                d = dict(feats[n])
                d["survival"] = 100.0 * sum(x[1] for x in samp) / len(samp)
                rows.append((n, d))
            yy = [truth[n] for n, _ in rows]
            X = [[d["survival"], d["creatures"], d["avg_cmc"]] for _, d in rows]
            p = model.loo(X, yy, 1.0)
            rhos.append(model.spearman(p, yy))
            maes.append(st.mean([abs(a - b) for a, b in zip(p, yy)]))
        print("   %2d          rho %.3f (sd %.3f)   MAE %.3f"
              % (k, st.mean(rhos), st.pstdev(rhos), st.mean(maes)))
    print("\nbaseline (guess the mean) MAE 4.249 pp; full-sample rho 0.477")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "runs_stock"))
