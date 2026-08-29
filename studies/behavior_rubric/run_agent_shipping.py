#!/usr/bin/env python3
"""Re-run the cEDH pods with the SHIPPING agent config, for the 3-way rubric.

The AGENT row in rubric.py came from runs_agent/, which was produced with
blockiness 1.0 and hold-back on (0.3 / 0.25). The arms ablation found hold-back
null and settled the shipping config as: hold-back OFF and the per-archetype
blockiness deck_plan.py emits. So that row describes a pilot we do not ship,
and the human-vs-stock-vs-agent comparison was reading a stale arm.

This rebuilds plans with no personality overrides (i.e. shipping defaults) and
replays the same 8 pods, 4 seat rotations each. All four seats are plan pilots,
matching how the STOCK runs are all-stock, so the three sources stay comparable
as whole runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "engine"))

SHIM = REPO.parent / "simlab-forge-shim" / "simlab-forge-shim.jar"
# Output dir is an argument so a shim-version validation lands in its own
# directory instead of cache-hitting the previous run's files.
import argparse
FORGE = Path(r"C:\Users\Vatto\forge\forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
_ap = argparse.ArgumentParser()
_ap.add_argument("--out-name", default="runs_agent_shipping")
_ARGS, _ = _ap.parse_known_args()
OUT_DIR = HERE / _ARGS.out_name
PLAN_DIR = OUT_DIR / "plans"


def finished(p: Path) -> bool:
    if not p.exists() or p.stat().st_size < 1000:
        return False
    with p.open(encoding="utf-8", errors="replace") as fh:
        return any('"rec":"result"' in ln or '"rec": "result"' in ln for ln in fh)


def build(pod: str) -> Path:
    from deck_plan import build_plans
    out = PLAN_DIR / f"plans_{pod}.json"
    if out.exists() and out.stat().st_size > 0:
        return out
    decks = sorted((REPO / "studies/human_ceiling/decks" / pod / "dck").glob("*.dck"))
    plans = build_plans([str(d) for d in decks], fetch=True)
    bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}"
           for n, p in plans["decks"].items() if p.get("factsCoverage", 0) < 0.9]
    if bad:
        sys.exit(f"{pod}: degraded plan data: " + "; ".join(bad))
    out.write_text(json.dumps(plans, indent=1), encoding="utf-8")
    return out


def cell(spec):
    pod, rot, plans_path, out = spec
    if finished(out):
        return f"{pod} r{rot} cached"
    decks = sorted((REPO / "studies/human_ceiling/decks" / pod / "dck").glob("*.dck"))
    decks = [str(d.resolve()) for d in decks]
    decks = decks[rot:] + decks[:rot]
    cmd = ["java", "-Xmx3g", "-cp", f"{SHIM}{os.pathsep}{FORGE}",
           "simlab.shim.SimShim", "--decks", *decks,
           "--games", "1", "--timeout", "900", "--max-turns", "90",
           "--plans", str(plans_path),
           "--seat-pilots", ",".join(["plan:SimLabHuman"] * 4),
           "--out", str(out.resolve())]
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                       stdout=subprocess.DEVNULL, stderr=eh, check=False)
    return f"{pod} r{rot} {'ok' if finished(out) else 'FAILED'}"


def main() -> int:
    pods = json.loads((HERE / "pods.json").read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_DIR.mkdir(exist_ok=True)
    specs = []
    for pod in pods:
        plans_path = build(pod)
        for rot in range(4):
            specs.append((pod, rot, plans_path, OUT_DIR / f"{pod}_rot{rot}.jsonl"))
    print(f"{len(pods)} pods x 4 rotations = {len(specs)} games", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(cell, s) for s in specs]
        for f in as_completed(futs):
            done += 1
            print(f"[{done}/{len(specs)}] {f.result()}", flush=True)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
