#!/usr/bin/env python3
"""Per-deck sim win rates over DECIDED games only.

The agent arm lost 34.1% of its games to the 1200s wall clock against 9.7%
for stock, and its timed-out games have FEWER turns than its finished ones
(43.0 vs 53.0) -- it deliberates more per turn, so it dies to the clock
mid-game rather than because games run long. Counting a wall-clock kill as a
non-win deflates every agent win rate (cohort mean 16.2% against a 25% null)
and makes the two arms different measurement scales. Any arm-to-arm number
has to be computed here, on games that actually finished.
"""
from __future__ import annotations
import collections, glob, json, math, os, re, statistics as st, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model  # noqa: E402
from run_cohort import pods_for_round  # noqa: E402

SEAT = re.compile(r"^Ai\((\d+)\)-")
CELL = re.compile(r"c_r(\d+)_p(\d+)_i(\d+)\.jsonl$")


def tally(arm, decided_only=True, min_games=12):
    cohort = json.loads((HERE / "cohort.json").read_text(encoding="utf-8"))
    feats = {r["name"]: r for r in
             json.loads((HERE / "features.json").read_text(encoding="utf-8"))}
    played, wins = collections.Counter(), collections.Counter()
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
            if '"result"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") != "result":
                continue
            if decided_only and (r.get("timedOut") or not r.get("winner")):
                continue
            for nm in names:
                played[nm] += 1
            w = r.get("winner")
            if w and not r.get("draw"):
                mm = SEAT.match(w)
                if mm:
                    wins[names[int(mm.group(1)) - 1]] += 1
    rows = []
    for c in cohort:
        n = played[c["name"]]
        if n < min_games or c["name"] not in feats:
            continue
        d = dict(feats[c["name"]])
        d["sim"] = 100.0 * wins[c["name"]] / n
        d["n"] = n
        rows.append(d)
    return rows


def reliability(rows):
    """Each deck's OWN p and OWN n. A fixed p=0.25 is a design-time upper
    bound; applied to an arm whose mean is 16% it inflates that arm's noise
    by 1.38x and only that arm's, which manufactures a reliability gap."""
    s = [r["sim"] for r in rows]
    noise = st.mean([(p / 100.0) * (1 - p / 100.0) / r["n"] * 10000.0
                     for p, r in zip(s, rows)])
    obs = st.pvariance(s)
    true = max(obs - noise, 0.0)
    return true / obs if obs else 0.0, math.sqrt(true)


def main(arms=None):
    """Arms on the command line, e.g. `decided.py runs_stock runs_agent
    runs_agent_015`; default is the two 2026-08-26 arms. A partial arm is
    fine: tally() reads whatever cells exist and drops decks under min_games."""
    arms = arms or ["runs_stock", "runs_agent"]
    print("DECIDED GAMES ONLY -- the honest arm comparison\n")
    print("%-26s" % "metric" + "".join("%16s" % a for a in arms))
    print("-" * (26 + 16 * len(arms)))
    o = {}
    for arm in arms:
        rows = tally(arm)
        y = [r["human"] for r in rows]
        s = [r["sim"] for r in rows]
        rel, tsd = reliability(rows)
        o[arm] = dict(rows=rows, y=y, s=s,
                      mean=st.mean(s), n=st.median([r["n"] for r in rows]),
                      r=model.pearson(s, y), rho=model.spearman(s, y),
                      cs=model.pearson([r["creatures"] for r in rows], s),
                      # Task 21's fourth acceptance criterion: does the sim
                      # reward interaction density the way humans do?
                      inter_s=model.pearson([r["interaction"] for r in rows], s),
                      inter_rho=model.spearman([r["interaction"] for r in rows], s),
                      inter_h=model.pearson([r["interaction"] for r in rows], y),
                      rel=rel, tsd=tsd, decks=len(rows))
    for k, lab in (("decks", "decks"), ("n", "decided games/deck"),
                   ("mean", "mean sim win rate %"), ("r", "corr(sim, human)"),
                   ("rho", "rank corr"), ("cs", "corr(creatures, sim)"),
                   ("inter_s", "corr(interaction, sim)"),
                   ("inter_rho", "rank corr(interaction, sim)"),
                   ("inter_h", "corr(interaction, human)*"),
                   ("rel", "reliability (own p)"), ("tsd", "true sd pp")):
        print("%-26s" % lab + "".join("%16.3f" % o[a][k] for a in arms))
    print("\nhuman: mean 24.22%, observed sd 5.56pp, corr(creatures,human) -0.378")
    print("* over the decks that arm has enough games for, so it can differ "
          "slightly between arms")
    return o


if __name__ == "__main__":
    main(sys.argv[1:])
