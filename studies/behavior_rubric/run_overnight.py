#!/usr/bin/env python3
"""Overnight win-rate ablation: does any configuration of the agent WIN more?

Every study so far measured BEHAVIOUR at n = 32 per arm, which detects nothing
smaller than a huge effect and says nothing about wins. Meanwhile the pooled
head-to-head record across 256 mixed-pod games is 89-102 (46.6%) -- the agent
blocks measurably better than stock and does not win more. This run exists to
find a configuration that does, with enough games to know.

Design:
  - Mixed pods, 2 plan seats + 2 stock seats alternating, so every game is a
    head-to-head observation (null: plan side wins 50% of decided games).
  - 16 pods drawn from the 64 usable precons, 4 seat rotations each, cycled
    until the deadline. ~380 games per arm detects roughly a 7 pp shift.
  - One game per JVM. Costs ~15% throughput vs batching, keeps every existing
    scorer (observer.py, compare.py, winrate.py) working unchanged.
  - Arms are THEME BUNDLES, not single changes. n = 32 single-change arms were
    proven noise-dominated (per-arm p-values did not replicate on identical
    code). If a bundle wins, ablate within it afterwards.

Arms:
  base   shipping defaults. Reference, and doubles the n behind the final
         agent-vs-stock claim.
  lean   strip the UNVALIDATED layers, keep the validated ones (mulligans,
         blocking, tutor steering): stock AI profile instead of the
         counter-eager SimLabHuman, threat veto disabled (counterThreshold 0,
         so the bar is always met), no grudge, no kingmaker re-aim, no
         voluntary chumps. Tests whether the extra layers COST wins, which
         "the agent scored highest when it did least" predicts.
  split  splitAttacks 0.7. The split-attacks dimension has been OFF in every
         shipped plan (deck_plan.py sends 0.0), so it has never been tested.

Usage:
  python studies/behavior_rubric/run_overnight.py [--hours 20] [--workers 12]
  (touch runs_overnight/STOP to stop after the games in flight)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "engine"))

SHIM = REPO.parent / "simlab-forge-shim" / "simlab-forge-shim-0.9.3.jar"
FORGE = Path(r"C:\Users\Vatto\forge\forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
SEED = 20260827  # same shuffle as run_arms; --pods 16 extends the same order

ARMS = {
    "base":  {"overrides": {}, "profile": "SimLabHuman"},
    # counterThreshold 0 makes the counter bar always met, so the threat
    # veto never swallows a counter the stock AI proposed. Without it, lean
    # seats would run stock's proposal rate THROUGH the veto (measured: the
    # veto swallows ~66% of proposals) and counter far less than stock,
    # which is not the layer-stripping the arm exists to test.
    "lean":  {"overrides": {"grudgeWeight": 0.0, "kingmakerRatio": 999.0,
                            "chumpiness": 0.0, "counterThreshold": 0.0},
              "profile": "Default"},
    "split": {"overrides": {"splitAttacks": 0.7}, "profile": "SimLabHuman"},
}


def make_pods(n_pods: int):
    cohort = json.loads((REPO / "studies/precon_predict/cohort.json")
                        .read_text(encoding="utf-8"))
    cohort = [d for d in cohort if Path(d["file"]).is_file()]
    rng = random.Random(SEED)
    shuffled = cohort[:]
    rng.shuffle(shuffled)
    pods = [shuffled[i:i + 4] for i in range(0, len(shuffled) - 3, 4)]
    return pods[:n_pods]


def build_arm_plans(arm: str, pods, out_dir: Path) -> Path:
    from deck_plan import build_plans
    decks = [d["file"] for pod in pods for d in pod]
    out = out_dir / f"plans_{arm}_{len(decks)}.json"
    if out.exists() and out.stat().st_size > 0:
        return out
    plans = build_plans(decks, fetch=True)
    bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}"
           for n, p in plans["decks"].items()
           if p.get("factsCoverage", 0) < 0.9]
    if bad:
        sys.exit(f"arm {arm}: degraded plan data: " + "; ".join(bad[:5]))
    ov = ARMS[arm]["overrides"]
    if ov:
        for p in plans["decks"].values():
            p.setdefault("personality", {}).update(ov)
    out.write_text(json.dumps(plans, indent=1), encoding="utf-8")
    return out


def finished(out: Path) -> bool:
    if not out.exists() or out.stat().st_size < 1000:
        return False
    with out.open(encoding="utf-8", errors="replace") as fh:
        return any('"rec":"result"' in ln or '"rec": "result"' in ln
                   for ln in fh)


def cell(spec):
    arm, cyc, pod_i, rot, pod, plans_path, out = spec
    # Queued games honour STOP too; only games already in a JVM run to the end.
    if (out.parent.parent / "STOP").exists():
        return f"{arm}/c{cyc}p{pod_i}r{rot} skipped(stop)"
    if finished(out):
        return f"{arm}/c{cyc}p{pod_i}r{rot} cached"
    decks = [d["file"] for d in pod]
    decks = decks[rot:] + decks[:rot]
    prof = ARMS[arm]["profile"]
    seats = ",".join([f"plan:{prof}", "stock:Default"] * 2)
    cmd = ["java", "-Xmx3g", "-cp", f"{SHIM}{os.pathsep}{FORGE}",
           "simlab.shim.SimShim", "--decks", *decks,
           "--games", "1", "--timeout", "900", "--max-turns", "90",
           "--plans", str(plans_path), "--seat-pilots", seats,
           "--out", str(out.resolve())]
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                       stdout=subprocess.DEVNULL, stderr=eh, check=False)
    return f"{arm}/c{cyc}p{pod_i}r{rot} {'ok' if finished(out) else 'FAILED'}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=20.0)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--pods", type=int, default=16)
    args = ap.parse_args()

    if not SHIM.is_file():
        sys.exit(f"shim jar not found: {SHIM}")
    deadline = time.time() + args.hours * 3600
    pods = make_pods(args.pods)
    root = HERE / "runs_overnight"
    root.mkdir(parents=True, exist_ok=True)
    plan_dir = root / "plans"
    plan_dir.mkdir(exist_ok=True)
    stop = root / "STOP"

    plans = {arm: build_arm_plans(arm, pods, plan_dir) for arm in ARMS}
    for arm in ARMS:
        (root / arm).mkdir(exist_ok=True)

    total_done = 0
    for cyc in range(999):
        if time.time() > deadline or stop.exists():
            break
        # Interleave arms within the cycle so a stop leaves them near-equal.
        specs = []
        for pod_i, pod in enumerate(pods):
            for rot in range(4):
                for arm in ARMS:
                    specs.append((arm, cyc, pod_i, rot, pod, plans[arm],
                                  root / arm / f"c{cyc}_p{pod_i}_r{rot}.jsonl"))
        print(f"cycle {cyc}: {len(specs)} games", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(cell, s) for s in specs]
            for f in as_completed(futs):
                total_done += 1
                print(f"[{total_done}] {f.result()}", flush=True)
                if stop.exists():
                    # let in-flight games finish; queue drains via cache check
                    pass
        if stop.exists() or time.time() > deadline:
            break
    print(f"done after {total_done} games. Score with winrate.py / observer.py "
          f"/ compare.py on {root}/<arm>", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
