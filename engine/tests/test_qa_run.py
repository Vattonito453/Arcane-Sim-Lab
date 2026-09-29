#!/usr/bin/env python3
"""QA layer A: engine/qa/run.py and the review queue (engine/qa/review_queue.py).

Repair plan WS2 layer A (tasks/25-repair-plan.md): every finished run gets
$MTG_DATA_DIR/simkb/runs/<stem>/qa.json, written atomically and last; each
detector has its own time budget; detector errors go into qa.json's errors
and never crash the CLI, whatever state the run is in; flags above a
severity threshold are filed in review_queue/auto/, at most 30 per run,
stratified by detector. These checks pin:

  * the committed 2-game fixture (stdout path): schema, basis, the board
    accuracy CLAUDE.md quotes for it (83.3% exit match), knockouts and method
    per game, the swing held on stdout, tutors null (not measurable), pilot;
  * a synthetic shim run: the shim's reach=false becomes a tutor.unreachable
    flag with the plan's anchor shape, severity, trust and id, and is queued;
    the swing is exactly game_story's;
  * the errors path: a detector that raises, one that overruns its budget, a
    spent global budget, a truncated (killed) result, a JSON file that is not
    a result, a salvaged partial run; qa.json is still written each time;
  * the CLI: exit codes, a missing result, --all (counts, skip current,
    --force), idempotency (same ids, no duplicate queue items, attempts);
  * the review queue: threshold, the 30 cap across re-runs and done/,
    round-robin stratification, no note fields, the reader's ordering,
    cursor, settle window and paging;
  * public(): the API's switches applied to the swing, human notes dropped.

A throwaway MTG_DATA_DIR; no network, no JVM, no Forge.

Run: py engine/tests/test_qa_run.py   -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="simlab_qa_run_"))
os.environ["MTG_DATA_DIR"] = str(_TMP)
os.environ.pop("MTG_QA_QUEUE_MIN_SEVERITY", None)
for k in ("MTG_TURNING_POINT", "MTG_KNOCKOUT_DETAIL"):
    os.environ.pop(k, None)

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import game_story  # noqa: E402
from qa import context as qctx  # noqa: E402
from qa import review_queue as rq  # noqa: E402
from qa import run as qa  # noqa: E402

RESULTS = _TMP / "sim_results"
RESULTS.mkdir(parents=True)
FIXTURE = "sim_20260724_093703_fixture.json"
shutil.copy(ENGINE / "tests" / "fixtures" / "sim_sample.json", RESULTS / FIXTURE)

A, B = "Ai(1)-Alpha", "Ai(2)-Beta"
EMPTY_FACTS = qctx.CardFacts({})


def eq(a, b, msg):
    assert a == b, f"{msg}: {a!r} != {b!r}"


def Z(turn, phase, card, cid, frm, to, fp, tp, types="", pt=""):
    return {"turn": turn, "phase": phase, "card": card, "cardId": cid, "from": frm, "to": to,
            "fromPlayer": fp, "toPlayer": tp, "types": types, "pt": pt, "token": False}


def shim_game(winner=A):
    """Alpha casts a creature, casts a tutor the shim says cannot reach its
    piece, and kills Beta in combat."""
    loser = B if winner == A else A
    return {
        "players": [A, B],
        "result": {"winner": winner, "draw": False},
        "zones": [
            Z(1, "MAIN1", "Grizzly Bears", 7, "Hand", "Stack", A, ""),
            Z(1, "MAIN1", "Grizzly Bears", 7, "Stack", "Battlefield", "", A, "Creature", "2/2"),
            Z(3, "MAIN1", "Verdant Call", 9, "Hand", "Stack", A, "", "Sorcery"),
            Z(3, "MAIN1", "Verdant Call", 9, "Stack", "Graveyard", "", A, "Sorcery"),
        ],
        "agent_events": [
            {"turn": 0, "player": A, "event": "mull_keep", "detail": "lands=3 size=7"},
            {"turn": 3, "player": A, "event": "tutor_cast",
             "detail": "reach=false where=Library why=restriction route=spell "
                       "Verdant Call seeking Tide Oracle"},
        ],
        "turns": [
            {"turn": 1, "active_player": A, "events": [
                {"seq": 1, "action": "stack_add", "raw": f"{A} cast Grizzly Bears (7)"}]},
            {"turn": 2, "active_player": B, "events": [
                {"seq": 2, "action": "phase", "raw": f"{B}'s Untap step"}]},
            {"turn": 3, "active_player": A, "events": [
                {"seq": 3, "action": "stack_add", "raw": f"{A} cast Verdant Call (9)"},
                {"seq": 4, "action": "damage",
                 "raw": f"Grizzly Bears (7) deals 40 combat damage to {loser}."},
                {"seq": 5, "action": "life_change", "raw": f"Life: {loser} 40 > 0"},
                {"seq": 6, "action": "game_outcome",
                 "raw": f"{loser} has lost because life total reached 0"}]},
        ],
    }


SHIM = "sim_20260101_000000_aaaaaaaaaaaa_rotated.json"
SHIM_RUN = {
    "meta": {"agent": "simlab-forge-shim/0.17.0", "agents": ["plan", "plan"],
             "decks": ["alpha.dck", "beta.dck"], "games_expected": 1,
             "unsupported_cards": ["Odd Card"],
             "unsupported_by_deck": {"alpha.dck": ["Odd Card"]},
             "commander_fidelity": [
                 {"deck": "alpha.dck", "player": "Alpha", "commanders": ["Alpha Prime"],
                  "refused": [], "basis": "zone_stream", "seen": {"Alpha Prime": 0},
                  "missing": ["Alpha Prime"], "never_cast": ["Alpha Prime"], "games": 1}]},
    "summary": {},
    "games": [shim_game()],
}
(RESULTS / SHIM).write_text(json.dumps(SHIM_RUN), encoding="utf-8")

# A run the time ceiling killed and run_sim salvaged: incomplete, fewer games.
SALVAGED = "sim_20260101_000100_bbbbbbbbbbbb_rotated.json"
salv = copy.deepcopy(SHIM_RUN)
salv["meta"].update(incomplete=True, salvaged_from_kill=True, games_expected=4)
salv["games"].append({"players": [A, B], "result": {}, "turns": []})   # a cut-off game
(RESULTS / SALVAGED).write_text(json.dumps(salv), encoding="utf-8")

TRUNCATED = "sim_20260101_000200_cccccccccccc.json"
(RESULTS / TRUNCATED).write_text(json.dumps(SHIM_RUN)[:500], encoding="utf-8")
NOT_A_RUN = "sim_20260101_000300_dddddddddddd.json"
(RESULTS / NOT_A_RUN).write_text("[1, 2, 3]", encoding="utf-8")


def fixture_run() -> None:
    rc, out = qa.run_one(RESULTS / FIXTURE, _TMP, quiet=True)
    eq(rc, 0, "a clean fixture run exits 0")
    eq(out, _TMP / "simkb" / "runs" / FIXTURE[:-5] / "qa.json", "qa.json path")
    d = json.loads(out.read_text(encoding="utf-8"))
    eq((d["schema"], d["analyzer"], d["run"]), ("simlab.qa/1", qa.ANALYZER, FIXTURE), "header")
    eq((d["status"], d["errors"]), ("complete", []), "no errors on the fixture")
    eq(d["basis"], "stdout", "the fixture is a stock stdout run")
    ba = d["board_accuracy"]
    eq((ba["basis"], ba["exit_match_rate"]), ("stdout", 0.8333),
       "board accuracy is CLAUDE.md's 83.3% for the 2-game fixture")
    eq(len(d["games"]), 2, "both games")
    for g in d["games"]:
        assert isinstance(g["knockouts"], list) and g["knockouts"], g
        eq(g["method"], g["knockouts"][-1]["cause"], "method is the final knockout's cause")
        eq(g["turning_point"], None, "the swing is held on stdout runs")
        for k in g["knockouts"]:
            eq(set(k["anchor"]), {"game", "turn", "player", "agent_event_index", "seq",
                                  "event_seq"}, "knockout anchor shape")
            eq(k["anchor"]["game"], g["n"], "anchor game is 1-based")
    eq(d["pilot"]["id"], "stock", "one pilot derivation: a stdout run is stock Forge")
    eq((d["pilot"]["lines_file"], d["pilot"]["overrides_version"]), (None, None),
       "no lines file and no overrides exist yet: null, not guessed")
    for deck, v in d["decks"].items():
        eq(v["tutors"], None, f"{deck}: tutors are not measurable on stdout, so null not 0")
        eq(v["games"], 2, "each deck played both games")
    for name in ("context", "knockouts", "tutors", "board_accuracy"):
        eq(d["detectors"][name]["status"], "ok", f"{name} ran")
    eq(d["inputs"]["plans_file"], None, "no plans beside a stock run")
    assert "\\" not in json.dumps(d["inputs"]) and str(_TMP) not in json.dumps(d), \
        "no server paths in qa.json (the route is public)"
    eq(d["review_queue"], {"eligible": 0, "written": 0}, "nothing to queue")


def shim_run() -> dict:
    rc, out = qa.run_one(RESULTS / SHIM, _TMP, quiet=True)
    eq(rc, 0, "a clean synthetic shim run exits 0")
    d = json.loads(out.read_text(encoding="utf-8"))
    eq(d["basis"], "shim-zones", "zone stream in every game")
    eq(d["board_accuracy"]["basis"], "shim-zones", "board read from the zones")
    flags = [f for f in d["flags"] if f["detector"] == "tutor.unreachable"]
    eq(len(flags), 1, "the shim's reach=false is flagged")
    f = flags[0]
    eq((f["kind"], f["trust"], f["severity"]), ("rules", "experimental", "high"),
       "rules detector, experimental until judged, high severity")
    eq(f["anchor"], {"game": 1, "turn": 3, "player": A, "agent_event_index": 1, "seq": None,
                     "event_seq": f["anchor"]["event_seq"]}, "the plan's anchor shape")
    eq(f["id"], f"{SHIM[:-5]}#g1a1.tutor.unreachable", "id: run, game, agent event, detector")
    eq((f["deck"], f["card"], f["round"], f["evidence"]), ("Alpha", "Verdant Call", 2, [1]),
       "deck, the tutor, the table round, the agent event as evidence")
    assert "—" not in f["detail"], "no em dash in a flag detail"
    g = d["games"][0]
    eq((g["method"], [k["cause"] for k in g["knockouts"]]), ("combat_damage", ["combat_damage"]),
       "the combat knockout")
    story = game_story.of_game(SHIM_RUN["games"][0], game_story.switches({}))
    eq(g["turning_point"], story["turning_point"], "the swing is exactly game_story's")
    tut = d["decks"]["Alpha"]["tutors"]
    eq((tut["casts"], tut["unreachable"], tut["reach_ok"]), (1, 1, 0), "tutor figures")
    eq(tut["measurable"], {"tutor_casts": True, "tutor_spells": True}, "both families measured")
    assert "plan" in tut["by_pilot"], tut["by_pilot"].keys()
    fid = d["fidelity"]
    eq(fid["unsupported"], [{"deck": "Alpha", "file": "alpha.dck", "card": "Odd Card",
                             "reason": "forge_refused"}], "unsupported cards per deck")
    eq(fid["commander_never_cast"], [{"deck": "Alpha", "commanders": ["Alpha Prime"],
                                      "games": 1}], "commander loaded, never cast")
    eq((fid["commander_missing"], fid["commander_flagged"]), ([], None),
       "nothing refused; flagged is the refusals detector's (week 5): null")
    eq(d["pilot"]["kind"], "plan", "plan pilot")
    q = d["review_queue"]
    eq((q["eligible"], q["written"], q["cap"], q["threshold"]), (1, 1, 30, "medium"), "queued")
    item = json.loads((_TMP / "simkb" / "review_queue" / "auto" / f"{f['id']}.json")
                      .read_text(encoding="utf-8"))
    eq((item["schema"], item["source"], item["run"], item["priority"], item["deck"]),
       ("simlab.review/1", "detector:tutor.unreachable", SHIM, 2, "Alpha"), "queue item")
    assert "note" not in item and "reporter" not in item, "no human fields in an auto item"
    return d


def idempotent(first: dict) -> None:
    rc, out = qa.run_one(RESULTS / SHIM, _TMP, quiet=True)
    eq(rc, 0, "second run")
    d = json.loads(out.read_text(encoding="utf-8"))
    eq([f["id"] for f in d["flags"]], [f["id"] for f in first["flags"]], "same flag ids")
    eq((d["review_queue"]["written"], d["review_queue"]["already_queued"]), (0, 1),
       "a re-run queues nothing twice")
    auto = list((_TMP / "simkb" / "review_queue" / "auto").glob(f"{SHIM[:-5]}#*.json"))
    eq(len(auto), 1, "one queue file")
    strip = lambda x: {k: v for k, v in x.items() if k not in ("generated", "seconds",
                                                                "detectors", "review_queue")}
    eq(strip(d), strip(first), "the same qa.json apart from timing and the queue note")
    eq(qa.read_attempts(SHIM, _TMP)["attempts"], 2, "each attempt counted")
    leftovers = [p for p in (_TMP / "simkb").rglob("*") if p.name.startswith((".qa-", ".tmp-"))]
    eq(leftovers, [], "no temp files left behind")


def errors_path() -> None:
    def boom(ctx):
        raise RuntimeError("detector exploded")

    def slow(ctx):
        time.sleep(5)
        return {}, []

    def junk(ctx):
        return "not a pair"

    from qa import knockouts
    t0 = time.perf_counter()
    d = qa.analyze(RESULTS / SHIM, facts=EMPTY_FACTS, load_forge=False,
                   detectors=[("boom", boom, "rules"), ("slow", slow, "rules"),
                              ("junk", junk, "rules"),
                              ("knockouts", knockouts.detect, knockouts.KIND)],
                   budgets={"slow": 0.5})
    took = time.perf_counter() - t0
    assert took < 4, f"an overrunning detector is abandoned at its budget ({took:.1f} s)"
    by = {e["stage"]: e["error"] for e in d["errors"]}
    assert "RuntimeError: detector exploded" in by["boom"], by
    assert "budget" in by["slow"], by
    assert "bad detector output" in by["junk"], by
    eq((d["detectors"]["boom"]["status"], d["detectors"]["slow"]["status"]),
       ("error", "timeout"), "statuses")
    eq(d["detectors"]["knockouts"]["status"], "ok", "the rest still run")
    assert d["games"][0]["knockouts"], "knockouts still filled"
    eq(d["decks"]["Alpha"]["tutors"], None, "no tutors detector ran: null, never zeros")

    # A spent global budget: later stages are skipped, not run over time.
    d = qa.analyze(RESULTS / SHIM, facts=EMPTY_FACTS, load_forge=False,
                   detectors=[("slow", slow, "rules"),
                              ("knockouts", knockouts.detect, knockouts.KIND)],
                   budgets={"slow": 60}, total_budget=qa.WRITE_RESERVE + 1.0)
    eq(d["detectors"]["knockouts"]["status"], "skipped", "skipped once the budget is spent")
    eq(d["games"][0]["knockouts"], None, "a skipped detector leaves its field null")

    # A truncated (killed) write, and a JSON file that is not a result.
    for name, needle in ((TRUNCATED, "JSONDecodeError"), (NOT_A_RUN, "not a simulation result")):
        rc, out = qa.run_one(RESULTS / name, _TMP, quiet=True)
        eq(rc, 1, f"{name}: written with errors")
        d = json.loads(out.read_text(encoding="utf-8"))
        eq((d["status"], d["games"], d["flags"]), ("partial", [], []), f"{name}: empty report")
        assert any(needle in e["error"] for e in d["errors"]), d["errors"]

    # A salvaged partial run: analysed, and says what it is.
    rc, out = qa.run_one(RESULTS / SALVAGED, _TMP, quiet=True)
    d = json.loads(out.read_text(encoding="utf-8"))
    eq(d["run_state"], {"games_played": 2, "games_expected": 4, "incomplete": True,
                        "salvaged": True, "rotated": False}, "run state")
    eq(len(d["games"]), 2, "every game kept, the cut-off one too")
    eq((d["games"][1]["winner"], d["games"][1]["method"]), (None, None),
       "a game with no result has no method")
    eq(rc, 0 if not d["errors"] else 1, "exit code follows errors")


def cli() -> None:
    py = [sys.executable, "-u", str(ENGINE / "qa" / "run.py")]
    env = dict(os.environ, MTG_DATA_DIR=str(_TMP))
    r = subprocess.run(py + ["sim_nope.json"], capture_output=True, text=True, env=env)
    eq(r.returncode, 2, "no such result: exit 2")
    assert not (_TMP / "simkb" / "runs" / "sim_nope").exists(), "nothing written for it"
    r = subprocess.run(py, capture_output=True, text=True, env=env)
    eq(r.returncode, 2, "no arguments: exit 2")
    r = subprocess.run(py + [FIXTURE, "--no-queue", "--nice", "5"], capture_output=True,
                       text=True, env=env)
    eq(r.returncode, 0, f"by bare name in sim_results: {r.stderr}")
    assert FIXTURE in r.stdout, r.stdout

    # --all over the corpus: the truncated and non-result files count as
    # written with errors, never as a crash.
    for p in (_TMP / "simkb" / "runs").glob("*/qa.json"):
        p.unlink()
    r = subprocess.run(py + ["--all", "--quiet"], capture_output=True, text=True, env=env,
                       timeout=300)
    line = [x for x in r.stdout.splitlines() if x.startswith("qa --all: ")][-1]
    c = json.loads(line[len("qa --all: "):])
    eq((c["runs"], c["written"], c["with_errors"], c["not_written"], c["skipped_current"]),
       (5, 5, 2, 0, 0), f"--all counts: {c}")
    eq(r.returncode, 1, "--all exits 1 when any run has errors")
    r = subprocess.run(py + ["--all", "--quiet"], capture_output=True, text=True, env=env,
                       timeout=300)
    c = json.loads([x for x in r.stdout.splitlines() if x.startswith("qa --all: ")][-1][10:])
    eq((c["written"], c["skipped_current"]), (0, 5), "a second --all skips current reports")
    # A report from another analyzer version is stale and redone.
    p = qa.qa_path(FIXTURE, _TMP)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["analyzer"] = "qa/0.0.1"
    p.write_text(json.dumps(d), encoding="utf-8")
    r = subprocess.run(py + ["--all", "--quiet"], capture_output=True, text=True, env=env,
                       timeout=300)
    c = json.loads([x for x in r.stdout.splitlines() if x.startswith("qa --all: ")][-1][10:])
    eq((c["written"], c["skipped_current"]), (1, 4), "stale analyzer version redone")
    # A qa.json written with --no-queue (what budget.py used to do on the VM)
    # has flags that were never filed; the sweeper skips any run with a
    # qa.json, so --all must redo it with the queue, and then leave it alone.
    for f in (_TMP / "simkb" / "review_queue" / "auto").glob(qa.run_stem(SHIM) + "#*.json"):
        f.unlink()
    r = subprocess.run(py + [SHIM, "--no-queue", "--quiet"], capture_output=True, text=True,
                       env=env)
    eq((r.returncode, qa.read_qa(SHIM, _TMP)["review_queue"]), (0, None), "--no-queue write")
    assert qa.read_qa(SHIM, _TMP)["flags"], "the shim run has flags to file"
    r = subprocess.run(py + ["--all", "--quiet"], capture_output=True, text=True, env=env,
                       timeout=300)
    c = json.loads([x for x in r.stdout.splitlines() if x.startswith("qa --all: ")][-1][10:])
    eq((c["written"], c["skipped_current"]), (1, 4), "a --no-queue report is redone by --all")
    filed = list((_TMP / "simkb" / "review_queue" / "auto").glob(qa.run_stem(SHIM) + "#*.json"))
    assert filed and qa.read_qa(SHIM, _TMP)["review_queue"]["written"] == len(filed), filed
    r = subprocess.run(py + ["--all", "--quiet", "--no-queue"], capture_output=True, text=True,
                       env=env, timeout=300)
    c = json.loads([x for x in r.stdout.splitlines() if x.startswith("qa --all: ")][-1][10:])
    eq(c["written"], 0, "--all --no-queue does not chase unfiled flags")
    r = subprocess.run(py + ["--all", "--force", "--quiet", "--limit", "2"], capture_output=True,
                       text=True, env=env, timeout=300)
    c = json.loads([x for x in r.stdout.splitlines() if x.startswith("qa --all: ")][-1][10:])
    eq(c["written"], 2, "--force --limit 2")


def mk_flag(det, sev, game, turn, i):
    return {"id": f"sim_x#g{game}t{turn}.{det}~{i}", "detector": det, "severity": sev,
            "anchor": {"game": game, "turn": turn}, "kind": "rules", "trust": "experimental"}


def queue_cap_and_strata() -> None:
    flags = ([mk_flag("noisy.a", "high", 1 + i % 4, i, i) for i in range(100)]
             + [mk_flag("quiet.b", "medium", 2, i, i) for i in range(5)]
             + [mk_flag("minor.c", "low", 1, i, i) for i in range(10)])
    elig = rq.eligible(flags, "medium")
    eq(len(elig), 105, "low is below the default threshold")
    picks = rq.stratify(elig, 30)
    by = {}
    for f in picks:
        by[f["detector"]] = by.get(f["detector"], 0) + 1
    eq(by, {"noisy.a": 25, "quiet.b": 5}, "a noisy detector cannot crowd out a quiet one")
    eq(rq.stratify(elig, 30), picks, "deterministic")
    eq(len(rq.stratify(rq.eligible(flags, "low"), 30)), 30, "cap")
    three = rq.stratify(rq.eligible(flags, "low"), 3)
    eq(sorted(f["detector"] for f in three), ["minor.c", "noisy.a", "quiet.b"],
       "round-robin: one of each before a second of any")
    eq(rq.min_severity({"MTG_QA_QUEUE_MIN_SEVERITY": "HIGH"}), "high", "env override")
    eq(rq.min_severity({"MTG_QA_QUEUE_MIN_SEVERITY": "bogus"}), "medium", "bad value: default")

    # The cap holds across re-runs and counts triaged items in done/.
    ddir = _TMP / "capdata"
    stem = "sim_20260101_010000_eeeeeeeeeeee"
    doc = {"run": stem + ".json", "run_stem": stem, "analyzer": qa.ANALYZER,
           "flags": [dict(f, id=f["id"].replace("sim_x", stem)) for f in flags]}
    done = rq.root(ddir) / "done"
    done.mkdir(parents=True)
    for f in doc["flags"][:28]:
        (done / f"{f['id']}.json").write_text("{}", encoding="utf-8")
    (done / "sim_other#g1t1.x.json").write_text("{}", encoding="utf-8")
    s = rq.enqueue(doc, ddir)
    eq((s["already_queued"], s["written"]), (28, 2), "28 triaged + 2 new = the cap of 30")
    s = rq.enqueue(doc, ddir)
    eq(s["written"], 0, "full: nothing more for this run")
    for p in (rq.root(ddir) / "auto").iterdir():
        rec = json.loads(p.read_text(encoding="utf-8"))
        assert rec["id"] not in {f["id"] for f in doc["flags"][:28]}, "never re-files a done id"


def queue_reader() -> None:
    ddir = _TMP / "readdata"
    root = rq.root(ddir)
    (root / "human").mkdir(parents=True)
    (root / "auto").mkdir(parents=True)
    base = time.time_ns() - 3600 * 10**9

    def put(sub, name, rec, t_ns):
        p = root / sub / name
        p.write_text(json.dumps(rec), encoding="utf-8")
        os.utime(p, ns=(t_ns, t_ns))

    put("auto", "sim_a#g1a1.tutor.x_zero.json",
        {"id": "sim_a#g1a1.tutor.x_zero", "priority": 2, "created": "2026-09-01T00:00:01Z"},
        base + 1 * 10**9)
    put("auto", "sim_a#g1a2.knockout.deckout.json",
        {"id": "sim_a#g1a2.knockout.deckout", "priority": 3, "created": "2026-09-01T00:00:01Z"},
        base + 1 * 10**9)
    put("human", "flag-1.json", {"id": "flag-1", "note": "why did it do that",
                                 "created": "2026-09-01T00:00:02Z"}, base + 2 * 10**9)
    put("auto", "sim_b#g1a1.tutor.unreachable.json",
        {"id": "sim_b#g1a1.tutor.unreachable", "priority": 2, "created": "2026-09-01T00:00:03Z"},
        base + 3 * 10**9)
    put("human", ".flag-tmp.tmp", {}, base)            # a writer's temp file: never listed
    (root / "auto" / "broken.json").write_text("{", encoding="utf-8")
    os.utime(root / "auto" / "broken.json", ns=(base + 4 * 10**9,) * 2)

    page = rq.read_queue(ddir)
    ids = [i["id"] for i in page["items"]]
    eq(ids, ["flag-1", "sim_a#g1a1.tutor.x_zero", "sim_b#g1a1.tutor.unreachable",
             "sim_a#g1a2.knockout.deckout"], "human first, then auto by priority")
    eq((page["counts"], page["unreadable"], page["more"]), ({"human": 1, "auto": 3}, 1, False),
       "counts")
    eq(page["items"][0]["queue"], "human", "each item says which queue")
    cur = page["cursor"]
    eq(rq.read_queue(ddir, rq.parse_cursor(cur))["items"], [], "nothing after the cursor")
    # Paging: a page never splits items that share one write time.
    p1 = rq.read_queue(ddir, 0, limit=1)
    eq(([i["id"] for i in p1["items"]], p1["more"]),
       (["sim_a#g1a1.tutor.x_zero", "sim_a#g1a2.knockout.deckout"], True),
       "the two items written in the same ns come together")
    p2 = rq.read_queue(ddir, rq.parse_cursor(p1["cursor"]), limit=1)
    eq([i["id"] for i in p2["items"]], ["flag-1"], "then the next")
    # A file younger than the settle window waits for the next pull.
    fresh = time.time_ns()
    put("human", "flag-2.json", {"id": "flag-2", "created": "x"}, fresh)
    page = rq.read_queue(ddir, rq.parse_cursor(cur), now_ns=fresh + 10**9)
    eq((page["items"], page["held_for_settle"], page["cursor"]), ([], 1, cur),
       "held, and the cursor does not pass it")
    page = rq.read_queue(ddir, rq.parse_cursor(cur), now_ns=fresh + 3 * 10**9)
    eq([i["id"] for i in page["items"]], ["flag-2"], "served once settled")
    for bad in ("abc", "-1", "1.5", "9" * 21):
        try:
            rq.parse_cursor(bad)
        except ValueError:
            continue
        raise AssertionError(f"cursor {bad!r} accepted")
    eq(rq.parse_cursor(""), 0, "empty cursor = from the start")


def public_view() -> None:
    d = qa.read_qa(SHIM, _TMP)
    assert d["games"][0]["turning_point"] is not None, "the synthetic game has a swing"
    d["flags"].append({"id": "x", "note": "a person's words", "reporter": "richard"})
    d["flags"].append({"id": "y", "source": "flag_this_play"})
    pub = qa.public(d, game_story.switches({}))
    assert "a person's words" not in json.dumps(pub), "no human note in the public view"
    eq(len(pub["flags"]), len(d["flags"]) - 2, "only the human-shaped flags dropped")
    assert "run_stem" not in pub, pub.keys()
    eq(pub["games"][0]["turning_point"]["label"], "Biggest board swing", "default label")
    pub = qa.public(d, game_story.switches({"MTG_TURNING_POINT": "off"}))
    eq(pub["games"][0]["turning_point"], None, "switch off: held, as on the pages")
    pub = qa.public(d, game_story.switches({"MTG_TURNING_POINT": "audited"}))
    eq(pub["games"][0]["turning_point"]["label"], "Turning point", "the label in force")
    assert d["games"][0]["turning_point"]["label"] == "Biggest board swing", "input untouched"


def main() -> None:
    try:
        fixture_run()
        first = shim_run()
        idempotent(first)
        errors_path()
        queue_cap_and_strata()
        queue_reader()
        public_view()
        cli()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
