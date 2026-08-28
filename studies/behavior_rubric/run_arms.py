#!/usr/bin/env python3
"""One-change-per-arm ablation, scored by the shim's neutral combat observer.

Design notes that matter:

MIXED PODS. Every pod seats two plan pilots and two stock pilots, alternating.
Both pilots therefore play the same board, the same shuffle and the same
opponents in the same game, so the comparison is paired within a game instead
of across separate all-plan and all-stock runs. Seat rotation means each deck
plays plan in two rotations and stock in the other two, so no deck is
permanently assigned to either pilot.

PRECONS, NOT cEDH. The cEDH pods that carry human traces barely block at all
(measured: 11 available blockers across 30 block records in one game), because
those decks run almost no creatures. The blocking axis has no discriminating
power there. Precons have real creature boards, so this is where blocking and
attacking policy can actually be measured. The cEDH pods stay the right place
for the interaction axis.

ONE CHANGE PER ARM. The earlier arms bundled five and two changes, so a null
result could not be attributed. Each arm below differs from `base` in exactly
one thing.

TURN CAP, NOT WALL CLOCK. The wall clock censors on how busy the machine is,
which is how an earlier agent arm lost 34.1% of its games to stock's 9.7% and
produced an uninterpretable comparison. --max-turns censors both pilots on the
same in-game quantity, and here both pilots are in the same game anyway.

Usage:
  python studies/behavior_rubric/run_arms.py [--pods N] [--arms base,hold]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "engine"))

SHIM = REPO.parent / "simlab-forge-shim" / "simlab-forge-shim.jar"
FORGE = Path(r"C:\Users\Vatto\forge\forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
SEED = 20260827

# Each arm differs from base in exactly one thing.
ARMS = {
    # Shipped defaults: hold-back off, blockiness 0.24, greed 1.0.
    "base": {"overrides": {}, "synergy": False},
    # The retuned hold-back. At 1.0/0.5 it fired 329 times per game and kept
    # half the board home every combat; this is the tested-plausible range.
    "hold": {"overrides": {"holdBackPerThreat": 0.3, "holdBackRatio": 0.25},
             "synergy": False},
    # Block more often. Rate only -- block QUALITY is already on in base.
    "blocky": {"overrides": {"blockiness": 0.6}, "synergy": False},
    # Plan-data change, not a personality change: 2-card engines derived from
    # archetype tags when Commander Spellbook returns nothing.
    "synergy": {"overrides": {}, "synergy": True},
}


def make_pods(n_pods: int) -> list[list[dict]]:
    cohort = json.loads((REPO / "studies/precon_predict/cohort.json")
                        .read_text(encoding="utf-8"))
    cohort = [d for d in cohort if Path(d["file"]).is_file()]
    rng = random.Random(SEED)
    shuffled = cohort[:]
    rng.shuffle(shuffled)
    pods = [shuffled[i:i + 4] for i in range(0, len(shuffled) - 3, 4)]
    return pods[:n_pods]


def build_arm_plans(arm: str, pods: list[list[dict]], out_dir: Path) -> Path:
    """One plans file per arm, covering every deck in every pod."""
    from deck_plan import build_plans

    decks = [d["file"] for pod in pods for d in pod]
    # Pod count is in the name: a smoke run over one pod must not leave a
    # 4-deck plans file that a later full run silently reuses.
    out = out_dir / f"plans_{arm}_{len(decks)}.json"
    if out.exists() and out.stat().st_size > 0:
        return out
    plans = build_plans(decks, fetch=True, synergy=ARMS[arm]["synergy"])
    bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}"
           for n, p in plans["decks"].items()
           if p.get("factsCoverage", 0) < 0.9]
    if bad:
        sys.exit(f"arm {arm}: degraded plan data, refusing to run: "
                 + "; ".join(bad[:5]))
    ov = ARMS[arm]["overrides"]
    if ov:
        for p in plans["decks"].values():
            p.setdefault("personality", {}).update(ov)
    out.write_text(json.dumps(plans, indent=1), encoding="utf-8")
    return out


def finished(out: Path) -> bool:
    """A file is only done when it carries a result record.

    Size alone is not enough: a shim process that dies after writing meta
    leaves a ~795 byte file, and treating that as a cache hit would bake the
    failure into every later run of the study.
    """
    if not out.exists() or out.stat().st_size < 1000:
        return False
    # The shim serialises without spaces ("rec":"result"). Both spellings are
    # accepted because matching only the pretty-printed one silently made
    # every finished game look unfinished, so nothing ever cached.
    try:
        with out.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"rec":"result"' in line or '"rec": "result"' in line:
                    return True
    except OSError:
        return False
    return False


def cell(spec):
    arm, pod_i, rot, pod, plans_path, out = spec
    if finished(out):
        return f"{arm}/{pod_i}r{rot} cached"
    decks = [d["file"] for d in pod]
    decks = decks[rot:] + decks[:rot]
    # Alternating pilots: the paired within-game comparison.
    seats = ",".join(["plan:SimLabHuman", "stock:Default"] * 2)
    # 900 s, not 2400. Measured: a normal 63-turn precon game finishes in
    # 150-400 s, but a token-copy board can wedge Forge inside a SINGLE stack
    # resolution -- each token entering play forces a full static-ability
    # recheck across all permanents, so it is quadratic and the turn cap can
    # never fire because the turn never ends. Stack-sampled one such JVM at
    # 1220 s of CPU sitting in GameAction.checkStaticAbilities under
    # TokenEffectBase.makeTokenTable, with no shim frame involved. The wall
    # clock is the only backstop for that shape, and a long one just burns a
    # worker slot. Censoring stays honest here because both pilots sit in
    # every pod, so a killed game drops plan and stock data symmetrically.
    cmd = ["java", "-Xmx3g", "-cp", f"{SHIM}{os.pathsep}{FORGE}",
           "simlab.shim.SimShim", "--decks", *decks,
           "--games", "1", "--timeout", "900", "--max-turns", "90",
           "--plans", str(plans_path), "--seat-pilots", seats,
           "--out", str(out.resolve())]
    # Keep stderr. Discarding it is how a 50% silent failure rate went
    # unnoticed on the first pod of this study.
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                       stdout=subprocess.DEVNULL, stderr=eh, check=False)
    ok = finished(out)
    return f"{arm}/{pod_i}r{rot} {'ok' if ok else 'FAILED'}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pods", type=int, default=8)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            sys.exit(f"unknown arm {a}; known: {list(ARMS)}")
    if not SHIM.is_file():
        sys.exit(f"shim jar not found: {SHIM}")

    pods = make_pods(args.pods)
    root = HERE / "runs_arms"
    root.mkdir(parents=True, exist_ok=True)
    plan_dir = root / "plans"
    plan_dir.mkdir(exist_ok=True)

    specs = []
    for arm in arms:
        plans_path = build_arm_plans(arm, pods, plan_dir)
        out_dir = root / arm
        out_dir.mkdir(exist_ok=True)
        for i, pod in enumerate(pods):
            for rot in range(4):
                specs.append((arm, i, rot, pod, plans_path,
                              out_dir / f"pod{i}_rot{rot}.jsonl"))

    print(f"{len(arms)} arms x {len(pods)} pods x 4 rotations = "
          f"{len(specs)} games, {args.workers} at a time", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(cell, s) for s in specs]
        for f in as_completed(futs):
            done += 1
            print(f"[{done}/{len(specs)}] {f.result()}", flush=True)
    print("done. score with: python studies/behavior_rubric/observer.py "
          f"{root}/<arm>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
