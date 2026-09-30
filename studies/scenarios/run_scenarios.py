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
--force, or unless its shim record names a different state file SHA-256
than the one just written for it (the scenario or a deck changed since it
ran). Raw output stays out of git; commit summaries only.

Arms are data: ARMS below, extended or overridden by --arms-file (JSON
{name: {"pilot": "stock:Default" | "plan:SimLabHuman", "plan_version": 1|2,
"fix": "all"|"none"|"a,b", "jar": path, "steps": true}}). A seat's "pilots"
object in the scenario overrides the arm's pilot for that seat (for example
"1 plan seat vs 3 stock"). An arm with "steps" (the E1 executor, shim >=
0.18.0-proto) is the plan arm plus the scenario's hand-written step file,
--steps DIR/<scenario id>.json (studies/e1_executor/README.md), merged into
its line deck's plan; a scenario without one runs that arm without steps.
Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import threading
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
    # The plan arm plus the E1 executor's step data for the line seat.
    "exec": {"pilot": "plan:SimLabHuman", "plan_version": 2, "fix": "all", "steps": True},
}
DEFAULT_STEPS = REPO / "studies" / "e1_executor" / "steps"
STEPS_FORMAT = "simlab-steps/1"
# The stop predicates the shim's StepRunner reads (repair plan WS9 part 3).
STOP_PREDICATES = {"count", "power_vs_life", "opponents_out", "mana_at_least", "no_progress"}
NO_PROGRESS_OF = {"mana", "opp_life", "opp_library", "power", "permanents"}
STEP_ZONES = {"Battlefield", "Hand", "Graveyard", "Exile", "Command", "Library"}
# StepRunner's agent-record detail: position, the executor's own decision
# time, ms since the line armed, then the event's fields.
EXEC_DETAIL = re.compile(r"^line=(\S+) step=(\d+) act=(\d+) it=(\d+) ms=([\d.]+) at=(\d+) ?(.*)$")
SEAT = re.compile(r"^(?:Additional)?Ai\((\d+)\)-")
TURN = re.compile(r"^Turn (\d+) ")
# Forge's outcome lines, written when the game ends: "<seat> has lost trying
# to draw cards from empty library", "<seat> has won because all opponents
# have lost" (every surviving seat of a draw reads "has won").
OUTCOME = re.compile(r"^((?:Additional)?Ai\(\d+\)-.+?) has (won|lost)\b")
STACK_VERB = re.compile(r"^Ai\((\d+)\)-.*? (cast|activated|triggered) ")
TARGETS = re.compile(r" targeting \[(.*)\]\s*$", re.S)
# Card names contain commas, so a target list splits on each "(instance id)"
# (the rule board.py _refs() and replay.ts attackerNames() follow); a player
# target (Ai(2)-name) carries no id.
TARGET_ID = re.compile(r" \(\d+\)(?:, |$)")
# Forge names the command-zone effect card it creates for every commander
# player; it is bookkeeping, not a card the scenario placed.
COMMAND_EFFECT = "Commander Effect"
# The shim's header and scenario records (compact JSON; spaces allowed).
REC_HEAD = re.compile(r'"rec"\s*:\s*"(?:scenario|meta)"')
REC_RESULT = re.compile(r'"rec"\s*:\s*"result"')


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def repo_commit() -> str:
    """HEAD, with "-dirty" when studies/scenarios differs from it (the
    runner, the writer or a scenario file), as the shim's build does."""
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short=12", "HEAD"],
                       capture_output=True, text=True)
    head = r.stdout.strip() or "unknown"
    if head != "unknown":
        s = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", str(HERE)],
                           capture_output=True, text=True)
        if s.stdout.strip():
            head += "-dirty"
    return head


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


# --- the E1 executor arm (repair plan WS9 Phase A) ---------------------------

def validate_steps(steps: dict) -> list[str]:
    """Schema errors in a simlab-steps/1 file ([] when it is well formed).
    The shim reads only "lines"; the rest is the runner's."""
    err = []
    if steps.get("format") != STEPS_FORMAT:
        err.append(f"format must be {STEPS_FORMAT}")
    if not isinstance(steps.get("deck"), str):
        err.append("deck (the line deck's name) is required")
    lines = steps.get("lines")
    if not isinstance(lines, list) or not lines:
        return err + ["lines must be a non-empty list"]

    def action(a, where):
        if not isinstance(a, dict):
            return [f"{where}: not an object"]
        e = []
        op = a.get("op", "activate")
        if op not in ("activate", "cast", "pass"):
            e.append(f"{where}: op {op!r} is not activate, cast or pass")
        if op != "pass" and not isinstance(a.get("card"), str):
            e.append(f"{where}: card is required")
        if a.get("zone", "Battlefield") not in STEP_ZONES:
            e.append(f"{where}: zone must be one of {sorted(STEP_ZONES)}")
        t = a.get("target")
        if t is not None and (not isinstance(t, dict) or ("card" in t) == ("player" in t)):
            e.append(f"{where}: target needs exactly one of card, player")
        elif t and t.get("player") not in (None, "self", "opponent"):
            e.append(f"{where}: target player must be self or opponent")
        return e

    for i, line in enumerate(lines):
        w = f"lines[{i}]"
        if not isinstance(line, dict) or not isinstance(line.get("id"), str):
            err.append(f"{w}: id is required")
            continue
        pieces = line.get("pieces", {})
        if not isinstance(pieces, dict) or not set(pieces.values()) <= STEP_ZONES:
            err.append(f"{w}: pieces must map card name to a zone ({sorted(STEP_ZONES)})")
        for j, t in enumerate(line.get("triggers", [])):
            if not isinstance(t, dict) or not isinstance(t.get("card"), str):
                err.append(f"{w}.triggers[{j}]: card is required")
            elif "target" in t:
                err += action({"op": "activate", "card": t["card"], "target": t["target"]},
                              f"{w}.triggers[{j}]")
        steps_ = line.get("steps")
        if not isinstance(steps_, list) or not steps_:
            err.append(f"{w}: steps must be a non-empty list")
            continue
        for j, st in enumerate(steps_):
            sw = f"{w}.steps[{j}]"
            if not isinstance(st, dict):
                err.append(f"{sw}: not an object")
                continue
            body = st.get("loop", [st])
            if not isinstance(body, list) or not body:
                err.append(f"{sw}: loop must be a non-empty list")
                continue
            for k, a in enumerate(body):
                err += action(a, f"{sw}.loop[{k}]" if "loop" in st else sw)
            bad = set(st.get("until", {})) - STOP_PREDICATES
            if bad:
                err.append(f"{sw}: unknown stop predicate(s) {sorted(bad)}")
            np_ = st.get("until", {}).get("no_progress")
            if np_ is not None and np_.get("of", "mana") not in NO_PROGRESS_OF:
                err.append(f"{sw}: no_progress.of must be one of {sorted(NO_PROGRESS_OF)}")
    n = len(lines[0].get("steps") or []) if isinstance(lines[0], dict) else 0
    for k in ("state_step", "outlet_step"):
        if k in steps and not (isinstance(steps[k], int) and 0 <= steps[k] < n):
            err.append(f"{k} must index lines[0].steps")
    return err


def load_steps(steps_dir: Path, sid: str) -> tuple[Path, dict] | None:
    """The scenario's step file, validated, or None when it has none."""
    p = Path(steps_dir) / f"{sid}.json"
    if not p.exists():
        return None
    steps = json.loads(p.read_text(encoding="utf-8"))
    bad = validate_steps(steps)
    if bad:
        sys.exit(f"{p}: " + "; ".join(bad))
    return p, steps


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def merge_steps(plans_path: Path, steps: dict, out: Path, sid: str) -> Path:
    """A plans file for the exec arm: the arm's plans with the step file's
    "lines" as the line deck's "steps" (the channel the shim reads) and its
    optional "plan_patch" deep-merged into that deck's plan."""
    plans = json.loads(Path(plans_path).read_text(encoding="utf-8"))
    deck = steps["deck"]
    if deck not in plans.get("decks", {}):
        sys.exit(f"step file deck {deck!r} is not in {plans_path}")
    plan = _deep_merge(plans["decks"][deck], steps.get("plan_patch") or {})
    plan["steps"] = {"lines": steps["lines"]}
    plans["decks"][deck] = plan
    text = json.dumps(plans, indent=1)
    path = out / "plans" / f"plans_exec_{sid}_{hashlib.sha256(text.encode()).hexdigest()[:12]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return path


def exec_records(recs: list[dict]) -> list[dict]:
    """StepRunner's agent records (exec_arm/step/stop/abort), parsed."""
    out = []
    for r in recs:
        if r.get("rec") != "agent" or not str(r.get("event", "")).startswith("exec_"):
            continue
        m = EXEC_DETAIL.match(r.get("detail", ""))
        if not m:
            continue
        rest = m.group(7)
        why = re.search(r"\bwhy=(\S+)", rest)
        op = re.search(r"\bop=(\S+)", rest)
        out.append({"event": r["event"], "turn": r.get("turn"), "player": r.get("player"),
                    "line": m.group(1), "step": int(m.group(2)), "act": int(m.group(3)),
                    "it": int(m.group(4)), "ms": float(m.group(5)), "at": int(m.group(6)),
                    "why": why.group(1) if why else None, "op": op.group(1) if op else None,
                    "detail": rest})
    return out


def exec_summary(recs: list[dict], line_player: str | None, s_turn: int, meta: dict | None) -> dict:
    """One trial's executor figures. "state" is the step file's stated
    infinite state (state_step's loop stopped on one of its own predicates,
    not on max, the budget or exhaustion); "outlet" is outlet_step firing (an
    action issued, or for a pass step the line seat declaring attackers on
    the scenario turn after the hand-off)."""
    ex = exec_records(recs)
    meta = meta or {}
    stops = Counter(e["why"] for e in ex if e["event"] == "exec_stop" and e["op"] != "confirm")
    aborts = [e["detail"].split("why=", 1)[-1] for e in ex if e["event"] == "exec_abort"]
    st, ot = meta.get("state_step"), meta.get("outlet_step")
    state = st is not None and any(e["event"] == "exec_stop" and e["step"] == st and e["op"] != "confirm"
                                   and e["why"] in STOP_PREDICATES for e in ex)
    outlet = False
    if ot is not None:
        if meta.get("outlet_op") == "pass":
            handed = any(e["event"] == "exec_stop" and e["step"] == ot and e["why"] == "handoff" for e in ex)
            turn, attacked = None, False
            for r in recs:
                if r.get("rec") != "entry":
                    continue
                m = TURN.match(r.get("message", "")) if r.get("type") == "TURN" else None
                if m:
                    # as parse_trial counts: the first TURN entry is the scenario turn
                    turn = s_turn if turn is None else int(m.group(1))
                elif (turn == s_turn and r.get("type") == "COMBAT" and line_player
                      and r.get("message", "").startswith(line_player + " assigned")):
                    attacked = True
            outlet = handed and attacked
        else:
            outlet = any(e["event"] == "exec_step" and e["step"] == ot and e["op"] in ("activate", "cast")
                         for e in ex)
    ms = [e["ms"] for e in ex]
    return {"line_player": line_player, "armed": sum(e["event"] == "exec_arm" for e in ex),
            "actions": sum(e["event"] == "exec_step" and e["op"] in ("activate", "cast") for e in ex),
            "binds": sum(e["event"] == "exec_step" and e["op"] == "bind" for e in ex),
            "confirms": sum(e["op"] == "confirm" for e in ex),
            "stops": dict(stops), "aborts": aborts, "decisions": len(ms), "decision_ms": ms,
            "state": state, "outlet": outlet, "state_then_outlet": state and outlet}


def trial_cmd(jar: Path, decks: list[Path], sc: dict, pilots: list[str], plans: Path | None,
              state: Path, seed: int, out: Path, timeout: int, horizon: int, xmx: str,
              jvm_args: list[str] | None = None) -> list[str]:
    max_turns = int(sc.get("turn", 1)) + int(sc.get("horizon_turns", horizon))
    cmd = ["java", *(jvm_args or []), f"-Xmx{xmx}", "-cp", f"{jar}{os.pathsep}{FORGE_JAR}", "simlab.shim.SimShim",
           "--decks", *map(str, decks), "--games", "1", "--timeout", str(timeout),
           "--max-turns", str(max_turns), "--seat-pilots", ",".join(pilots),
           "--seed-forge", str(seed), "--scenario", str(state), "--out", str(out)]
    if plans is not None:
        cmd[cmd.index("--seat-pilots"):cmd.index("--seat-pilots")] = ["--plans", str(plans)]
    return cmd


def has_result(p: Path) -> bool:
    return p.exists() and REC_RESULT.search(p.read_text(encoding="utf-8", errors="replace")) is not None


def recorded_state_sha(p: Path) -> str | None:
    """The state file SHA-256 the shim recorded for a trial (its scenario
    record, else the meta header), or None."""
    if not p.exists():
        return None
    meta_sha = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if REC_HEAD.search(line):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") == "scenario" and r.get("sha256"):
                return r["sha256"]
            meta_sha = meta_sha or r.get("scenarioSha256")
    return meta_sha


def recorded_plans_sha(p: Path) -> str | None:
    """The plans file SHA-256 in a trial's shim header (null without plans),
    so a trial whose plans or step data changed is re-run, not reused."""
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if REC_HEAD.search(line):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") == "meta":
                return r.get("plansSha256")
    return None


def run_cell(job: dict) -> str:
    out: Path = job["out"]
    stale = False
    if has_result(out) and not job["force"]:
        # A cached trial is reused only if it played the state just written:
        # a scenario or deck edited since would otherwise pair an old game
        # with the new board check.
        if recorded_state_sha(out) == sha256(job["state"]) and recorded_plans_sha(out) == job.get("plans_sha"):
            return f"{job['label']} cached"
        stale = True
    out.parent.mkdir(parents=True, exist_ok=True)
    # --affinity: worker slot i pins its JVM to masks[i % n] (Windows CPU
    # affinity, set right after start; Forge spends its first ~15 s loading).
    masks = job.get("affinity") or []
    mask = masks[int(threading.current_thread().name.rsplit("_", 1)[-1]) % len(masks)] if masks else None
    t0 = time.time()
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        p = subprocess.Popen(job["cmd"], cwd=str(FORGE_JAR.parent), stdout=subprocess.DEVNULL, stderr=eh)
        if mask:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Get-Process -Id {p.pid}).ProcessorAffinity = {int(mask, 16)}"],
                           capture_output=True)
        rc = p.wait()
    wall = time.time() - t0
    out.with_suffix(".cell.json").write_text(json.dumps(
        {"rc": rc, "wall_s": round(wall, 1), "cmd": job["cmd"], "seed": job["seed"], "affinity": mask,
         "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))}, indent=1),
        encoding="utf-8")
    return f"{job['label']} rc={rc} {wall:.0f}s" + (" (re-run: its cached game played another state or plans file)" if stale else "")


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
            have_sig[_have_sig(c, ids)] += 1
        need_sig = Counter()
        tokens_need = 0
        transformed = 0
        for s in want["battlefield"]:
            if s["token"]:
                tokens_need += 1
                continue
            if s.get("transformed"):
                transformed += 1        # compared by count: it reads back under its back face
                continue
            need_sig[_need_sig(s)] += 1
        if have_sig != need_sig:
            missing = list((need_sig - have_sig).elements())
            extra = list((have_sig - need_sig).elements())
            if missing or len(extra) != transformed:
                diffs.append(f"seat {i} battlefield: missing {missing} extra {extra}")
        elif transformed:
            diffs.append(f"seat {i} battlefield: {transformed} transformed card(s) missing")
        if tokens_have != tokens_need:
            diffs.append(f"seat {i} tokens {tokens_have} != {tokens_need}")
    return diffs


def _have_sig(c: dict, ids: dict) -> str:
    """A battlefield card as the shim read it back, in the writer's terms."""
    return json.dumps({"card": c["card"], "tapped": c.get("tapped", False),
                       "sick": c.get("sick", False), "counters": _counts(c.get("counters")),
                       "attached_to": ids.get(c.get("attachedTo")),
                       "commander": bool(c.get("commander")),
                       "damage": int(c.get("damage", 0))}, sort_keys=True)


def _need_sig(s: dict) -> str:
    """A battlefield card as the writer placed it (writer.expected_sig)."""
    return json.dumps({k: v for k, v in s.items() if k != "token"}, sort_keys=True)


def line_loaded(info: dict, rec: dict, line: dict | None) -> bool | None:
    """Whether the line seat's line pieces read back as written, whatever
    else on the board differs: on the battlefield card by card (tapped,
    sickness, counters, attachment), and in hand, graveyard, exile, command
    and library by count, so a line held in hand (S5's Oracle and
    Consultation) is checked too. A real-game board can differ elsewhere
    because Forge runs enter-the-battlefield replacements while it loads
    (Mox Diamond, a clone's copy choice); this says whether the line under
    test survived."""
    if not line or not info or not rec or line.get("seat") is None:
        return None
    seats, i = rec.get("seats") or [], line["seat"]
    if i >= len(seats) or i >= len(info["seats"]):
        return None
    pieces = set(line.get("pieces", []))
    ids = {c["id"]: c["card"] for s in seats for c in s.get("Battlefield", [])}
    have = Counter(_have_sig(c, ids) for c in seats[i].get("Battlefield", [])
                   if not c.get("token") and c["card"] in pieces)
    need = Counter(_need_sig(s) for s in info["seats"][i]["battlefield"]
                   if not s["token"] and not s.get("transformed") and s.get("card") in pieces)
    if have != need:
        return False
    for zone in ("hand", "graveyard", "exile", "command", "library"):
        got = Counter(c["card"] for c in seats[i].get(zone.capitalize(), []) if c["card"] in pieces)
        want = Counter(n for n in info["seats"][i]["zones"][zone] if n in pieces)
        if got != want:
            return False
    return True


def zone_moves(recs: list[dict], seat: str | None, frm: str, to: str, first_turn: int,
               last_turn: int) -> list[tuple[str, str]]:
    """(card name, Forge's core types) the seat moved from zone frm to zone
    to, in order, from the shim's zone records stamped first_turn..last_turn.
    The records written while the state loads carry turn 1, so a scenario
    turn above 1 excludes them. The seat is the zone's owner: fromPlayer, or
    toPlayer when the move starts on the stack."""
    out = []
    for r in recs:
        if r.get("rec") != "zone" or r.get("from") != frm or r.get("to") != to:
            continue
        if not first_turn <= int(r.get("turn", 0)) <= last_turn:
            continue
        if (r.get("fromPlayer") or r.get("toPlayer")) == seat:
            out.append((r.get("card"), r.get("types", "")))
    return out


def parse_trial(path: Path, sc: dict, info: dict | None, exec_meta: dict | None = None) -> dict:
    """One trial's JSONL (and its .err / .cell.json) -> the report row.
    exec_meta: the exec arm's step-file facts (state_step, outlet_step,
    outlet_op), for the executor columns."""
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
    # Did this game play the state file now beside it? False means the
    # trial ran on an older state (the scenario or a deck changed since),
    # so its board check and scoring describe another board.
    state = path.parent.parent / f"{path.stem}.state"
    t["state_matches"] = (t["scenario_sha256"] == sha256(state)) \
        if (t["scenario_sha256"] and state.exists()) else None
    t["applied"] = bool(scen and scen.get("applied"))
    t["apply_error"] = scen.get("error") if scen else "no scenario record"
    t["board_diffs"] = check_board(info, scen) if (info and t["applied"]) else []
    t["loaded"] = t["applied"] and not t["board_diffs"]
    t["line_loaded"] = line_loaded(info, scen, sc.get("line")) if t["applied"] else False
    s_turn = int(sc.get("turn", 1))
    t["scenario_turn"] = s_turn
    t["has_result"] = res is not None
    err = path.with_suffix(".err")
    err_text = err.read_text(encoding="utf-8", errors="replace") if err.exists() else ""
    game_over_threw = "setGameOver threw" in err_text
    t["game_over_threw"] = game_over_threw
    outcomes = {}
    for r in recs:
        if r.get("rec") == "entry" and r.get("type") == "GAME_OUTCOME":
            m = OUTCOME.match(r.get("message", ""))
            if m:
                outcomes[m.group(1)] = m.group(2)
    t["outcomes"] = outcomes
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
    stype = (succ or {}).get("type", "win")
    by_turn = int((succ or {}).get("by_turn", 10 ** 6))
    if stype == "zone":
        # A named card moved between two zones for the seat (a tutor's pick):
        # zone records from the scenario turn to by_turn, in the order Forge
        # moved them.
        seat_name = players[succ["seat"]] if succ["seat"] < len(players) else None
        moves = zone_moves(recs, seat_name, succ["from"], succ["to"], s_turn, by_turn)
        t["zone_moves"] = [m[0] for m in moves[:10]]
        t["zone_first"] = moves[0][0] if moves else None
        wanted = set(succ["cards"])
        # types_any: a move also qualifies when Forge types the card as any of
        # these (a class of right answers, such as "usable from the graveyard").
        types_any = set(succ.get("types_any") or [])
        ok = lambda m: m[0] in wanted or bool(types_any & set(m[1].split(",")))
        t["success"] = bool(moves and ok(moves[0])) if succ.get("first") else any(map(ok, moves))
    elif stype == "alive":
        # The seat has not lost when the game ends (the scenario caps the game
        # at by_turn through horizon_turns): for "do not kill yourself" tests.
        # Forge's own outcome lines decide. When setGameOver threw at the
        # shim's turn-cap kill (a Forge NullPointerException the shim catches)
        # those lines are never written and the result's alive flags are not
        # reliable (measured: seats at 33 and 40 life flagged dead), so the
        # trial is left unscored rather than guessed.
        seat_name = players[succ["seat"]] if succ["seat"] < len(players) else None
        alive = t.get("alive") or []
        if seat_name in outcomes:
            t["success"] = outcomes[seat_name] == "won"
        elif game_over_threw:
            t["success"] = None
            t["unscored"] = "setGameOver threw before Forge wrote the outcome"
        else:
            t["success"] = bool(res and succ["seat"] < len(alive) and alive[succ["seat"]])
    else:
        t["success"] = bool(succ and won and t.get("turns") is not None and t["turns"] <= by_turn)
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
    targets = defaultdict(Counter)        # piece -> Counter("verb: target")
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
                tm = TARGETS.search(msg)
                for name in (TARGET_ID.split(tm.group(1)) if tm else []):
                    if name.strip():
                        targets[r["card"]][f"{m.group(2)}: {name.strip()}"] += 1
    it = {k: v["activated"] + v["triggered"] for k, v in per_turn.items()}
    t["line_seat"] = lseat
    t["piece_counts"] = {k: dict(v) for k, v in sorted(by_piece.items())}
    # What each line piece's casts, activations and triggers targeted (S1 and
    # S2 test a trigger's target: did the copy untap Kiki, did Derevi untap
    # Cradle).
    t["piece_targets"] = {k: dict(v.most_common()) for k, v in sorted(targets.items())}
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
    # Per-decision timing exists only for the E1 executor's own decisions
    # (shim 0.18.0-proto exec_* records); none for stock or plan seats.
    t["ms_per_decision"] = None
    if exec_meta is not None or any(r.get("rec") == "agent" and str(r.get("event", "")).startswith("exec_")
                                    for r in recs):
        lp = players[lseat] if lseat is not None and lseat < len(players) else None
        t["exec"] = exec_summary(recs, lp, s_turn, exec_meta)
        ms = t["exec"]["decision_ms"]
        t["ms_per_decision"] = round(statistics.median(ms), 3) if ms else None
    exc = []
    for l in err_text.splitlines():
        if "Exception" in l or "shim: fatal" in l or re.search(r"\bError\b", l):
            exc.append(l.strip()[:200])
    t["exceptions"] = len(exc)
    t["exception_samples"] = list(dict.fromkeys(exc))[:3]
    cell = path.with_suffix(".cell.json")
    if cell.exists():
        c = json.loads(cell.read_text(encoding="utf-8"))
        t["rc"] = c.get("rc")
        t["wall_s"] = c.get("wall_s")
    # Unhandled: the JVM exited non-zero, the shim died, or the game ended as
    # an errored result. Exceptions Forge catches and prints (its attack AI's
    # worker futures, a failed setGameOver the shim catches) are in
    # `exceptions`, not here.
    t["unhandled"] = bool(t.get("rc") not in (None, 0) or "shim: fatal" in err_text or t.get("error"))
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
    scored = [t for t in ran if t.get("success") is not None]
    k = sum(bool(t["success"]) for t in scored)
    ttk = [t["turns_to_kill"] for t in ran if t["turns_to_kill"] is not None]
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    summary = {
        "trials": len(trials), "finished": n,
        "loaded": sum(t.get("loaded", False) for t in trials),
        "line_loaded": sum(bool(t.get("line_loaded")) for t in trials),
        "applied": sum(t.get("applied", False) for t in trials),
        # trials whose game played a different state file than the one now on disk
        "stale": sum(t.get("state_matches") is False for t in trials),
        "scored": len(scored), "unscored": n - len(scored),
        "success": k, "success_rate": round(k / len(scored), 3) if scored else None,
        "success_wilson95": wilson(k, len(scored)),
        "kill_on_scenario_turn": sum(t["kill_on_scenario_turn"] for t in ran),
        "turns_to_kill_median": statistics.median(ttk) if ttk else None,
        "turns_to_kill_mean": mean(ttk),
        "draws": sum(bool(t.get("draw")) for t in ran),
        "turn_capped": sum(bool(t.get("turnCapped")) for t in ran),
        "timed_out": sum(bool(t.get("timedOut")) for t in ran),
        "errored": sum(bool(t.get("error")) for t in ran),
        "kill_failed": sum(bool(t.get("killFailed")) for t in ran),
        "exceptions": sum(t.get("exceptions", 0) for t in trials),
        "unhandled": sum(bool(t.get("unhandled")) for t in trials),
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
        # zone scenarios: the seat's first qualifying move per trial (the pick)
        "zone_first": dict(Counter(str(t.get("zone_first")) for t in ran if "zone_first" in t)),
    }
    ex = [t["exec"] for t in ran if "exec" in t]
    if ex:
        ms = sorted(m for e in ex for m in e["decision_ms"])
        pct = lambda q: ms[min(len(ms) - 1, int(q * len(ms)))] if ms else None
        stops = Counter()
        for e in ex:
            stops.update(e["stops"])
        summary["exec"] = {
            "trials": len(ex), "armed": sum(e["armed"] > 0 for e in ex),
            "state": sum(e["state"] for e in ex), "outlet": sum(e["outlet"] for e in ex),
            "state_then_outlet": sum(e["state_then_outlet"] for e in ex),
            "state_then_outlet_wilson95": wilson(sum(e["state_then_outlet"] for e in ex), len(ex)),
            "aborted": sum(bool(e["aborts"]) for e in ex),
            "abort_reasons": dict(Counter(" ".join(a.split()[:2]) for e in ex for a in e["aborts"])),
            "stop_reasons": dict(stops),
            "actions_mean": mean([e["actions"] for e in ex]),
            "decisions": len(ms),
            "decision_ms_median": round(statistics.median(ms), 3) if ms else None,
            "decision_ms_p95": pct(0.95), "decision_ms_max": ms[-1] if ms else None,
        }
        summary["ms_per_decision"] = summary["exec"]["decision_ms_median"]
    return summary


def write_report(out: Path) -> dict:
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    report = {"run": run, "scenarios": {}}
    for sid, meta in run["scenarios"].items():
        sc = writer.load(meta["path"])
        rows = {}
        for arm in run["arms"]:
            trials = []
            ex_meta = (meta.get("steps") or {}).get(arm)
            for k in range(run["trials"]):
                info_p = out / sid / f"trial_{k}.info.json"
                info = json.loads(info_p.read_text(encoding="utf-8")) if info_p.exists() else None
                trials.append(parse_trial(out / sid / arm / f"trial_{k}.jsonl", sc, info, ex_meta))
            rows[arm] = {"summary": aggregate(trials), "trials": trials}
        report["scenarios"][sid] = {"description": sc.get("description", ""),
                                    "turn": sc.get("turn"), "success": sc.get("success"),
                                    "line": sc.get("line"), "arms": rows}
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def _f(v) -> str:
    return "–" if v is None else str(v)


def success_text(succ: dict | None) -> str:
    if not succ:
        return "no success condition"
    kind = succ.get("type", "win")
    if kind == "zone":
        also = f", or any {'/'.join(succ['types_any'])} card" if succ.get("types_any") else ""
        names = f"{', '.join(succ['cards'])}{also}"
        if succ.get("first"):
            return (f"seat {succ['seat']}'s first {succ['from']} to {succ['to']} move by turn "
                    f"{succ['by_turn']} is one of: {names}")
        return (f"seat {succ['seat']} moves one of: {names} from {succ['from']} to {succ['to']} "
                f"by turn {succ['by_turn']}")
    if kind == "alive":
        return f"seat {succ['seat']} has not lost at turn {succ['by_turn']}"
    return f"seat {succ['seat']} wins by turn {succ.get('by_turn', 'the cap')}"


def markdown(report: dict) -> str:
    run = report["run"]
    out = [f"# Scenario report",
           "",
           f"Shim `{run['jar_name']}` (sha256 `{run['jar_sha256'][:16]}`), repo `{run['repo_commit']}`, "
           f"{run['trials']} trials per arm, seeds {run['seed']}..{run['seed'] + run['trials'] - 1}, "
           f"started {run['started']}. Trial k of every arm shares its Forge seed and library "
           f"shuffle. ms per decision: the E1 executor's own decisions only (exec arms)."
           + (f" Wall clock {run['wall_s']} s at {run['parallel']} JVMs ({run['trials_run']} trials run, "
              f"{run['trials_cached']} cached)." if run.get("wall_s") is not None else ""),
           ""]
    for sid, s in report["scenarios"].items():
        goal = success_text(s.get("success"))
        out += [f"## {sid}", "", s["description"], "",
                f"Scenario turn {s['turn']}; success: {goal}; line pieces: "
                f"{', '.join((s.get('line') or {}).get('pieces', [])) or '–'}.", "",
                "| Arm | Loaded (exact / line pieces) | Success | 95% CI | Kill on scenario turn | Turns to kill (median) "
                "| Line activity (mean) | Iterations, best turn (mean) | Extra combats, scenario turn (mean) "
                "| Draws / capped / timed out | Errors / exceptions | Game ms (mean) | Wall s (total) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm, row in s["arms"].items():
            a = row["summary"]
            ci = a["success_wilson95"]
            out.append(
                f"| {arm} | {a['loaded']} / {a.get('line_loaded', '–')} of {a['trials']} | "
                f"{a['success']}/{a.get('scored', a['finished'])} | "
                f"{'–' if ci is None else f'{ci[0]:.2f}-{ci[1]:.2f}'} | "
                f"{a['kill_on_scenario_turn']}/{a['finished']} | {_f(a['turns_to_kill_median'])} | "
                f"{_f(a['piece_activity_mean'])} | {_f(a['iterations_max_turn_mean'])} | "
                f"{_f(a['extra_combats_scenario_turn_mean'])} | "
                f"{a['draws']} / {a['turn_capped']} / {a['timed_out']} | "
                f"{a['errored']} / {a['exceptions']} | {_f(a['game_ms_mean'])} | {a['wall_s_total']} |")
        exs = [(arm, row["summary"]["exec"], row["summary"]) for arm, row in s["arms"].items()
               if row["summary"].get("exec")]
        if exs:
            out += ["", "Executor (E1): *state* = the step file's stated infinite state reached (its loop "
                        "stopped on its own predicate); *outlet* = the outlet step fired after it.", "",
                    "| Arm | Armed | State | Outlet | State then outlet | 95% CI | Aborted (reasons) "
                    "| Stops | Actions (mean) | Decisions | Decision ms (median / p95 / max) "
                    "| Unhandled / printed exceptions |",
                    "|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for arm, e, a in exs:
                ci = e["state_then_outlet_wilson95"]
                reasons = "; ".join(f"{k} x{v}" for k, v in sorted(e["abort_reasons"].items()))
                stops = "; ".join(f"{k} x{v}" for k, v in sorted(e["stop_reasons"].items(), key=str))
                out.append(
                    f"| {arm} | {e['armed']}/{e['trials']} | {e['state']} | {e['outlet']} | "
                    f"{e['state_then_outlet']}/{e['trials']} | "
                    f"{'–' if ci is None else f'{ci[0]:.2f}-{ci[1]:.2f}'} | "
                    f"{e['aborted']}{f' ({reasons})' if reasons else ''} | {stops or '–'} | "
                    f"{_f(e['actions_mean'])} | {e['decisions']} | {_f(e['decision_ms_median'])} / "
                    f"{_f(e['decision_ms_p95'])} / {_f(e['decision_ms_max'])} | "
                    f"{a.get('unhandled', '–')} / {a['exceptions']} |")
        picks = [(arm, row["summary"].get("zone_first")) for arm, row in s["arms"].items()
                 if row["summary"].get("zone_first")]
        if picks:
            z = s.get("success") or {}
            out += ["", f"First {z.get('from')} to {z.get('to')} move per trial, the pick "
                        f"(None: no such move by the deadline):"]
            out += [f"- {arm}: " + ", ".join(f"{k} {v}" for k, v in sorted(z.items(), key=lambda kv: -kv[1]))
                    for arm, z in picks]
        stale = [(arm, t["file"]) for arm, row in s["arms"].items()
                 for t in row["trials"] if t.get("state_matches") is False]
        if stale:
            out += ["", f"**Stale trials ({len(stale)}):** these games played an older state file than the "
                        "one now in the run directory (the scenario or a deck changed since); re-run them: "
                        + ", ".join(f"{arm} {f}" for arm, f in stale[:10])]
        diffs = [(arm, t["file"], t["board_diffs"]) for arm, row in s["arms"].items()
                 for t in row["trials"] if t.get("board_diffs")]
        if diffs:
            out += ["", "Board differences (loaded != as written):"]
            out += [f"- {arm} {f}: {'; '.join(d)[:300]}" for arm, f, d in diffs[:10]]
        out.append("")
    return "\n".join(out)


# --- main ---------------------------------------------------------------------

INVOCATION_KEYS = ("started", "finished", "repo_commit", "jar_sha256", "arms", "trials", "seed", "parallel",
                   "wall_s", "trials_run", "trials_cached")


def invocation_record(run: dict) -> dict:
    """One invocation's provenance, as kept in run.json's history."""
    return dict({k: run.get(k) for k in INVOCATION_KEYS}, scenarios=len(run.get("scenarios") or {}))


def previous_invocations(path: Path) -> list[dict]:
    """The invocation history of an existing run.json; a run.json written
    before the history existed counts as one invocation (its own fields)."""
    if not path.exists():
        return []
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    if "invocations" not in old:
        return [invocation_record(old)] if old.get("started") else []
    hist = list(old["invocations"])
    if not old.get("finished"):
        # that invocation was interrupted: its own record was never appended
        hist.append(invocation_record(old))
    return hist

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
    ap.add_argument("--steps", default=str(DEFAULT_STEPS),
                    help="step files for arms with \"steps\" (<scenario id>.json; default %(default)s)")
    ap.add_argument("--fetch", action="store_true", help="let plan building fetch card data")
    ap.add_argument("--xmx", default="3g")
    ap.add_argument("--jvm-arg", action="append", default=[],
                    help="extra JVM option, repeatable (e.g. -XX:ActiveProcessorCount=2 for 2-core timing)")
    ap.add_argument("--affinity", help="comma list of hex CPU masks; worker slot i pins its JVM to "
                    "mask i mod n (Windows; e.g. 3,C,30,C0 for four 2-core slots)")
    ap.add_argument("--force", action="store_true", help="re-run finished trials")
    ap.add_argument("--report-only", action="store_true", help="rebuild report.json/.md from --out")
    args = ap.parse_args()
    # The report prints card names and en dashes; a Windows console's code
    # page cannot always encode them (compile_baseline.py does the same).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
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
                found = load_steps(Path(args.steps), sid) if arm.get("steps") else None
                if arm.get("steps") and found is None:
                    print(f"{sid}: warning: arm {arm_name} has no step file; it runs without steps")
                if found:
                    sp_, steps = found
                    plans = merge_steps(plans, steps, out, sid)
                    body = steps["lines"][0]["steps"]
                    ot = steps.get("outlet_step")
                    scen_meta[sid].setdefault("steps", {})[arm_name] = {
                        "path": str(sp_.resolve()), "sha256": sha256(sp_), "deck": steps["deck"],
                        "state_step": steps.get("state_step"), "outlet_step": ot,
                        "outlet_op": body[ot].get("op", "activate") if ot is not None else None}
                scen_meta[sid].setdefault("plans", {})[arm_name] = {"path": str(plans), "sha256": sha256(plans)}
            arm_jar = Path(arm.get("jar", jar)).resolve()
            for k in range(args.trials):
                seed = args.seed + k
                jl = out / sid / arm_name / f"trial_{k}.jsonl"
                jobs.append({"label": f"{sid} {arm_name} {k}", "out": jl, "seed": seed, "force": args.force,
                             "state": out / sid / f"trial_{k}.state",
                             "plans_sha": sha256(plans) if plans is not None else None,
                             "affinity": [m.strip() for m in args.affinity.split(",")] if args.affinity else None,
                             "cmd": trial_cmd(arm_jar, decks, sc, pilots, plans, out / sid / f"trial_{k}.state",
                                              seed, jl, args.timeout, args.horizon, args.xmx,
                                              args.jvm_arg)})
    run = {"cli": sys.argv, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "repo_commit": repo_commit(),
           "jar": str(jar), "jar_name": jar.name, "jar_sha256": sha256(jar), "forge_jar": str(FORGE_JAR),
           "arms": arm_names, "arm_defs": {a: arms[a] for a in arm_names}, "trials": args.trials,
           "seed": args.seed, "timeout": args.timeout, "horizon": args.horizon, "parallel": args.parallel,
           "scenarios": scen_meta}
    # run.json's top-level fields describe this invocation only; every
    # earlier invocation into the same --out is kept under "invocations", so
    # a directory topped up later (a supplement, a re-run of stale trials)
    # still says what ran first.
    history = previous_invocations(out / "run.json")
    run["invocations"] = history
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    t0 = time.time()
    print(f"{len(jobs)} trials, {args.parallel} at a time", flush=True)
    cached = 0
    with ThreadPoolExecutor(max_workers=args.parallel, thread_name_prefix="slot") as ex:
        for r in ex.map(run_cell, jobs):
            cached += r.endswith(" cached")
            print(r, flush=True)
    wall = time.time() - t0
    print(f"wall {wall:.0f}s", flush=True)
    # This invocation's wall clock: the whole run only when nothing was cached.
    run.update({"wall_s": round(wall, 1), "trials_run": len(jobs) - cached, "trials_cached": cached,
                "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    run["invocations"] = history + [invocation_record(run)]
    (out / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    write_report(out)
    print((out / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
