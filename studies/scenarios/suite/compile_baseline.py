#!/usr/bin/env python3
"""Suite baseline tables from run_scenarios.py output directories.

    py studies/scenarios/suite/compile_baseline.py --suite OUT/stock/suite OUT/plan/suite \\
        --s8 OUT/stock/s8 OUT/plan/s8 --c1 OUT/stock/c1 OUT/plan/c1 \\
        [--timing OUT/timing_stock.json ...] --json studies/scenarios/suite/baseline.json

Reads each directory's report.json (rebuild it first with
run_scenarios.py --report-only --out DIR); several directories of one kind
(one per arm) are merged by arm. Prints the markdown tables that
BASELINE.md carries and writes a compact JSON summary (per scenario and arm,
plus the handful of per-trial fields the tables use). Raw logs stay in the
run directories, outside git.

"Executed" is derived, since the report has no such flag: a trial ran its
line when the line seat made 5 or more activations and triggers of line
pieces in one turn, or took an extra combat on the scenario turn.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRIAL_KEYS = ("file", "loaded", "applied", "has_result", "winner_seat", "turns", "success",
              "kill_on_scenario_turn", "turns_to_kill", "piece_counts", "iterations_max_turn",
              "iterations_scenario_turn", "extra_combats_scenario_turn", "zone_first", "alive",
              "draw", "turnCapped", "timedOut", "error", "exceptions", "wall_s", "ms", "board_diffs")


def executed(t: dict) -> bool:
    return (t.get("iterations_max_turn") or 0) >= 5 or (t.get("extra_combats_scenario_turn") or 0) > 0


RUN_KEYS = ("jar_name", "jar_sha256", "repo_commit", "trials", "seed", "started", "finished", "arms",
            "parallel", "wall_s", "trials_run", "trials_cached")


def load(dirs: list[Path]) -> dict:
    """One kind's reports (one directory per arm, or one with every arm),
    merged: scenarios keep every arm found; runs lists each directory's
    provenance."""
    merged: dict = {}
    for d in dirs or []:
        rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
        merged.setdefault("runs", []).append(dict({k: rep["run"].get(k) for k in RUN_KEYS}, dir=d.as_posix()))
        arms = merged.setdefault("arms", [])
        arms += [a for a in rep["run"]["arms"] if a not in arms]
        for sid, sc in rep["scenarios"].items():
            into = merged.setdefault("scenarios", {}).setdefault(sid, dict(sc, arms={}))
            for arm, a in sc["arms"].items():
                if arm in into["arms"]:
                    raise SystemExit(f"{sid}: arm {arm} appears in two directories")
                into["arms"][arm] = a
    return merged


def arm_row(trials: list[dict], summary: dict) -> dict:
    ran = [t for t in trials if t.get("has_result")]
    ttk = [t["turns_to_kill"] for t in ran if t.get("turns_to_kill") is not None]
    return {
        "trials": len(trials), "finished": len(ran), "loaded": sum(bool(t.get("loaded")) for t in trials),
        "success": sum(bool(t.get("success")) for t in ran), "wilson95": summary.get("success_wilson95"),
        "kill_on_scenario_turn": sum(bool(t.get("kill_on_scenario_turn")) for t in ran),
        "turns_to_kill_median": statistics.median(ttk) if ttk else None,
        "any_win_by_line_seat": sum(1 for t in ran if t.get("turns_to_kill") is not None),
        "executed": sum(executed(t) for t in ran),
        "piece_activity_mean": summary.get("piece_activity_mean"),
        "iterations_max_turn_mean": summary.get("iterations_max_turn_mean"),
        "iterations_max_turn_max": max((t.get("iterations_max_turn") or 0 for t in ran), default=0),
        "extra_combats_scenario_turn_mean": summary.get("extra_combats_scenario_turn_mean"),
        "draws": sum(bool(t.get("draw")) for t in ran), "turn_capped": sum(bool(t.get("turnCapped")) for t in ran),
        "timed_out": sum(bool(t.get("timedOut")) for t in ran), "errors": sum(bool(t.get("error")) for t in ran),
        "exceptions": sum(t.get("exceptions", 0) for t in trials),
        "wall_s_total": round(sum(t.get("wall_s") or 0 for t in trials), 1),
        "game_ms_mean": summary.get("game_ms_mean"),
        "zone_first": dict(Counter(str(t.get("zone_first")) for t in ran)) if any("zone_first" in t for t in ran) else None,
        "piece_totals": dict(sum((Counter({f"{p} {v}": n for v, n in c.items()})
                                  for t in ran for p, c in (t.get("piece_counts") or {}).items()), Counter())),
    }


def f(v) -> str:
    return "–" if v is None else str(v)


def table(rows: list[tuple[str, str, dict]]) -> list[str]:
    out = ["| Scenario | Arm | Loaded | Finished | Success | 95% CI | Kill on scenario turn | Line seat won (any turn) "
           "| Turns to kill (median) | Executed | Iterations, best turn (mean / max) | Extra combats (mean) "
           "| Capped / timed out | Errors / exceptions | Wall s (sum of trials) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sid, arm, r in rows:
        ci = r["wilson95"]
        out.append(
            f"| {sid} | {arm} | {r['loaded']}/{r['trials']} | {r['finished']}/{r['trials']} | "
            f"{r['success']}/{r['finished']} | {'–' if not ci else f'{ci[0]:.2f}-{ci[1]:.2f}'} | "
            f"{r['kill_on_scenario_turn']}/{r['finished']} | {r['any_win_by_line_seat']}/{r['finished']} | "
            f"{f(r['turns_to_kill_median'])} | {r['executed']}/{r['finished']} | "
            f"{f(r['iterations_max_turn_mean'])} / {r['iterations_max_turn_max']} | "
            f"{f(r['extra_combats_scenario_turn_mean'])} | {r['turn_capped']} / {r['timed_out']} | "
            f"{r['errors']} / {r['exceptions']} | {r['wall_s_total']} |")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", type=Path, nargs="*", default=[])
    ap.add_argument("--s8", type=Path, nargs="*", default=[])
    ap.add_argument("--c1", type=Path, nargs="*", default=[])
    ap.add_argument("--timing", type=Path, nargs="*", default=[])
    ap.add_argument("--json", type=Path, default=HERE / "baseline.json")
    args = ap.parse_args()
    reports = {"suite": load(args.suite), "s8": load(args.s8), "c1": load(args.c1)}
    out = {"runs": {k: v["runs"] for k, v in reports.items() if v},
           "timing": {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in args.timing},
           "scenarios": {}, "c1": {}}
    rows = []
    for key in ("suite", "s8"):
        rep = reports[key]
        for sid, s in (rep.get("scenarios") or {}).items():
            out["scenarios"][sid] = {"success": s.get("success"), "turn": s.get("turn"), "arms": {}}
            for arm, a in s["arms"].items():
                r = arm_row(a["trials"], a["summary"])
                out["scenarios"][sid]["arms"][arm] = dict(
                    r, trials_detail=[{k: t.get(k) for k in TRIAL_KEYS} for t in a["trials"]])
                rows.append((sid, arm, r))
    print("\n".join(table(rows)))
    # C1: one trial per real board, paired with the board's own game.
    rep = reports["c1"]
    if rep:
        src = json.loads((HERE / "c1" / "sources.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in src["chosen"]}
        arms = rep["arms"]
        per_arm = {arm: [] for arm in arms}
        for sid, s in rep["scenarios"].items():
            for arm in arms:
                t = s["arms"][arm]["trials"][0]
                per_arm[arm].append(dict({k: t.get(k) for k in TRIAL_KEYS}, id=sid,
                                         in_game=by_id[sid]))
        print()
        print("| C1 | Arm | Loaded | Finished | Won within 8 turns (success) | Won on the scenario turn | "
              "Executed (extra combat on the scenario turn) | In game, same boards: won within 8 turns / same turn / ever | "
              "Agreement with the game (within 8) | Wall s (sum) |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for arm, ts in per_arm.items():
            ran = [t for t in ts if t.get("has_result")]
            ig = [t["in_game"] for t in ts]
            agree = sum(bool(t.get("success")) == t["in_game"]["won_within_horizon"] for t in ran)
            row = {"trials": len(ts), "finished": len(ran), "loaded": sum(bool(t.get("loaded")) for t in ts),
                   "success": sum(bool(t.get("success")) for t in ran),
                   "kill_on_scenario_turn": sum(bool(t.get("kill_on_scenario_turn")) for t in ran),
                   "executed": sum(executed(t) for t in ran),
                   "in_game_within_horizon": sum(g["won_within_horizon"] for g in ig),
                   "in_game_same_turn": sum(g["won_on_attach_turn"] for g in ig),
                   "in_game_ever": sum(g["won"] for g in ig), "agreement": agree,
                   "wall_s_total": round(sum(t.get("wall_s") or 0 for t in ts), 1),
                   "exceptions": sum(t.get("exceptions") or 0 for t in ts),
                   "errors": sum(bool(t.get("error")) for t in ran)}
            out["c1"][arm] = dict(row, boards=ts)
            print(f"| C1 | {arm} | {row['loaded']}/{row['trials']} | {row['finished']}/{row['trials']} | "
                  f"{row['success']}/{row['finished']} | {row['kill_on_scenario_turn']}/{row['finished']} | "
                  f"{row['executed']}/{row['finished']} | {row['in_game_within_horizon']} / {row['in_game_same_turn']} / "
                  f"{row['in_game_ever']} of {len(ig)} | {agree}/{len(ran)} | {row['wall_s_total']} |")
    args.json.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
