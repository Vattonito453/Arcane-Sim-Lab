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
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Per-trial fields kept in baseline.json (piece counts and targets are
# summed per arm; board differences are counted, and listed in the run's
# report.md, which stays with the raw logs).
TRIAL_KEYS = ("file", "loaded", "line_loaded", "applied", "has_result", "winner_seat", "turns", "success",
              "kill_on_scenario_turn", "turns_to_kill", "iterations_max_turn",
              "iterations_scenario_turn", "extra_combats_scenario_turn", "zone_first", "alive",
              "draw", "turnCapped", "timedOut", "error", "exceptions", "wall_s", "ms")


def detail(t: dict) -> dict:
    return dict({k: t.get(k) for k in TRIAL_KEYS}, board_diffs=len(t.get("board_diffs") or []))


def table_of(rows: list[dict]) -> dict:
    """Per-trial dicts as one header and one row per trial (a third the size)."""
    cols = list(rows[0]) if rows else []
    return {"columns": cols, "rows": [[r.get(c) for c in cols] for r in rows]}


def dumps(o, pad: str = "") -> str:
    """JSON with one line per table row, so baseline.json diffs by trial."""
    if isinstance(o, dict) and set(o) == {"columns", "rows"}:
        rows = ",\n".join(pad + "  " + json.dumps(r, ensure_ascii=False) for r in o["rows"])
        return ("{\n" + pad + ' "columns": ' + json.dumps(o["columns"]) + ",\n" + pad + ' "rows": [\n'
                + rows + "\n" + pad + " ]}")
    if isinstance(o, dict) and any(isinstance(v, (dict, list)) and v for v in o.values()):
        body = ",\n".join(pad + " " + json.dumps(k) + ": " + dumps(v, pad + " ") for k, v in o.items())
        return "{\n" + body + "\n" + pad + "}"
    if isinstance(o, list) and any(isinstance(v, dict) for v in o):
        return "[\n" + ",\n".join(pad + " " + dumps(v, pad + " ") for v in o) + "\n" + pad + "]"
    return json.dumps(o, ensure_ascii=False)


def executed(t: dict) -> bool:
    return (t.get("iterations_max_turn") or 0) >= 5 or (t.get("extra_combats_scenario_turn") or 0) > 0


RUN_KEYS = ("jar_name", "jar_sha256", "repo_commit", "trials", "seed", "started", "finished", "arms",
            "parallel", "wall_s", "trials_run", "trials_cached", "invocations")


def load(dirs: list[Path]) -> dict:
    """One kind's reports (one directory per arm, or one with every arm),
    merged: scenarios keep every arm found; runs lists each directory's
    provenance."""
    merged: dict = {}
    for d in dirs or []:
        rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
        merged.setdefault("runs", []).append(dict({k: rep["run"].get(k) for k in RUN_KEYS}, dir="/".join(d.parts[-2:])))   # arm/kind; the raw tree stays outside git
        arms = merged.setdefault("arms", [])
        arms += [a for a in rep["run"]["arms"] if a not in arms]
        for sid, sc in rep["scenarios"].items():
            into = merged.setdefault("scenarios", {}).setdefault(sid, dict(sc, arms={}))
            for arm, a in sc["arms"].items():
                if arm in into["arms"]:
                    raise SystemExit(f"{sid}: arm {arm} appears in two directories")
                # A baseline never counts a game that played another state
                # than the one in its run directory (run_scenarios.py re-runs
                # such a trial; a report built before the re-run still lists it).
                stale = [t["file"] for t in a["trials"] if t.get("state_matches") is False]
                if stale:
                    raise SystemExit(f"{d}: {sid} {arm} has stale trials {stale[:5]}; re-run them first")
                into["arms"][arm] = a
    return merged


def arm_row(trials: list[dict], summary: dict) -> dict:
    ran = [t for t in trials if t.get("has_result")]
    ttk = [t["turns_to_kill"] for t in ran if t.get("turns_to_kill") is not None]
    return {
        "trials": len(trials), "finished": len(ran), "loaded": sum(bool(t.get("loaded")) for t in trials),
        "line_loaded": sum(bool(t.get("line_loaded")) for t in trials),
        "success": sum(bool(t.get("success")) for t in ran), "wilson95": summary.get("success_wilson95"),
        "scored": sum(t.get("success") is not None for t in ran),
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
        "piece_targets": {p: dict(c.most_common()) for p, c in sorted(targets(ran).items())},
    }


def targets(ran: list[dict]) -> dict[str, Counter]:
    """Every line piece's targets summed over the arm's finished trials."""
    tot: dict[str, Counter] = {}
    for t in ran:
        for p, c in (t.get("piece_targets") or {}).items():
            tot.setdefault(p, Counter()).update(c)
    return tot


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def f(v) -> str:
    return "–" if v is None else str(v)


def table(rows: list[tuple[str, str, dict]]) -> list[str]:
    out = ["| Scenario | Arm | Loaded (exact / line pieces) | Finished | Success (of scored) | 95% CI | Kill on scenario turn | Line seat won (any turn) "
           "| Turns to kill (median) | Executed | Iterations, best turn (mean / max) | Extra combats (mean) "
           "| Capped / timed out | Errors / exceptions | Wall s (sum of trials) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sid, arm, r in rows:
        ci = r["wilson95"]
        out.append(
            f"| {sid} | {arm} | {r['loaded']} / {r['line_loaded']} of {r['trials']} | {r['finished']}/{r['trials']} | "
            f"{r['success']}/{r['scored']} | {'–' if not ci else f'{ci[0]:.2f}-{ci[1]:.2f}'} | "
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
    ap.add_argument("--c1-supplement", type=Path, nargs="*", default=[],
                    help="C1 runs with several trials per board (every trial counted, per board)")
    ap.add_argument("--timing", type=Path, nargs="*", default=[])
    ap.add_argument("--json", type=Path, default=HERE / "baseline.json")
    ap.add_argument("--md", type=Path, help="also write the tables to this file (UTF-8)")
    args = ap.parse_args()
    reports = {"suite": load(args.suite), "s8": load(args.s8), "c1": load(args.c1)}
    out = {"runs": {k: v["runs"] for k, v in reports.items() if v},
           "timing": {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in args.timing},
           "scenarios": {}, "c1": {}}
    md: list[str] = []
    rows = []
    for key in ("suite", "s8"):
        rep = reports[key]
        for sid, s in (rep.get("scenarios") or {}).items():
            out["scenarios"][sid] = {"success": s.get("success"), "turn": s.get("turn"), "arms": {}}
            for arm, a in s["arms"].items():
                r = arm_row(a["trials"], a["summary"])
                out["scenarios"][sid]["arms"][arm] = dict(
                    r, trials_detail=table_of([detail(t) for t in a["trials"]]))
                rows.append((sid, arm, r))
    md += table(rows)
    # What the line pieces targeted (the choice S1 and S2 test), and the
    # tutor's pick for the zone scenarios (S8, S9).
    md += ["", "| Scenario | Arm | Piece | Targets, summed over trials (top 6) |", "|---|---|---|---|"]
    for sid, arm, r in rows:
        for piece, c in r["piece_targets"].items():
            top = list(c.items())[:6]
            md.append(f"| {sid} | {arm} | {piece} | " + "; ".join(f"{k} x{n}" for k, n in top) + " |")
    md += ["", "| Scenario | Arm | First move per trial (the pick) | Named cards (strict) |", "|---|---|---|---|"]
    for sid, arm, r in rows:
        if r["zone_first"] is None:
            continue
        named = set((out["scenarios"][sid]["success"] or {}).get("cards", []))
        strict = sum(n for k, n in r["zone_first"].items() if k in named)
        picks = "; ".join(f"{k} x{n}" for k, n in sorted(r["zone_first"].items(), key=lambda kv: -kv[1]))
        md.append(f"| {sid} | {arm} | {picks} | {strict}/{r['finished']} |")
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
                per_arm[arm].append(dict(detail(t), id=sid, in_game=by_id[sid]))
        md += ["", "| C1 | Arm | Loaded (exact / line pieces) | Finished | Won within 8 turns (success) | Won on the scenario turn | "
                   "Executed | In game, same boards: won within 8 turns / same turn / ever | "
                   "Agreement with the game (within 8) | Errors / exceptions | Wall s (sum) |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm, ts in per_arm.items():
            ran = [t for t in ts if t.get("has_result")]
            ig = [t["in_game"] for t in ts]
            agree = sum(bool(t.get("success")) == t["in_game"]["won_within_horizon"] for t in ran)
            row = {"trials": len(ts), "finished": len(ran), "loaded": sum(bool(t.get("loaded")) for t in ts),
                   "line_loaded": sum(bool(t.get("line_loaded")) for t in ts),
                   "applied": sum(bool(t.get("applied")) for t in ts),
                   "success": sum(bool(t.get("success")) for t in ran),
                   "kill_on_scenario_turn": sum(bool(t.get("kill_on_scenario_turn")) for t in ran),
                   "executed": sum(executed(t) for t in ran),
                   "in_game_within_horizon": sum(g["won_within_horizon"] for g in ig),
                   "in_game_same_turn": sum(g["won_on_attach_turn"] for g in ig),
                   "in_game_ever": sum(g["won"] for g in ig), "agreement": agree,
                   "wall_s_total": round(sum(t.get("wall_s") or 0 for t in ts), 1),
                   "exceptions": sum(t.get("exceptions") or 0 for t in ts),
                   "errors": sum(bool(t.get("error")) for t in ran)}
            out["c1"][arm] = dict(row, boards=table_of(
                [dict({k: v for k, v in t.items() if k != "in_game"},
                      in_game_won_within_8=t["in_game"]["won_within_horizon"],
                      in_game_won_same_turn=t["in_game"]["won_on_attach_turn"],
                      in_game_end_turn=t["in_game"]["end_turn"]) for t in ts]))
            md.append(f"| C1 | {arm} | {row['loaded']} / {row['line_loaded']} of {row['trials']} | "
                      f"{row['finished']}/{row['trials']} | "
                      f"{row['success']}/{row['finished']} | {row['kill_on_scenario_turn']}/{row['finished']} | "
                      f"{row['executed']}/{row['finished']} | {row['in_game_within_horizon']} / "
                      f"{row['in_game_same_turn']} / {row['in_game_ever']} of {len(ig)} | {agree}/{len(ran)} | "
                      f"{row['errors']} / {row['exceptions']} | {row['wall_s_total']} |")
        # Per board: the game's own outcome beside each arm's.
        md += ["", "| Board | Turn | In game: won within 8 / same turn (end turn) | "
               + " | ".join(f"{a}: success / turns to kill / extra combats" for a in arms) + " |",
               "|---|---|---|" + "---|" * len(arms)]
        for sid in rep["scenarios"]:
            g = by_id[sid]
            cells = []
            for arm in arms:
                t = next(x for x in per_arm[arm] if x["id"] == sid)
                cells.append(f"{'yes' if t.get('success') else 'no'} / {f(t.get('turns_to_kill'))} / "
                             f"{f(t.get('extra_combats_scenario_turn'))}")
            md.append(f"| {sid} | {g['turn']} | {'yes' if g['won_within_horizon'] else 'no'} / "
                      f"{'yes' if g['won_on_attach_turn'] else 'no'} ({g['end_turn']}) | " + " | ".join(cells) + " |")
    # C1 supplement: several trials per board, every trial counted.
    sup = load(args.c1_supplement)
    if sup:
        src = json.loads((HERE / "c1" / "sources.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in src["chosen"]}
        out["c1_supplement"] = {"runs": sup["runs"]}
        for arm in sup["arms"]:
            rows, k_all, n_all = [], 0, 0
            split = {True: [0, 0], False: [0, 0]}
            for sid, s in sup["scenarios"].items():
                ran = [t for t in s["arms"][arm]["trials"] if t.get("has_result")]
                k = sum(bool(t.get("success")) for t in ran)
                g = by_id[sid]["won_within_horizon"]
                split[g][0] += k
                split[g][1] += len(ran)
                k_all, n_all = k_all + k, n_all + len(ran)
                rows.append({"id": sid, "won_within_8": k, "trials": len(ran),
                             "won_on_scenario_turn": sum(bool(t.get("kill_on_scenario_turn")) for t in ran),
                             "loaded": sum(bool(t.get("loaded")) for t in ran),
                             "line_loaded": sum(bool(t.get("line_loaded")) for t in ran),
                             "in_game_won_within_8": g})
            out["c1_supplement"][arm] = {
                "won_within_8": k_all, "trials": n_all, "wilson95": sup["scenarios"] and wilson(k_all, n_all),
                "on_boards_the_game_won": split[True], "on_boards_it_did_not": split[False],
                "boards": table_of(rows)}
            md += ["", f"C1 supplement ({arm}): {k_all}/{n_all} won within 8 turns; "
                       f"{split[True][0]}/{split[True][1]} on the boards the game won, "
                       f"{split[False][0]}/{split[False][1]} on the others."]
    text = "\n".join(md) + "\n"
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if args.md:
        args.md.write_text(text, encoding="utf-8")
    args.json.write_text(dumps(out) + "\n", encoding="utf-8")
    print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
