#!/usr/bin/env python3
"""E2 post hoc diagnostic (NOT pre-registered): why do seeded games diverge?

E2 passed (every pair identical up to the first decision), but 3 of 10
game-0 pairs later parted ways within 16 turns. Every random draw in
forge.ai and forge.game goes through MyRandom, which --seed-forge replaces,
so the suspect is iteration order over hash collections keyed by
identity-hashed objects (enum constants such as ManaCostShard, whose hash
codes differ from one JVM to the next). This reruns the three diverging
seeds with every identity hash code pinned to 1
(-XX:+UnlockExperimentalVMOptions -XX:hashCode=2) and, as the control, in
more ordinary JVMs:

    py studies/e2_seeding/diag_hashcode.py run
    py studies/e2_seeding/diag_hashcode.py read

Prediction if identity-hash order is the cause: the pinned replicates agree
with each other through turn 16 on every seed, while ordinary replicates
keep diverging. Output under $E2_OUT/diag, never into git.

Review note (2026-09-28): the premise above is false. Forge also calls
java.util.Collections.shuffle(List), whose one-argument form draws from a
clock-seeded static Random that --seed-forge does not replace (CharmAi mode
order, AiCostDecision gift recipient, DiscardAi; see review_e2.py scan).
That source, not identity hashes, is what the play divergences here follow;
the hash pin did remove the tap-order-only swaps. RESULTS.md has the reading.
"""
from __future__ import annotations

import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_e2 as E  # noqa: E402
import read_e2 as R  # noqa: E402

SEEDS_K = [0, 3, 6]                       # the game-0 pairs that diverged
ARMS = {"N": ([], ["c", "d"]),            # ordinary JVM, two more replicates
        "H": (["-XX:+UnlockExperimentalVMOptions", "-XX:hashCode=2"], ["a", "b", "c"])}
DIAG = E.OUT / "diag"


def out_path(arm, k, rep):
    return DIAG / arm / f"seed{k}_{rep}.jsonl"


def command(arm, k, rep):
    cmd = E.command("E2", k, rep)
    cmd[cmd.index("--games") + 1] = "1"
    cmd[cmd.index("--out") + 1] = str(out_path(arm, k, rep))
    return cmd[:1] + ARMS[arm][0] + cmd[1:]


def cell(spec):
    arm, k, rep = spec
    out = out_path(arm, k, rep)
    if 0 in E.results_in(out):
        return f"{arm} seed{k} {rep} cached"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = command(arm, k, rep)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        rc = subprocess.run(cmd, cwd=str(E.FORGE.parent), stdout=subprocess.DEVNULL, stderr=eh).returncode
    out.with_suffix(".cell.json").write_text(json.dumps(
        {"arm": arm, "k": k, "seed": E.seed(k), "rep": rep, "started": started, "rc": rc, "cmd": cmd},
        indent=1), encoding="utf-8")
    return f"{arm} seed{k} {rep} rc={rc}"


def run():
    E.assert_inputs()
    # Replicate-major order, so a seed's replicates mostly run at different times.
    specs = []
    for i in range(max(len(reps) for _, reps in ARMS.values())):
        for arm, (_, reps) in ARMS.items():
            if i < len(reps):
                specs += [(arm, k, reps[i]) for k in SEEDS_K]
    with ThreadPoolExecutor(max_workers=E.MAX_JVMS) as ex:
        for r in ex.map(cell, specs):
            print(r, flush=True)


def read():
    out = {}
    for k in SEEDS_K:
        runs = {("E2", r): R.load(E.out_path("E2", k, r)) for r in ("a", "b")}
        for arm, (_, reps) in ARMS.items():
            for r in reps:
                runs[(arm, r)] = R.load(out_path(arm, k, r))
        print(f"seed k={k} ({E.seed(k)}): first divergence turn per pair (none = identical through turn {E.MAX_TURNS})")
        rows = []
        for (x, y) in combinations(sorted(runs), 2):
            (mx, gx), (my, gy) = runs[x], runs[y]
            if 0 not in gx or 0 not in gy:
                continue
            if (x[0] == "H") != (y[0] == "H"):
                continue                  # pinned vs ordinary JVMs play different games by design
            row = R.compare_pair(gx[0], gy[0], (mx or {}).get("players"), E.MAX_TURNS)
            t = row.get("first_divergence_turn")
            where = {s: d and f"#{d['index']}@t{d['turn_a']}" for s, d in row["divergence"].items() if d}
            print(f"  {x[0]}/{x[1]} vs {y[0]}/{y[1]}: opening identical={row['identical']} "
                  f"first divergence={'none' if t is None else t} {where}")
            rows.append({"a": x, "b": y, "identical": row["identical"], "first_divergence_turn": t,
                         "where": where})
        out[k] = rows
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(out, indent=1, default=str),
                                                                encoding="utf-8")


if __name__ == "__main__":
    {"run": run, "read": read}[sys.argv[1]]()
