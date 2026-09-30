#!/usr/bin/env python3
"""G1 reading, committed with PREREG.md before any gate game ran.

    py studies/e1_executor/read_g1.py                      # the reading and the verdict
    py studies/e1_executor/read_g1.py --json OUT.json --md OUT.md
    py studies/e1_executor/read_g1.py --dev --outcome D --c1 D --timing D
        # exercise the reader on other runs (the builder's dev runs): no
        # provenance checks, and the verdict it prints is not G1's

Reads the three phase directories run_g1.py writes ($G1_OUT/outcome, c1,
timing): the scenario runner's report is rebuilt from the raw shim JSONL
(run_scenarios.write_report), then each trial's raw records are read again for
what the report does not carry (the strict state-then-outlet order and turn,
escaped exceptions, abort reasons). Every threshold below is quoted from
PREREG.md; changing one after the run is a protocol violation and must be
reported as such. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_g1 as G  # noqa: E402  (paths, seeds, hashes: one definition)
sys.path.insert(0, str(G.RUNNER.parent))
import run_scenarios as rs  # noqa: E402

# PREREG thresholds
PASS_EXEC = 16          # exec G1 success >= 16/20
STOCK_MAX = 2           # stock kills <= 2/20
N_PASS = 3              # at least 3 scenarios pass, S1 or S2 among them
C1_MARGIN = 3           # exec C1 successes not lower than stock's by more than 3
C1_AGREE_MIN = 14       # stock's agreement with the source games >= 14/20
MEDIAN_MAX_MS = 2000.0  # pooled 2-core median decision time
JAVA_MAX = 400          # added + removed Java lines
NOGO_COUNT = 5          # N-a and N-c: at least 5 of 20 exec trials of one scenario
LOW = 6                 # N-d: exec G1 success <= 6/20 ...
LOW_N = 3               # ... on at least 3 of the 5
SUB_CHOOSER = ("not-played", "exception")
TRIGGER = ("s1_kiki_conscripts", "s2_derevi_emiel_cradle")
ACTIVATION = ("s3_druid_reconfiguration", "s4_magda_clock_torque", "s6_scepter_reversal")


# --- one trial -------------------------------------------------------------------

def records(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def exec_stream(recs: list[dict]) -> list[dict]:
    """StepRunner records in log order, with their index in the JSONL."""
    out = []
    for i, r in enumerate(recs):
        if r.get("rec") != "agent" or not str(r.get("event", "")).startswith("exec_"):
            continue
        m = rs.EXEC_DETAIL.match(r.get("detail", ""))
        if not m:
            continue
        rest = m.group(7)
        why = re.search(r"\bwhy=(\S+)", rest)
        op = re.search(r"\bop=(\S+)", rest)
        out.append({"i": i, "turn": r.get("turn"), "event": r["event"], "step": int(m.group(2)),
                    "ms": float(m.group(5)), "why": why.group(1) if why else None,
                    "op": op.group(1) if op else None,
                    "reason": rest.split("why=", 1)[-1] if r["event"] == "exec_abort" else None})
    return out


def attacked_on(recs: list[dict], line_player: str | None, pieces: set, s_turn: int) -> bool:
    """The line seat declared attackers on the scenario turn after the line
    began: a COMBAT "<seat> assigned ... to attack" entry whose seq follows
    the seat's first activation or cast of a line piece that turn (agent
    records carry no seq, so Forge's own entries order the two; a line whose
    actions never used the stack is ordered by the turn alone). The first
    TURN entry is the scenario turn, as parse_trial counts."""
    if not line_player:
        return False
    seat = rs.SEAT.match(line_player)
    turn, first_line, attacks = None, None, []
    for r in recs:
        if r.get("rec") != "entry":
            continue
        if r.get("type") == "TURN":
            m = rs.TURN.match(r.get("message", ""))
            if m:
                turn = s_turn if turn is None else int(m.group(1))
            continue
        if turn != s_turn:
            continue
        msg, seq = r.get("message", ""), int(r.get("seq", -1))
        if r.get("type") == "STACK_ADD" and r.get("card") in pieces and first_line is None:
            m = rs.STACK_VERB.match(msg)
            if m and seat and m.group(1) == seat.group(1) and m.group(2) in ("activated", "cast"):
                first_line = seq
        elif r.get("type") == "COMBAT" and msg.startswith(line_player + " assigned") and " to attack " in msg:
            attacks.append(seq)
    return any(first_line is None or s > first_line for s in attacks)


def strict_state_outlet(recs: list[dict], ex: list[dict], meta: dict | None, s_turn: int,
                        line_player: str | None, pieces: set) -> tuple[bool, bool]:
    """(state reached, state then outlet), both on the scenario turn and in
    order (PREREG, "The stated infinite state followed by the outlet")."""
    if not meta or meta.get("state_step") is None or meta.get("outlet_step") is None:
        return False, False
    st, ot = meta["state_step"], meta["outlet_step"]
    state = next((e for e in ex if e["event"] == "exec_stop" and e["step"] == st and e["op"] != "confirm"
                  and e["why"] in rs.STOP_PREDICATES and e["turn"] == s_turn), None)
    if state is None:
        return False, False
    later = [e for e in ex if e["i"] > state["i"] and e["turn"] == s_turn and e["step"] == ot]
    if meta.get("outlet_op") == "pass":
        hand = next((e for e in later if e["event"] == "exec_stop" and e["why"] == "handoff"), None)
        return True, bool(hand and attacked_on(recs, line_player, pieces, s_turn))
    return True, any(e["event"] == "exec_step" and e["op"] in ("activate", "cast") for e in later)


def unhandled_reasons(t: dict, err: str) -> list[str]:
    why = []
    if t.get("rc") not in (None, 0):
        why.append(f"exit {t['rc']}")
    if "shim: fatal" in err:
        why.append("shim: fatal")
    if t.get("error"):
        why.append(f"result error {t['error']}")
    if t.get("ran") and not t.get("has_result"):
        why.append("no result record")
    if "Exception in thread" in err:
        why.append("Exception in thread")
    return why


def trial_row(out: Path, sid: str, arm: str, k: int, t: dict, sc: dict, ex_meta: dict | None) -> dict:
    path = out / sid / arm / f"trial_{k}.jsonl"
    err_p = path.with_suffix(".err")
    err = err_p.read_text(encoding="utf-8", errors="replace") if err_p.exists() else ""
    recs = records(path)
    ex = exec_stream(recs)
    s_turn = int(sc.get("turn", 1))
    players = t.get("players") or []
    lseat = t.get("line_seat")
    lp = players[lseat] if lseat is not None and lseat < len(players) else None
    state, so = strict_state_outlet(recs, ex, ex_meta, s_turn, lp, set((sc.get("line") or {}).get("pieces", [])))
    kill = bool(t.get("success"))
    aborts = [e["reason"] for e in ex if e["event"] == "exec_abort"]
    row = {
        "trial": k, "seed": None, "ran": bool(t.get("ran")), "finished": bool(t.get("has_result")),
        "line_loaded": bool(t.get("line_loaded")), "kill": kill,
        "kill_on_scenario_turn": bool(t.get("kill_on_scenario_turn")), "turns": t.get("turns"),
        "winner_seat": t.get("winner_seat"), "timed_out": bool(t.get("timedOut")),
        "state_strict": state, "so_strict": so,
        "so_harness": bool((t.get("exec") or {}).get("state_then_outlet")),
        "exec_records": len(ex), "armed": sum(e["event"] == "exec_arm" for e in ex),
        "binds": sum(e["event"] == "exec_step" and e["op"] == "bind" for e in ex),
        "actions": sum(e["event"] == "exec_step" and e["op"] in ("activate", "cast") for e in ex),
        "stops": dict(Counter(e["why"] for e in ex if e["event"] == "exec_stop" and e["op"] != "confirm")),
        "aborts": aborts,
        "sub_chooser": any(a.startswith(SUB_CHOOSER) for a in aborts),
        "budget_stop": any(e["event"] == "exec_stop" and e["why"] == "budget" for e in ex),
        "decision_ms": [e["ms"] for e in ex],
        "unhandled": unhandled_reasons(t, err), "printed_exceptions": t.get("exceptions", 0),
        "game_s": round(t["ms"] / 1000, 1) if t.get("ms") else None,
        "iterations_scenario_turn": t.get("iterations_scenario_turn"),
        "shim_commit": t.get("shim_commit"),
    }
    cell = path.with_suffix(".cell.json")
    if cell.exists():
        c = json.loads(cell.read_text(encoding="utf-8"))
        row.update({"seed": c.get("seed"), "affinity": c.get("affinity"), "started": c.get("started"),
                    "jvm_args": [a for a in c.get("cmd", []) if a.startswith("-XX:")], "wall_s": c.get("wall_s")})
    return row


def read_phase(out: Path, rebuild: bool = True) -> dict:
    """{sid: {arm: [row per trial]}} plus the run record."""
    report = rs.write_report(out) if rebuild else json.loads((out / "report.json").read_text(encoding="utf-8"))
    run = report["run"]
    rows = {}
    for sid, s in report["scenarios"].items():
        sc = rs.writer.load(run["scenarios"][sid]["path"])
        rows[sid] = {}
        for arm, a in s["arms"].items():
            ex_meta = (run["scenarios"][sid].get("steps") or {}).get(arm)
            rows[sid][arm] = [trial_row(out, sid, arm, k, t, sc, ex_meta) for k, t in enumerate(a["trials"])]
    return {"run": run, "rows": rows, "report": report}


# --- aggregates --------------------------------------------------------------------

def pct(xs: list[float], q: float):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def ms_summary(ms: list[float]) -> dict:
    return {"decisions": len(ms), "median": round(statistics.median(ms), 3) if ms else None,
            "p95": pct(ms, 0.95), "max": max(ms) if ms else None}


def success_of(r: dict, arm: str, reading: str) -> bool:
    """G1 success of a trial. Stock: a kill. Exec: a kill, or (primary) the
    strict state then outlet, or (harness) the harness's looser column. A
    trial that did not finish, whose line did not load or whose game timed
    out is a failure (PREREG)."""
    if not (r["finished"] and r["line_loaded"]) or r["timed_out"]:
        return False
    if arm != "exec" or reading == "kills":
        return r["kill"]
    return r["kill"] or (r["so_strict"] if reading == "primary" else r["so_harness"])


def scenario_table(outcome: dict, reading: str) -> dict:
    tab = {}
    for sid in G.SCENARIOS:
        arms = outcome["rows"].get(sid, {})
        st, ex = arms.get("stock", []), arms.get("exec", [])
        n_st, n_ex = G.PHASES["outcome"]["trials"], G.PHASES["outcome"]["trials"]
        k_st = sum(success_of(r, "stock", reading) for r in st)
        k_ex = sum(success_of(r, "exec", reading) for r in ex)
        tab[sid] = {"stock": k_st, "stock_n": n_st, "stock_ci": rs.wilson(k_st, n_st),
                    "exec": k_ex, "exec_n": n_ex, "exec_ci": rs.wilson(k_ex, n_ex),
                    "passes": k_ex >= PASS_EXEC and k_st <= STOCK_MAX}
    return tab


def c1_reading(c1: dict) -> dict:
    src = {c["id"]: c for c in json.loads((G.SUITE / "c1" / "sources.json").read_text(encoding="utf-8"))["chosen"]}
    arms = {}
    boards = {}
    for sid, by_arm in sorted(c1["rows"].items()):
        g = src.get(sid, {})
        boards[sid] = {"turn": g.get("turn"), "game_within_8": g.get("won_within_horizon")}
        for arm, trs in by_arm.items():
            r = trs[0]
            a = arms.setdefault(arm, Counter())
            a["boards"] += 1
            a["finished"] += r["finished"]
            a["line_loaded"] += r["line_loaded"] and r["finished"]
            a["success"] += r["kill"]
            a["on_turn"] += r["kill_on_scenario_turn"]
            a["agree"] += r["kill"] == bool(g.get("won_within_horizon"))
            a["exec_records"] += r["exec_records"]
            a["unhandled"] += bool(r["unhandled"])
            a["printed_exceptions"] += r["printed_exceptions"]
            boards[sid][arm] = {"success": r["kill"], "turns": r["turns"], "on_turn": r["kill_on_scenario_turn"]}
    st, ex = arms.get("stock", Counter()), arms.get("exec", Counter())
    cond = {
        "a_margin": ex["success"] >= st["success"] - C1_MARGIN,
        "b_exec_loaded_finished": ex["finished"] == 20 and ex["line_loaded"] == 20,
        "c_no_exec_records": ex["exec_records"] == 0,
        "d_stock_agreement": st["agree"] >= C1_AGREE_MIN,
    }
    return {"arms": {a: dict(v) for a, v in arms.items()}, "boards": boards, "conditions": cond,
            "not_broken": all(cond.values())}


def timing_reading(tm: dict) -> dict:
    per, pooled = {}, []
    for sid in G.SCENARIOS:
        rows = tm["rows"].get(sid, {}).get("exec", [])
        ms = [m for r in rows for m in r["decision_ms"]]
        pooled += ms
        per[sid] = dict(ms_summary(ms), trials=len(rows),
                        success_primary=sum(success_of(r, "exec", "primary") for r in rows),
                        kills=sum(r["kill"] for r in rows),
                        game_s=[r["game_s"] for r in rows],
                        timed_out=sum(r["timed_out"] for r in rows),
                        unhandled=sum(bool(r["unhandled"]) for r in rows),
                        printed_exceptions=sum(r["printed_exceptions"] for r in rows),
                        pinned=sum(bool(r.get("affinity")) and G.ACTIVE_CPUS in (r.get("jvm_args") or [])
                                   for r in rows))
    return {"per_scenario": per, "pooled": ms_summary(pooled)}


def java_reading() -> dict:
    r = subprocess.run(["git", "-C", str(G.SHIM_REPO), "diff", "--numstat", f"{G.SHIM_BASE}..{G.SHIM_TIP}",
                        "--", "*.java"], capture_output=True, text=True)
    files, add, rem = {}, 0, 0
    for line in r.stdout.splitlines():
        a, d, f = line.split("\t")
        files[f] = [int(a), int(d)]
        add += int(a)
        rem += int(d)
    head = subprocess.run(["git", "-C", str(G.SHIM_WT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(G.SHIM_WT), "status", "--porcelain", "--", "src", "tools"],
                           capture_output=True, text=True).stdout.strip()
    lint_ok, lint_out = False, "not run: the lint worktree is not at the tip or is dirty"
    if head == G.SHIM_TIP and not dirty:
        lr = subprocess.run([sys.executable, "tools/lint_card_names.py", "--cardsfolder", str(G.CARDSFOLDER)],
                            cwd=str(G.SHIM_WT), capture_output=True, text=True)
        lint_ok, lint_out = lr.returncode == 0, (lr.stdout + lr.stderr).strip()
    return {"numstat_ok": r.returncode == 0 and bool(files), "files": files, "added": add, "removed": rem,
            "strict": add + rem, "lint_ok": lint_ok, "lint": lint_out,
            "passes": r.returncode == 0 and bool(files) and add + rem <= JAVA_MAX and lint_ok}


# --- provenance ---------------------------------------------------------------------

def provenance(phases: dict) -> list[str]:
    bad = []
    prereg = G.git("log", "-1", "--format=%H %cI", "--", "studies/e1_executor/PREREG.md").stdout.split()
    if len(prereg) != 2:
        return ["PREREG.md has no commit"]
    pre_sha, pre_time = prereg
    pre_local = pre_time[:19]
    for name, ph in phases.items():
        run, want = ph["run"], G.PHASES[name]
        for inv in run.get("invocations", []) + [run]:
            if inv.get("jar_sha256") != G.JAR_SHA:
                bad.append(f"{name}: an invocation ran jar {str(inv.get('jar_sha256'))[:12]}")
            if inv.get("seed") != want["seed"] or inv.get("trials") != want["trials"]:
                bad.append(f"{name}: an invocation ran seed {inv.get('seed')} x {inv.get('trials')}")
            rc = str(inv.get("repo_commit") or "")
            if rc.endswith("-dirty") or G.git("merge-base", "--is-ancestor", pre_sha, rc).returncode != 0:
                bad.append(f"{name}: an invocation ran at repo {rc}, not a clean descendant of the PREREG commit")
        if run.get("arms") != want["arms"].split(","):
            bad.append(f"{name}: arms {run.get('arms')}")
        want_sids = [p.stem for p in G.scenario_files(name)]
        if sorted(run["scenarios"]) != sorted(want_sids):
            bad.append(f"{name}: scenarios differ from the PREREG's")
        for sid, meta in run["scenarios"].items():
            key = "c1" if name == "c1" else sid
            for arm, p in (meta.get("plans") or {}).items():
                if p["sha256"] != G.PLANS_SHA[key]:
                    bad.append(f"{name} {sid} {arm}: plans {p['sha256'][:12]}")
            for arm, s in (meta.get("steps") or {}).items():
                if s["sha256"] != G.STEP_SHA.get(sid):
                    bad.append(f"{name} {sid} {arm}: step file {s['sha256'][:12]}")
            if name != "c1" and "exec" in run["arms"] and "exec" not in (meta.get("steps") or {}):
                bad.append(f"{name} {sid}: the exec arm ran without its step file")
        for sid, by_arm in ph["rows"].items():
            for arm, rows in by_arm.items():
                for r in rows:
                    if not r["ran"]:
                        continue
                    if arm != "plan017" and r["shim_commit"] != G.JAR_COMMIT:
                        bad.append(f"{name} {sid} {arm} {r['trial']}: shim commit {r['shim_commit']}")
                    want_seed = want["seed"] + r["trial"]
                    if r.get("seed") != want_seed:
                        bad.append(f"{name} {sid} {arm} {r['trial']}: seed {r.get('seed')} != {want_seed}")
                    if r.get("started") and r["started"] <= pre_local:
                        bad.append(f"{name} {sid} {arm} {r['trial']}: started {r['started']} before the PREREG commit")
                    if name == "timing" and not (r.get("affinity") and G.ACTIVE_CPUS in (r.get("jvm_args") or [])):
                        bad.append(f"timing {sid} {r['trial']}: not pinned")
    return bad


def missing(phases: dict) -> list[str]:
    out = []
    for name, ph in phases.items():
        for sid, by_arm in ph["rows"].items():
            for arm, rows in by_arm.items():
                out += [f"{name} {sid} {arm} {r['trial']}" for r in rows if not r["ran"]]
    return out


# --- the verdict ---------------------------------------------------------------------

def verdict(outcome: dict, c1: dict, tm: dict, java: dict, reading: str) -> dict:
    tab = scenario_table(outcome, reading)
    passing = [s for s in G.SCENARIOS if tab[s]["passes"]]
    gate_rows = [r for ph in (outcome, tm) for by_arm in ph["rows"].values() for rows in by_arm.values()
                 for r in rows]
    gate_rows += [r for by_arm in c1["rows"].values() for arm, rows in by_arm.items() if arm != "plan017"
                  for r in rows]
    exec_rows = [r for ph in (outcome, tm) for by_arm in ph["rows"].values() for r in by_arm.get("exec", [])]
    exec_rows += [r for by_arm in c1["rows"].values() for r in by_arm.get("exec", [])]
    c1r = c1_reading(c1)
    tmr = timing_reading(tm)
    med = tmr["pooled"]["median"]
    ex_out = {s: outcome["rows"].get(s, {}).get("exec", []) for s in G.SCENARIOS}
    sub = {s: sum(r["sub_chooser"] for r in ex_out[s]) for s in G.SCENARIOS}
    over = {s: sum(r["budget_stop"] or r["timed_out"] for r in ex_out[s]) for s in G.SCENARIOS}
    low = [s for s in G.SCENARIOS if tab[s]["exec"] <= LOW]
    unhandled_all = sum(bool(r["unhandled"]) for r in gate_rows)
    unhandled_exec = sum(bool(r["unhandled"]) for r in exec_rows)
    go = {
        "G-a scenarios": len(passing) >= N_PASS and any(s in passing for s in TRIGGER),
        "G-b C1 not broken": c1r["not_broken"],
        "G-c 0 unhandled": unhandled_all == 0,
        "G-d 2-core median <= 2 s": med is not None and med <= MEDIAN_MAX_MS,
        "G-e Java diff and lint": java["passes"],
    }
    nogo = {
        "N-a sub-chooser": any(v >= NOGO_COUNT for v in sub.values()),
        "N-b crash": unhandled_exec >= 1,
        "N-c time budget": (med is not None and med > MEDIAN_MAX_MS) or any(v >= NOGO_COUNT for v in over.values()),
        "N-d most <= 6/20": len(low) >= LOW_N,
    }
    partial = (all(tab[s]["passes"] for s in ACTIVATION) and not any(tab[s]["passes"] for s in TRIGGER)
               and go["G-b C1 not broken"] and go["G-c 0 unhandled"] and go["G-d 2-core median <= 2 s"]
               and go["G-e Java diff and lint"])
    if any(nogo.values()):
        v = "NO-GO"
    elif all(go.values()):
        v = "GO"
    elif partial:
        v = "PARTIAL"
    else:
        v = "UNDECIDED"
    return {"reading": reading, "verdict": v, "go": go, "nogo": nogo, "partial": partial, "passing": passing,
            "table": tab, "sub_chooser": sub, "budget_or_timeout": over, "low": low,
            "unhandled_gate": unhandled_all, "unhandled_exec": unhandled_exec, "median_ms": med}


# --- markdown -------------------------------------------------------------------------

def ci(c) -> str:
    return "–" if not c else f"{c[0]:.2f}-{c[1]:.2f}"


def f(v) -> str:
    return "–" if v is None else str(v)


def counts(d: dict) -> str:
    return "; ".join(f"{k} x{v}" for k, v in sorted(d.items(), key=str)) or "–"


def markdown(res: dict) -> str:
    v, outcome, c1r, tmr, java = res["verdict"], res["outcome"], res["c1"], res["timing"], res["java"]
    L = [f"# G1 reading", "", f"**Verdict (primary reading): {v['verdict']}**" +
         ("" if not res["provenance"] else " (provenance problems below: not a valid G1 reading)"), ""]
    L += ["| Condition | Holds |", "|---|---|"]
    L += [f"| {k} | {'yes' if x else 'no'} |" for k, x in v["go"].items()]
    L += [f"| {k} | {'yes' if x else 'no'} |" for k, x in v["nogo"].items()]
    L += [f"| PARTIAL (S3, S4, S6 pass; S1, S2 do not; G-b to G-e) | {'yes' if v['partial'] else 'no'} |", ""]
    L += ["| Scenario | Stock kills | 95% CI | Exec G1 success | 95% CI | Exec kills | Exec state then outlet (strict) "
          "| Harness column | Passes |", "|---|---|---|---|---|---|---|---|---|"]
    for sid in G.SCENARIOS:
        t = v["table"][sid]
        ex = outcome.get(sid, {}).get("exec", {})
        L.append(f"| {G.LABEL[sid]} {sid} | {t['stock']}/{t['stock_n']} | {ci(t['stock_ci'])} | {t['exec']}/{t['exec_n']} "
                 f"| {ci(t['exec_ci'])} | {ex.get('kills', '–')}/20 | {ex.get('so_strict', '–')}/20 "
                 f"| {ex.get('so_harness', '–')}/20 | {'yes' if t['passes'] else 'no'} |")
    L += ["", "| Scenario | Armed | Binds | Actions (mean) | Stops | Aborts | Sub-chooser aborts | Budget stops or timeouts "
          "| Decisions | ms median / p95 / max | Game s mean / max | Line loaded (stock; exec) "
          "| Unhandled / printed exceptions (stock; exec) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sid in G.SCENARIOS:
        ex, st = outcome.get(sid, {}).get("exec", {}), outcome.get(sid, {}).get("stock", {})
        if not ex:
            continue
        L.append(f"| {G.LABEL[sid]} | {ex['armed']}/20 | {ex['binds']} | {f(ex['actions_mean'])} | {counts(ex['stops'])} "
                 f"| {counts(ex['aborts'])} | {ex['sub_chooser']} | {ex['budget_or_timeout']} | {ex['ms']['decisions']} "
                 f"| {f(ex['ms']['median'])} / {f(ex['ms']['p95'])} / {f(ex['ms']['max'])} | {f(ex['game_s_mean'])} / "
                 f"{f(ex['game_s_max'])} | {st.get('line_loaded', '–')}; {ex['line_loaded']} "
                 f"| {st.get('unhandled', '–')} / {st.get('printed_exceptions', '–')}; {ex['unhandled']} / "
                 f"{ex['printed_exceptions']} |")
    L += ["", "C1 (20 boards, one trial each):", "",
          "| Arm | Finished | Line loaded | Won within 8 turns | On the scenario turn | Agreement with the source game "
          "| Executor records | Unhandled / printed exceptions |", "|---|---|---|---|---|---|---|---|"]
    for arm, a in c1r["arms"].items():
        L.append(f"| {arm} | {a.get('finished', 0)} | {a.get('line_loaded', 0)} | {a.get('success', 0)}/20 "
                 f"| {a.get('on_turn', 0)}/20 | {a.get('agree', 0)}/20 | {a.get('exec_records', 0)} "
                 f"| {a.get('unhandled', 0)} / {a.get('printed_exceptions', 0)} |")
    L += ["", "C1 conditions: " + "; ".join(f"{k} {'yes' if x else 'no'}" for k, x in c1r["conditions"].items()), ""]
    L += ["| Board | Turn | Game won within 8 | " + " | ".join(c1r["arms"]) + " |",
          "|---|---|---|" + "---|" * len(c1r["arms"])]
    for sid, b in c1r["boards"].items():
        cells = [("yes" if b[a]["success"] else "no") + (f" (turn {b[a]['turns']})" if b[a]["success"] else "")
                 for a in c1r["arms"] if a in b]
        L.append(f"| {sid} | {b['turn']} | {'yes' if b['game_within_8'] else 'no'} | " + " | ".join(cells) + " |")
    L += ["", "Timing (exec, each JVM on 2 logical CPUs, ActiveProcessorCount=2):", "",
          "| Scenario | Trials (pinned) | G1 success | Kills | Decisions | ms median / p95 / max | Game s min-max "
          "| Timed out | Unhandled / printed exceptions |", "|---|---|---|---|---|---|---|---|---|"]
    for sid, p in tmr["per_scenario"].items():
        gs = [g for g in p["game_s"] if g is not None]
        L.append(f"| {G.LABEL[sid]} | {p['trials']} ({p['pinned']}) | {p['success_primary']} | {p['kills']} "
                 f"| {p['decisions']} | {f(p['median'])} / {f(p['p95'])} / {f(p['max'])} "
                 f"| {f(min(gs)) if gs else '–'}-{f(max(gs)) if gs else '–'} | {p['timed_out']} "
                 f"| {p['unhandled']} / {p['printed_exceptions']} |")
    pl = tmr["pooled"]
    L += ["", f"Pooled: {pl['decisions']} decisions, median {f(pl['median'])} ms, p95 {f(pl['p95'])}, max {f(pl['max'])}.",
          "", f"Java diff {G.SHIM_BASE[:7]}..{G.SHIM_TIP[:7]}: {java['added']} added, {java['removed']} removed, "
          f"strict {java['strict']} (limit {JAVA_MAX}); lint {'ok' if java['lint_ok'] else 'FAILED'}: {java['lint']}", ""]
    L += ["Sensitivity (same rules, other exec success definitions):", ""]
    for s in res["sensitivity"]:
        L.append(f"- {s['reading']}: {s['verdict']}; passing {', '.join(G.LABEL[x] for x in s['passing']) or 'none'}")
    if res["provenance"]:
        L += ["", "Provenance problems:"] + [f"- {p}" for p in res["provenance"][:40]]
    if res["missing"]:
        L += ["", f"Missing trials ({len(res['missing'])}): " + ", ".join(res["missing"][:20])]
    for name, ld in res["load"].items():
        L.append(f"Load during {name}: {ld}")
    return "\n".join(L) + "\n"


def arm_summary(rows: list[dict]) -> dict:
    ms = [m for r in rows for m in r["decision_ms"]]
    gs = [r["game_s"] for r in rows if r["game_s"] is not None]
    stops, aborts = Counter(), Counter()
    for r in rows:
        stops.update(r["stops"])
        aborts.update(" ".join(a.split()[:2]) for a in r["aborts"])
    return {"trials": len(rows), "kills": sum(r["kill"] for r in rows), "so_strict": sum(r["so_strict"] for r in rows),
            "state_strict": sum(r["state_strict"] for r in rows), "so_harness": sum(r["so_harness"] for r in rows),
            "armed": sum(r["armed"] > 0 for r in rows), "binds": sum(r["binds"] for r in rows),
            "actions_mean": round(sum(r["actions"] for r in rows) / len(rows), 1) if rows else None,
            "stops": dict(stops), "aborts": dict(aborts), "sub_chooser": sum(r["sub_chooser"] for r in rows),
            "budget_or_timeout": sum(r["budget_stop"] or r["timed_out"] for r in rows),
            "timed_out": sum(r["timed_out"] for r in rows), "ms": ms_summary(ms),
            "game_s_mean": round(sum(gs) / len(gs), 1) if gs else None, "game_s_max": max(gs) if gs else None,
            "line_loaded": sum(r["line_loaded"] for r in rows), "finished": sum(r["finished"] for r in rows),
            "unhandled": sum(bool(r["unhandled"]) for r in rows),
            "unhandled_reasons": sorted({w for r in rows for w in r["unhandled"]}),
            "printed_exceptions": sum(r["printed_exceptions"] for r in rows),
            "iterations_scenario_turn_mean": round(sum(r["iterations_scenario_turn"] or 0 for r in rows) / len(rows), 1)
            if rows else None}


def load_summary(path: Path) -> str:
    if not path.exists():
        return "no load log"
    xs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    java = [x["java"] for x in xs]
    cpu = [x["cpu"] for x in xs if x.get("cpu") is not None]
    return (f"{len(xs)} samples; Java processes on the box median {statistics.median(java) if java else '–'}, "
            f"max {max(java) if java else '–'}; CPU load mean {round(sum(cpu) / len(cpu)) if cpu else '–'}%, "
            f"max {max(cpu) if cpu else '–'}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outcome", default=str(G.OUT / "outcome"))
    ap.add_argument("--c1", default=str(G.OUT / "c1"))
    ap.add_argument("--timing", default=str(G.OUT / "timing"))
    ap.add_argument("--dev", action="store_true", help="other runs: skip provenance; not a G1 verdict")
    ap.add_argument("--no-rebuild", action="store_true", help="read report.json as it is")
    ap.add_argument("--json")
    ap.add_argument("--md")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    phases = {n: read_phase(Path(getattr(args, n)), not args.no_rebuild) for n in ("outcome", "c1", "timing")}
    java = java_reading()
    readings = [verdict(phases["outcome"], phases["c1"], phases["timing"], java, r)
                for r in ("primary", "kills", "harness")]
    prov = [] if args.dev else provenance(phases)
    miss = missing(phases)
    primary = readings[0]
    if prov or miss:
        primary = dict(primary, verdict="UNDECIDED", why="provenance problems or missing trials")
    res = {
        "verdict": primary,
        "sensitivity": [{"reading": r["reading"], "verdict": r["verdict"], "passing": r["passing"]} for r in readings[1:]],
        "outcome": {sid: {arm: arm_summary(rows) for arm, rows in by_arm.items()}
                    for sid, by_arm in phases["outcome"]["rows"].items()},
        "c1": c1_reading(phases["c1"]),
        "timing": timing_reading(phases["timing"]),
        "java": java,
        "provenance": prov,
        "missing": miss,
        "dev": args.dev,
        "load": {n: load_summary(Path(getattr(args, n)).parent / f"{n}.load.jsonl") for n in phases},
        "runs": {n: dict({k: ph["run"].get(k) for k in ("started", "finished", "repo_commit", "jar_sha256", "seed",
                                                        "trials", "parallel", "wall_s", "trials_run", "trials_cached")},
                         invocations=len(ph["run"].get("invocations", []))) for n, ph in phases.items()},
        "trials": {n: ph["rows"] for n, ph in phases.items()},
    }
    md = markdown(res)
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
