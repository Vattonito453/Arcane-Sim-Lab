#!/usr/bin/env python3
"""Pilot: does the plan agent beat stock Forge on decks where it can operate?

Every prior head-to-head measured the agent on Forge precons, where
deck_plan finds ZERO combo lines. With no lines, PlanPlayerController's
lineOfSight() returns null on its first branch, which switches off combo
pursuit, line-piece cast priority, tutor casting, greed and combo-mode tutor
steering together. What is left running is blocking, attack splitting, the
counterspell veto and kingmaker re-aim -- all defensive. That is the agent
those studies found "no better than stock Forge", and an agent with only
defensive features is expected to survive longer and win the same, which is
exactly the one signal that reproduced across 1536 games.

The cEDH pods in studies/human_ceiling warm to 3-29 lines per deck, so the
machinery is live there. This pilot asks the product question directly:

    ONE plan seat vs THREE stock Forge seats, in the same pod.

The plan seat rotates through all four positions so Forge's seat bias
cancels. The null is 25%: if the agent is not better, it wins its share.

This is a PILOT. At the default 64 games the standard error on a win share
is about 5.4 pp, so it can only see a large effect. It exists to decide
whether to spend 8 hours on a powered run, not to settle anything.

Usage:
  python3 studies/agent_viability/run_pilot.py --games-per-cell 8 --workers 8
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ENGINE = REPO / "engine"

# Pods that warm to 4/4 combo-live decks. Two archetypes: a treasure/toolbox
# pod and an elves/big-mana pod, both with human traces in studies/human_ceiling.
PODS = ["n7WpsqsZtdQ", "2iA_Jt0d6sM"]

# Personality dials are the agent's own handicaps: they exist to make it play
# like a person, which means playing worse than it could. Measuring "can our
# agent beat stock Forge" with them on measures the handicap, not the agent.
#
#   greed 0.5        holds the piece that WINS THE GAME against open mana,
#                    re-rolled every turn (14 hold decisions in 8 games)
#   triggerMiss 0.03 declines a beneficial optional trigger 3% of the time
#   splitAttacks 0.7 spreads damage across opponents instead of killing one
#   politics 0.5     raises the counterspell bar while others hold mana
#
# ARMS are the same agent with those dials at their play-to-win settings.
ARMS = {
    # What ships today.
    "default": {},
    # Every self-imposed handicap off. This is the agent's ceiling.
    "winmax": {"greed": 1.0, "triggerMiss": 0.0, "splitAttacks": 0.0,
               "politics": 0.0},
    # Isolation arms: which handicap costs the most?
    "jam": {"greed": 1.0},
    "notriggermiss": {"triggerMiss": 0.0},
    # Win-max MINUS combo pursuit. Keeps plan weights, mulligan policy, threat
    # index and Stage 2 tutor targeting; drops the `lines` that gate
    # lineOfSight(), so the agent never diverts into assembling a combo.
    # The question this answers: is pursuing a line the agent cannot CONVERT
    # actively costing us games? If dropping it scores higher than win-max,
    # pursuit is a handicap until conversion exists, and conversion is the
    # thing to build. If it scores lower, pursuit is already paying and the
    # gap is elsewhere.
    "nocombo": {"greed": 1.0, "triggerMiss": 0.0, "splitAttacks": 0.0,
                "politics": 0.0, "_dropLines": True},
}


def forge_jar() -> str:
    hits = sorted(Path(os.path.expanduser("~/forge")).glob(
        "forge-gui-desktop-*-jar-with-dependencies.jar"))
    if not hits:
        sys.exit("Forge jar not found in ~/forge")
    return str(hits[-1])


def shim_jar(explicit: str | None) -> str:
    if explicit:
        return explicit
    p = Path(os.path.expanduser("~/simlab-forge-shim/simlab-forge-shim.jar"))
    if not p.is_file():
        sys.exit(f"shim jar not found: {p}")
    return str(p)


def pod_decks(pod: str) -> list[Path]:
    d = REPO / "studies" / "human_ceiling" / "decks" / pod / "dck"
    decks = sorted(d.glob("*.dck"))
    if len(decks) != 4:
        sys.exit(f"pod {pod} has {len(decks)} decks, need 4")
    return decks


def build_plans(decks: list[Path], out: Path, overrides: dict | None = None) -> dict:
    """Cache-only, and REFUSE to run on a degraded plan.

    This is the whole point of the pilot: a cold cache silently produces the
    same crippled agent the earlier studies measured. Warm it first with
    deck_plan.py --fetch.
    """
    sys.path.insert(0, str(ENGINE))
    from deck_plan import build_plans as bp
    plans = bp([str(p) for p in decks])
    bad = []
    for name, plan in plans["decks"].items():
        cov = plan.get("factsCoverage", 0)
        if cov < 0.9 or not plan.get("lines"):
            bad.append(f"{name} cov={cov:.2f} lines={len(plan.get('lines', []))}")
    if bad:
        sys.exit("plan data is degraded; the agent under test would be the "
                 "crippled one:\n  " + "\n  ".join(bad)
                 + "\nWarm with: python engine/deck_plan.py <decks> --fetch")
    # Applied to every deck: only the plan seat reads its plan, and which deck
    # sits there changes with the rotation, so the arm has to travel with all
    # of them. Stock seats ignore plans entirely.
    if overrides:
        dials = {k: v for k, v in overrides.items() if not k.startswith("_")}
        for plan in plans["decks"].values():
            plan.setdefault("personality", {}).update(dials)
            if overrides.get("_dropLines"):
                plan["lines"] = []
    out.write_text(json.dumps(plans, indent=2), encoding="utf-8")
    return plans


def run_cell(spec) -> dict:
    pod, rot, decks, plans_path, out_path, games, clock, jars, heap = spec
    if out_path.exists() and out_path.stat().st_size > 0:
        return parse_cell(pod, rot, out_path)
    # Seat `rot` is the plan agent; every other seat is stock Forge.
    pilots = ",".join("plan:SimLabHuman" if s == rot else "stock:Default"
                      for s in range(4))
    cmd = ["java", f"-Xmx{heap}", "-cp", f"{jars[0]}{os.pathsep}{jars[1]}",
           "simlab.shim.SimShim", "--decks", *[str(d) for d in decks],
           "--games", str(games), "--timeout", str(clock),
           "--plans", str(plans_path), "--seat-pilots", pilots,
           "--out", str(out_path)]
    subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=False)
    return parse_cell(pod, rot, out_path)


def parse_cell(pod: str, rot: int, out_path: Path) -> dict:
    """Read the shim's own records. Verify the arm actually landed where the
    design says it did -- a silent arm mismatch makes every number worthless
    (the precon pilot lost half its agent arm to exactly that)."""
    wins = {}
    games = decided = 0
    agents = None
    for line in out_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("rec") == "meta":
            agents = r.get("agents")
        elif r.get("rec") == "result":
            games += 1
            w = r.get("winner")
            if r.get("draw") or not w:
                continue
            decided += 1
            seat = w.split(")-")[0].replace("Ai(", "")
            wins[seat] = wins.get(seat, 0) + 1
    ok = agents is not None and len(agents) == 4 and \
        agents[rot] == "plan" and all(a == "stock" for i, a in enumerate(agents) if i != rot)
    return {"pod": pod, "rotation": rot, "games": games, "decided": decided,
            "plan_seat": rot + 1, "plan_wins": wins.get(str(rot + 1), 0),
            "wins_by_seat": wins, "arm_ok": ok, "agents": agents}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games-per-cell", type=int, default=8)
    ap.add_argument("--clock", type=int, default=900)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--heap", default="3g")
    ap.add_argument("--shim-jar", default=None)
    ap.add_argument("--arm", default="default", choices=sorted(ARMS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    overrides = ARMS[args.arm]
    out_dir = Path(args.out) if args.out else HERE / f"runs_{args.arm}"
    out_dir.mkdir(parents=True, exist_ok=True)
    jars = (shim_jar(args.shim_jar), forge_jar())

    specs = []
    for pod in PODS:
        decks = pod_decks(pod)
        plans_path = out_dir / f"plans_{pod}.json"
        build_plans(decks, plans_path, overrides)
        for rot in range(4):
            specs.append((pod, rot, decks, plans_path,
                          out_dir / f"cell_{pod}_rot{rot}.jsonl",
                          args.games_per_cell, args.clock, jars, args.heap))

    total = len(specs) * args.games_per_cell
    print(f"arm      {args.arm}: {overrides or 'ships-today dials'}")
    print(f"design   1 plan seat vs 3 stock seats, plan seat rotated 0-3")
    print(f"pods     {', '.join(PODS)} (all decks combo-live and warm)")
    print(f"cells    {len(specs)} x {args.games_per_cell} games = {total} games, "
          f"clock {args.clock}s, {args.workers} workers")
    print(f"null     plan seat wins 25% if the agent is no better than stock\n")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(run_cell, specs))

    (out_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    bad = [r for r in rows if not r["arm_ok"]]
    decided = sum(r["decided"] for r in rows)
    plan_wins = sum(r["plan_wins"] for r in rows)
    played = sum(r["games"] for r in rows)
    for r in rows:
        print(f"  {r['pod']} rot{r['rotation']} seat{r['plan_seat']}: "
              f"plan {r['plan_wins']}/{r['decided']} decided "
              f"({r['games']} played){'  ARM MISMATCH' if not r['arm_ok'] else ''}")
    print(f"\nplayed {played}, decided {decided}, censored {played - decided}")
    if bad:
        print(f"REFUSING to report: {len(bad)} cells had the wrong arm placement")
        return 1
    if decided:
        share = plan_wins / decided
        se = (share * (1 - share) / decided) ** 0.5
        print(f"plan-seat win share {plan_wins}/{decided} = {share:.1%} "
              f"+/- {se * 100:.1f} pp (1 SE), null 25%")
        print(f"95% CI approx [{(share - 1.96 * se):.1%}, {(share + 1.96 * se):.1%}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
