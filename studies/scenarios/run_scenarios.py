#!/usr/bin/env python3
"""Seeded-board scenario runner (repair plan WS3): arms x N trials per scenario.

    py studies/scenarios/run_scenarios.py SCENARIO.json [SCENARIO.json ...] \\
        --jar SHIM.jar --out DIR [--arms stock,plan] [--trials 20] \\
        [--parallel 8] [--seed 2026101400] [--plans FILE] [--data-dir DIR]
    py studies/scenarios/run_scenarios.py --report-only --out DIR

Every trial is one JVM playing one game (shim >= 0.17.1, --scenario). Trial
k of every scenario and every arm uses --seed-forge SEED+k and a library
shuffle seeded with SEED+k, so arms pair on the same openings and the same
seeded libraries (Forge's own play is not fully deterministic under a seed:
studies/scenarios/SPIKE.md). Output under --out:

    run.json                         provenance (CLI, jar SHA-256, repo commit)
    <scenario>/trial_<k>.state       the Forge state text (shared by every arm)
    <scenario>/trial_<k>.info.json   what the writer expects Forge to hold
    <scenario>/<arm>/trial_<k>.jsonl raw shim output (+ .err, .cell.json)
    report.json, report.md           per scenario and arm

A finished trial (its JSONL has a result record) is not re-run unless
--force. Raw output stays out of git; commit summaries only.

Arms are data: ARMS below, extended or overridden by --arms-file (JSON
{name: {"pilot": "stock:Default" | "plan:SimLabHuman", "plan_version": 1|2,
"fix": "all"|"none"|"a,b", "jar": path}}). A seat's "pilots" object in the
scenario overrides the arm's pilot for that seat (for example "1 plan seat vs
3 stock"). Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import writer  # noqa: E402

FORGE_JAR = Path(os.environ.get(
    "FORGE_JAR", r"C:/Users/Vatto/forge/forge-gui-desktop-2.0.13-jar-with-dependencies.jar"))
MAX_PARALLEL = 8
DEFAULT_HORIZON = 8
ARMS = {
    # Every seat Forge's stock AI with its Default profile.
    "stock": {"pilot": "stock:Default"},
    # Every seat the plan agent (production's pilot), version-2 plans
    # (the tutoring hotfix) with every fix flag on.
    "plan": {"pilot": "plan:SimLabHuman", "plan_version": 2, "fix": "all"},
}
SEAT = re.compile(r"^(?:Additional)?Ai\((\d+)\)-")
TURN = re.compile(r"^Turn (\d+) ")
STACK_VERB = re.compile(r"^Ai\((\d+)\)-.*? (cast|activated|triggered) ")
# Forge names the command-zone effect card it creates for every commander
# player; it is bookkeeping, not a card the scenario placed.
COMMAND_EFFECT = "Commander Effect"


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def repo_commit() -> str:
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short=12", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


# --- setup ----------------------------------------------------------------

def seat_pilots(sc: dict, arm_name: str, arm: dict) -> list[str]:
    return [seat.get("pilots", {}).get(arm_name, arm["pilot"]) for seat in sc["seats"]]


def build_plans(decks: list[Path], arm: dict, out: Path, data_dir: str | None,
                fetch: bool) -> Path:
    """Plans for these decks at the arm's version, cached by content."""
    key = hashlib.sha256(json.dumps(
        [sorted(sha256(d) for d in decks), arm.get("plan_version", 2), arm.get("fix", "all")]
    ).encode()).hexdigest()[:12]
    path = out / "plans" / f"plans_v{arm.get('plan_version', 2)}_{key}.json"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(REPO / "engine" / "deck_plan.py"), *map(str, decks),
           "--plan-version", str(arm.get("plan_version", 2)), "--out", str(path)]
    if arm.get("plan_version", 2) >= 2 and arm.get("fix"):
        cmd += ["--fix", arm["fix"]]
    if fetch:
        cmd.append("--fetch")
    env = dict(os.environ)
    if data_dir:
        env["MTG_DATA_DIR"] = data_dir
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.exit(f"plan build failed:\n{r.stdout}\n{r.stderr}")
    plans = json.loads(path.read_text(encoding="utf-8"))
    bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}" for n, p in plans["decks"].items()
           if p.get("factsCoverage", 0) < 0.9]
    if bad:
        path.unlink()
        sys.exit(f"degraded plan data (card facts missing; pass --data-dir with a warm "
                 f"card cache, or --fetch): {bad}")
    return path


def trial_cmd(jar: Path, decks: list[Path], sc: dict, pilots: list[str], plans: Path | None,
              state: Path, seed: int, out: Path, timeout: int, horizon: int, xmx: str) -> list[str]:
    max_turns = int(sc.get("turn", 1)) + int(sc.get("horizon_turns", horizon))
    cmd = ["java", f"-Xmx{xmx}", "-cp", f"{jar}{os.pathsep}{FORGE_JAR}", "simlab.shim.SimShim",
           "--decks", *map(str, decks), "--games", "1", "--timeout", str(timeout),
           "--max-turns", str(max_turns), "--seat-pilots", ",".join(pilots),
           "--seed-forge", str(seed), "--scenario", str(state), "--out", str(out)]
    if plans is not None:
        cmd[cmd.index("--seat-pilots"):cmd.index("--seat-pilots")] = ["--plans", str(plans)]
    return cmd


def has_result(p: Path) -> bool:
    return p.exists() and '"rec":"result"' in p.read_text(encoding="utf-8", errors="replace")


def run_cell(job: dict) -> str:
    out: Path = job["out"]
    if has_result(out) and not job["force"]:
        return f"{job['label']} cached"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        rc = subprocess.run(job["cmd"], cwd=str(FORGE_JAR.parent), stdout=subprocess.DEVNULL,
                            stderr=eh).returncode
    wall = time.time() - t0
    out.with_suffix(".cell.json").write_text(json.dumps(
        {"rc": rc, "wall_s": round(wall, 1), "cmd": job["cmd"], "seed": job["seed"],
         "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))}, indent=1),
        encoding="utf-8")
    return f"{job['label']} rc={rc} {wall:.0f}s"


# --- reading one trial ------------------------------------------------------

def _counts(d) -> dict:
    return {str(k): int(v) for k, v in (d or {}).items()}


def check_board(info: dict, rec: dict) -> list[str]:
    """Differences between what the writer asked for and what the shim's
    scenario record says Forge holds after the apply. Empty = loaded as
    written."""
    diffs = []
    seats = rec.get("seats") or []
    if len(seats) != len(info["seats"]):
        return [f"seat count {len(seats)} != {len(info['seats'])}"]
    ids = {c["id"]: c["card"] for s in seats for c in s.get("Battlefield", [])}
    for i, (want, got) in enumerate(zip(info["seats"], seats)):
        if got.get("life") != want["life"]:
            diffs.append(f"seat {i} life {got.get('life')} != {want['life']}")
        if got.get("poison", 0) != want["poison"]:
            diffs.append(f"seat {i} poison {got.get('poison')} != {want['poison']}")
        for zone in ("hand", "graveyard", "exile", "command", "library"):
            have = [c["card"] for c in got.get(zone.capitalize(), []) if c["card"] != COMMAND_EFFECT]
            need = want["zones"][zone]
            if zone == "library":
                if have != need:
                    diffs.append(f"seat {i} library order differs (have {len(have)}, want {len(need)})")
            elif Counter(have) != Counter(need):
                diffs.append(f"seat {i} {zone}: have {sorted(have)} want {sorted(need)}")
        bf = got.get("Battlefield", [])
        have_sig = Counter()
        tokens_have = 0
        for c in bf:
            if c.get("token"):
                tokens_have += 1
                continue
            have_sig[json.dumps({"card": c["card"], "tapped": c.get("tapped", False),
                                 "sick": c.get("sick", False), "counters": _counts(c.get("counters")),
                                 "attached_to": ids.get(c.get("attachedTo")),
                                 "commander": bool(c.get("commander")),
                                 "damage": int(c.get("damage", 0))}, sort_keys=True)] += 1
        need_sig = Counter()
        tokens_need = 0
        for s in want["battlefield"]:
            if s["token"]:
                tokens_need += 1
                continue
            need_sig[json.dumps({k: v for k, v in s.items() if k != "token"}, sort_keys=True)] += 1
        if have_sig != need_sig:
            missing = list((need_sig - have_sig).elements())
            extra = list((have_sig - need_sig).elements())
            diffs.append(f"seat {i} battlefield: missing {missing} extra {extra}")
        if tokens_have != tokens_need:
            diffs.append(f"seat {i} tokens {tokens_have} != {tokens_need}")
    return diffs


def parse_trial(path: Path, sc: dict, info: dict | None) -> dict:
    """One trial's JSONL (and its .err / .cell.json) -> the report row."""
    t = {"file": path.name, "ran": path.exists()}
    if not path.exists():
        return t
    recs = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            recs.append(json.loads(line))
        except ValueError:
            t["bad_lines"] = t.get("bad_lines", 0) + 1
    meta = next((r for r in recs if r.get("rec") == "meta"), {})
    scen = next((r for r in recs if r.get("rec") == "scenario"), None)
    res = next((r for r in recs if r.get("rec") == "result"), None)
    players = meta.get("players", [])
    t["shim"] = meta.get("shim")
    t["shim_commit"] = meta.get("shimCommit")
    t["scenario_sha256"] = scen.get("sha256") if scen else None
    t["applied"] = bool(scen and scen.get("applied"))
    t["apply_error"] = scen.get("error") if scen else "no scenario record"
    t["board_diffs"] = check_board(info, scen) if (info and t["applied"]) else []
    t["loaded"] = t["applied"] and not t["board_diffs"]
    s_turn = int(sc.get("turn", 1))
    t["scenario_turn"] = s_turn
    t["has_result"] = res is not None
    if res:
        t.update({k: res.get(k) for k in ("winner", "draw", "turns", "timedOut", "turnCapped", "ms")})
        t["error"] = res.get("errorClass") if res.get("error") else None
        t["killFailed"] = bool(res.get("killFailed"))
        t["alive"] = [s.get("alive") for s in res.get("seats", [])]
    win_seat = None
    if t.get("winner"):
        m = SEAT.match(t["winner"])
        win_seat = int(m.group(1)) - 1 if m else None
    t["winner_seat"] = win_seat
    succ = sc.get("success")
    target = succ["seat"] if succ else win_seat
    won = win_seat is not None and win_seat == target
    t["success"] = bool(succ and won and t.get("turns") is not None
                        and t["turns"] <= int(succ.get("by_turn", 10 ** 6)))
    t["kill_on_scenario_turn"] = bool(won and t.get("turns") == s_turn)
    t["turns_to_kill"] = (t["turns"] - s_turn) if (won and t.get("turns") is not None) else None

    # Walk Forge's log in order. Entries before the scenario applied are the
    # discarded opening (mulligans, turn 1's untap); from the first TURN entry
    # the game is at the scenario turn until the next TURN entry.
    line = sc.get("line") or {}
    pieces = set(line.get("pieces", []))
    lseat = line.get("seat", succ["seat"] if succ else None)
    turn = None
    per_turn = defaultdict(Counter)       # turn -> Counter(verb) for line pieces
    combats = Counter()                   # turn -> beginning-of-combat steps
    by_piece = defaultdict(Counter)
    for r in recs:
        if r.get("rec") != "entry":
            continue
        msg = r.get("message", "")
        if r.get("type") == "TURN":
            m = TURN.match(msg)
            if m:
                turn = s_turn if turn is None else int(m.group(1))
            continue
        if turn is None:
            continue
        if r.get("type") == "PHASE" and "Beginning of Combat" in msg:
            # Forge prefixes a phase set by the state with "dev" and an extra
            # combat with "Additional".
            m = SEAT.match(re.sub(r"^dev", "", msg))
            if m and lseat is not None and int(m.group(1)) - 1 == lseat:
                combats[turn] += 1
        if r.get("type") == "STACK_ADD" and r.get("card") in pieces:
            m = STACK_VERB.match(msg)
            if m and (lseat is None or int(m.group(1)) - 1 == lseat):
                per_turn[turn][m.group(2)] += 1
                by_piece[r["card"]][m.group(2)] += 1
    it = {k: v["activated"] + v["triggered"] for k, v in per_turn.items()}
    t["line_seat"] = lseat
    t["piece_counts"] = {k: dict(v) for k, v in sorted(by_piece.items())}
    t["piece_activity_total"] = sum(sum(v.values()) for v in by_piece.values())
    t["iterations_max_turn"] = max(it.values()) if it else 0
    t["iterations_scenario_turn"] = it.get(s_turn, 0)
    t["combats_max_turn"] = max(combats.values()) if combats else 0
    t["extra_combats_scenario_turn"] = max(0, combats.get(s_turn, 0) - 1)
    agent = Counter(r.get("event") for r in recs if r.get("rec") == "agent")
    t["agent_events"] = dict(sorted(agent.items()))
    t["agent_events_on_pieces"] = sum(
        1 for r in recs if r.get("rec") == "agent" and any(p in r.get("detail", "") for p in pieces))
    turns_played = (t["turns"] - s_turn + 1) if t.get("turns") else None
    t["ms_per_turn"] = round(t["ms"] / turns_played) if (t.get("ms") and turns_played) else None
    # 0.17.1 exposes no per-decision timing; the executor prototype adds it.
    t["ms_per_decision"] = None
    err = path.with_suffix(".err")
    exc = []
    if err.exists():
        for l in err.read_text(encoding="utf-8", errors="replace").splitlines():
            if "Exception" in l or "shim: fatal" in l or re.search(r"\bError\b", l):
                exc.append(l.strip()[:200])
    t["exceptions"] = len(exc)
    t["exception_samples"] = list(dict.fromkeys(exc))[:3]
    cell = path.with_suffix(".cell.json")
    if cell.exists():
        c = json.loads(cell.read_text(encoding="utf-8"))
        t["rc"] = c.get("rc")
        t["wall_s"] = c.get("wall_s")
    t["players"] = players
    return t


# --- aggregate ----------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 3), round(min(1.0, c + h), 3))


def aggregate(trials: list[dict]) -> dict:
    ran = [t for t in trials if t.get("has_result")]
    n = len(ran)
    k = sum(t["success"] for t in ran)
    ttk = [t["turns_to_kill"] for t in ran if t["turns_to_kill"] is not None]
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    return {
        "trials": len(trials), "finished": n,
        "loaded": sum(t.get("loaded", False) for t in trials),
        "applied": sum(t.get("applied", False) for t in trials),
        "success": k, "success_rate": round(k / n, 3) if n else None, "success_wilson95": wilson(k, n),
        "kill_on_scenario_turn": sum(t["kill_on_scenario_turn"] for t in ran),
        "turns_to_kill_median": statistics.median(ttk) if ttk else None,
        "turns_to_kill_mean": mean(ttk),
        "draws": sum(bool(t.get("draw")) for t in ran),
        "turn_capped": sum(bool(t.get("turnCapped")) for t in ran),
        "timed_out": sum(bool(t.get("timedOut")) for t in ran),
        "errored": sum(bool(t.get("error")) for t in ran),
        "kill_failed": sum(bool(t.get("killFailed")) for t in ran),
        "exceptions": sum(t.get("exceptions", 0) for t in trials),
        "piece_activity_mean": mean([t["piece_activity_total"] for t in ran]),
        "iterations_max_turn_mean": mean([t["iterations_max_turn"] for t in ran]),
        "iterations_scenario_turn_mean": mean([t["iterations_scenario_turn"] for t in ran]),
        "extra_combats_scenario_turn_mean": mean([t["extra_combats_scenario_turn"] for t in ran]),
        "game_ms_mean": mean([t["ms"] for t in ran if t.get("ms")]),
        "ms_per_turn_mean": mean([t["ms_per_turn"] for t in ran if t.get("ms_per_turn")]),
        "ms_per_decision": None,
        "wall_s_total": round(sum(t.get("wall_s") or 0 for t in trials), 1),
        "wall_s_mean": mean([t["wall_s"] for t in trials if t.get("wall_s")]),
        "winners": dict(Counter(str(t.get("winner_seat")) for t in ran)),
    }


def write_report(out: Path) -> dict:
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    report = {"run": run, "scenarios": {}}
    for sid, meta in run["scenarios"].items():
        sc = writer.load(meta["path"])
        rows = {}
        for arm in run["arms"]:
            trials = []
            for k in range(run["trials"]):
                info_p = out / sid / f"trial_{k}.info.json"
                info = json.loads(info_p.read_text(encoding="utf-8")) if info_p.exists() else None
                trials.append(parse_trial(out / sid / arm / f"trial_{k}.jsonl", sc, info))
            rows[arm] = {"summary": aggregate(trials), "trials": trials}
        report["scenarios"][sid] = {"description": sc.get("description", ""),
                                    "turn": sc.get("turn"), "success": sc.get("success"),
                                    "line": sc.get("line"), "arms": rows}
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def _f(v) -> str:
    return "–" if v is None else str(v)


def markdown(report: dict) -> str:
    run = report["run"]
    out = [f"# Scenario report",
           "",
           f"Shim `{run['jar_name']}` (sha256 `{run['jar_sha256'][:16]}`), repo `{run['repo_commit']}`, "
           f"{run['trials']} trials per arm, seeds {run['seed']}..{run['seed'] + run['trials'] - 1}, "
           f"started {run['started']}. Trial k of every arm shares its Forge seed and library "
           f"shuffle. ms per decision: not exposed by this shim.",
           ""]
    for sid, s in report["scenarios"].items():
        succ = s.get("success")
        goal = (f"seat {succ['seat']} wins by turn {succ.get('by_turn')}" if succ else "no success condition")
        out += [f"## {sid}", "", s["description"], "",
                f"Scenario turn {s['turn']}; success: {goal}; line pieces: "
                f"{', '.join((s.get('line') or {}).get('pieces', [])) or '–'}.", "",
                "| Arm | Loaded | Success | 95% CI | Kill on scenario turn | Turns to kill (median) "
                "| Line activity (mean) | Iterations, best turn (mean) | Extra combats, scenario turn (mean) "
                "| Draws / capped / timed out | Errors / exceptions | Game ms (mean) | Wall s (total) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm, row in s["arms"].items():
            a = row["summary"]
            ci = a["success_wilson95"]
            out.append(
                f"| {arm} | {a['loaded']}/{a['trials']} | {a['success']}/{a['finished']} | "
                f"{'–' if ci is None else f'{ci[0]:.2f}-{ci[1]:.2f}'} | "
                f"{a['kill_on_scenario_turn']}/{a['finished']} | {_f(a['turns_to_kill_median'])} | "
                f"{_f(a['piece_activity_mean'])} | {_f(a['iterations_max_turn_mean'])} | "
                f"{_f(a['extra_combats_scenario_turn_mean'])} | "
                f"{a['draws']} / {a['turn_capped']} / {a['timed_out']} | "
                f"{a['errored']} / {a['exceptions']} | {_f(a['game_ms_mean'])} | {a['wall_s_total']} |")
        diffs = [(arm, t["file"], t["board_diffs"]) for arm, row in s["arms"].items()
                 for t in row["trials"] if t.get("board_diffs")]
        if diffs:
            out += ["", "Board differences (loaded != as written):"]
            out += [f"- {arm} {f}: {'; '.join(d)[:300]}" for arm, f, d in diffs[:10]]
        out.append("")
    return "\n".join(out)


# --- main ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="*", help="scenario JSON files (simlab-scenario/1)")
    ap.add_argument("--out", required=True, help="output directory (raw logs; never commit)")
    ap.add_argument("--jar", help="shim jar (>= 0.17.1)")
    ap.add_argument("--arms", default="stock,plan", help="comma list of arm names (default stock,plan)")
    ap.add_argument("--arms-file", help="JSON adding or overriding arms")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--parallel", type=int, default=MAX_PARALLEL, help=f"JVMs at once (at most {MAX_PARALLEL})")
    ap.add_argument("--seed", type=int, default=2026101400, help="trial k uses seed+k")
    ap.add_argument("--timeout", type=int, default=900, help="per-game wall clock, s")
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON,
                    help="turns after the scenario turn before the cap, unless the scenario sets horizon_turns")
    ap.add_argument("--plans", help="prebuilt plans JSON for plan seats (keyed by deck name)")
    ap.add_argument("--data-dir", help="MTG_DATA_DIR for building plans (card and combo caches)")
    ap.add_argument("--fetch", action="store_true", help="let plan building fetch card data")
    ap.add_argument("--xmx", default="3g")
    ap.add_argument("--force", action="store_true", help="re-run finished trials")
    ap.add_argument("--report-only", action="store_true", help="rebuild report.json/.md from --out")
    args = ap.parse_args()
    out = Path(args.out)
    if args.report_only:
        write_report(out)
        print((out / "report.md").read_text(encoding="utf-8"))
        return
    if not args.scenarios or not args.jar:
        ap.error("scenarios and --jar are required unless --report-only")
    if not 1 <= args.parallel <= MAX_PARALLEL:
        ap.error(f"--parallel must be 1..{MAX_PARALLEL}")
    arms = dict(ARMS)
    if args.arms_file:
        arms.update(json.loads(Path(args.arms_file).read_text(encoding="utf-8")))
    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arm_names:
        if a not in arms:
            ap.error(f"unknown arm {a!r}; known: {sorted(arms)}")
    out.mkdir(parents=True, exist_ok=True)
    jar = Path(args.jar).resolve()
    scen_meta, jobs = {}, []
    for sp in args.scenarios:
        sc = writer.load(sp)
        sid = sc.get("id") or Path(sp).stem
        if sid in scen_meta:
            sys.exit(f"duplicate scenario id {sid}")
        base = Path(sp).resolve().parent
        decks = [writer.resolve_path(s["deck"], base).resolve() for s in sc["seats"]]
        scen_meta[sid] = {"path": str(Path(sp).resolve()), "sha256": sha256(Path(sp)),
                          "decks": [str(d) for d in decks]}
        for k in range(args.trials):
            seed = args.seed + k
            text, info = writer.build(sc, seed=seed)
            state = out / sid / f"trial_{k}.state"
            state.parent.mkdir(parents=True, exist_ok=True)
            writer.write_state(state, text)
            (out / sid / f"trial_{k}.info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
            for w in info["warnings"] if k == 0 else []:
                print(f"{sid}: warning: {w}")
        for arm_name in arm_names:
            arm = arms[arm_name]
            pilots = seat_pilots(sc, arm_name, arm)
            plans = None
            if any(p.startswith("plan") for p in pilots):
                plans = Path(args.plans).resolve() if args.plans else build_plans(
                    decks, arm, out, args.data_dir, args.fetch)
                scen_meta[sid].setdefault("plans", {})[arm_name] = {"path": str(plans), "sha256": sha256(plans)}
            arm_jar = Path(arm.get("jar", jar)).resolve()
            for k in range(args.trials):
                seed = args.seed + k
                jl = out / sid / arm_name / f"trial_{k}.jsonl"
                jobs.append({"label": f"{sid} {arm_name} {k}", "out": jl, "seed": seed, "force": args.force,
                             "cmd": trial_cmd(arm_jar, decks, sc, pilots, plans, out / sid / f"trial_{k}.state",
                                              seed, jl, args.timeout, args.horizon, args.xmx)})
    run = {"cli": sys.argv, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "repo_commit": repo_commit(),
           "jar": str(jar), "jar_name": jar.name, "jar_sha256": sha256(jar), "forge_jar": str(FORGE_JAR),
           "arms": arm_names, "arm_defs": {a: arms[a] for a in arm_names}, "trials": args.trials,
           "seed": args.seed, "timeout": args.timeout, "horizon": args.horizon, "parallel": args.parallel,
           "scenarios": scen_meta}
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    t0 = time.time()
    print(f"{len(jobs)} trials, {args.parallel} at a time", flush=True)
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        for r in ex.map(run_cell, jobs):
            print(r, flush=True)
    print(f"wall {time.time() - t0:.0f}s", flush=True)
    write_report(out)
    print((out / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
