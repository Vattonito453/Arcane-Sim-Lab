#!/usr/bin/env python3
"""QA layer A's read routes (repair plan WS2 layer A task 3).

  GET /results/{file}/qa    public, the same traversal guard as the sibling
                            result routes (_result_path), never a human note
  GET /qa/queue?since=      the review queue, human flags first; a REVIEWER
                            key from MTG_REVIEW_KEYS only. An API key gets 403
                            (the web build inlines one, so it is not private),
                            so does a flags key; no key or an unknown key 401,
                            open mode included. A reviewer key writes nothing.

These checks pin: the served report and its 404 while pending; traversal
probes; that neither a playtester's note written through POST /flags nor a
note planted in a stored qa.json reaches the public route; the API's own
game-story switches applied to the served swing; the queue's auth matrix,
ordering, cursor, paging and argument errors, and that it is never cached.

An in-process server on 127.0.0.1 with a throwaway MTG_DATA_DIR; no network
beyond loopback, no JVM, no Forge.

Run: py engine/tests/test_qa_routes.py   -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ADMIN = "admin-key-for-qa-tests-0001"
FLAGGER = "flag-key-for-qa-tests-0001"
REVIEWER = "review-key-for-qa-tests-0001"
NOTE = "PRIVATE-NOTE-7f3a: why did it bin Sol Ring?"

_TMP = Path(tempfile.mkdtemp(prefix="simlab_qa_routes_"))
os.environ["MTG_DATA_DIR"] = str(_TMP)
os.environ["MTG_EMBEDDED_WORKER"] = "0"
os.environ["MTG_BIND"] = "127.0.0.1"
os.environ["MTG_API_KEYS"] = ADMIN
os.environ["MTG_FLAG_KEYS"] = f"tester:{FLAGGER}"
# The admin and flags keys listed as reviewer keys too: both must be dropped
# (the web build inlines an admin key; a flags key is a tester's).
os.environ["MTG_REVIEW_KEYS"] = f"{REVIEWER},{ADMIN},{FLAGGER}"
for k in ("MTG_TURNING_POINT", "MTG_KNOCKOUT_DETAIL", "MTG_FLAG_PER_HOUR",
          "MTG_ALLOW_OPEN_PUBLIC", "MTG_QA_QUEUE_MIN_SEVERITY"):
    os.environ.pop(k, None)

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))
import mtg_engine  # noqa: E402
from qa import run as qa  # noqa: E402

RESULTS = _TMP / "sim_results"
RESULTS.mkdir(parents=True)
FIXTURE = "sim_20260724_093703_fixture.json"
PENDING = "sim_20260724_093703_pending.json"
SHIM = "sim_20260101_000000_aaaaaaaaaaaa_rotated.json"
for name in (FIXTURE, PENDING):
    shutil.copy(ENGINE / "tests" / "fixtures" / "sim_sample.json", RESULTS / name)
(_TMP / "secret.json").write_text('{"schema": "simlab.qa/1", "secret": true}', encoding="utf-8")

A, B = "Ai(1)-Alpha", "Ai(2)-Beta"


def Z(turn, card, cid, frm, to, fp, tp, types="", pt=""):
    return {"turn": turn, "phase": "MAIN1", "card": card, "cardId": cid, "from": frm, "to": to,
            "fromPlayer": fp, "toPlayer": tp, "types": types, "pt": pt, "token": False}


(RESULTS / SHIM).write_text(json.dumps({
    "meta": {"agent": "simlab-forge-shim/0.17.0", "agents": ["plan", "plan"]},
    "games": [{
        "players": [A, B], "result": {"winner": A, "draw": False},
        "zones": [Z(1, "Grizzly Bears", 7, "Hand", "Stack", A, ""),
                  Z(1, "Grizzly Bears", 7, "Stack", "Battlefield", "", A, "Creature", "2/2"),
                  Z(3, "Verdant Call", 9, "Hand", "Stack", A, "", "Sorcery")],
        "agent_events": [{"turn": 3, "player": A, "event": "tutor_cast",
                          "detail": "reach=false where=Library why=restriction route=spell "
                                    "Verdant Call seeking Tide Oracle"}],
        "turns": [
            {"turn": 1, "active_player": A, "events": [
                {"seq": 1, "action": "stack_add", "raw": f"{A} cast Grizzly Bears (7)"}]},
            {"turn": 2, "active_player": B, "events": []},
            {"turn": 3, "active_player": A, "events": [
                {"seq": 3, "action": "damage", "raw": f"Grizzly Bears (7) deals 40 combat damage to {B}."},
                {"seq": 4, "action": "life_change", "raw": f"Life: {B} 40 > 0"},
                {"seq": 5, "action": "game_outcome",
                 "raw": f"{B} has lost because life total reached 0"}]}]}]}), encoding="utf-8")

BASE = ""


def eq(a, b, msg):
    assert a == b, f"{msg}: {a!r} != {b!r}"


def start_server() -> None:
    global BASE
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    threading.Thread(target=mtg_engine.serve, args=(port,), daemon=True).start()
    BASE = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            urllib.request.urlopen(BASE + "/health", timeout=2).read()
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("server did not start")


def call(path, body=None, key=None, header="bearer"):
    """(status, parsed body, raw text, headers)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    if key:
        if header == "bearer":
            req.add_header("Authorization", f"Bearer {key}")
        else:
            req.add_header("X-Api-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw, st, hd = r.read().decode("utf-8"), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, st, hd = e.read().decode("utf-8"), e.code, dict(e.headers)
    try:
        return st, json.loads(raw), raw, hd
    except ValueError:
        return st, raw, raw, hd


def setup_data() -> None:
    for name in (FIXTURE, SHIM):
        rc, _ = qa.run_one(RESULTS / name, _TMP, quiet=True)
        eq(rc, 0, f"qa for {name}")
    st, body, _, _ = call("/flags", {"run": FIXTURE, "game": 1, "anchor": {"event_index": 3},
                                     "note": NOTE}, key=FLAGGER)
    eq(st, 200, f"a human flag with a note: {body}")


def report_route() -> None:
    st, body, raw, hd = call(f"/results/{FIXTURE}/qa")
    eq(st, 200, "public: no key needed")
    eq((body["schema"], body["run"], body["errors"]), ("simlab.qa/1", FIXTURE, []), "the report")
    assert NOTE not in raw and "PRIVATE-NOTE" not in raw, "a human note never reaches it"
    assert "run_stem" not in body and str(_TMP) not in raw, "no internal fields or paths"
    assert "immutable" not in (hd.get("Cache-Control") or ""), "a report can be rewritten"

    # Defence in depth: even a note planted in the stored file is not served.
    p = qa.qa_path(FIXTURE, _TMP)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["flags"].append({"id": "planted", "note": NOTE, "reporter": "tester"})
    p.write_text(json.dumps(d), encoding="utf-8")
    st, body, raw, _ = call(f"/results/{FIXTURE}/qa")
    assert st == 200 and NOTE not in raw, "a planted note is dropped"

    st, body, _, _ = call(f"/results/{PENDING}/qa")
    eq((st, body.get("qa")), (404, "pending"), "a run with no qa.json yet")
    st, body, _, _ = call("/results/sim_20990101_000000_nope.json/qa")
    eq((st, body.get("qa")), (404, None), "no such run: not 'pending'")
    for probe in ("/results/..%2Fsecret.json/qa", "/results/..%5Csecret.json/qa",
                  "/results/%2Fetc%2Fpasswd/qa", "/results/..%2F..%2Fsecret.json/qa",
                  "/results/sim_20260724_093703_fixture/qa"):
        st, body, raw, _ = call(probe)
        assert st in (400, 404) and "secret" not in raw, f"{probe}: {st} {raw[:120]}"

    st, body, _, _ = call(f"/results/{SHIM}/qa")
    tp = body["games"][0]["turning_point"]
    assert tp and tp["label"] == "Biggest board swing", tp
    assert any(f["detector"] == "tutor.unreachable" for f in body["flags"]), body["flags"]
    os.environ["MTG_TURNING_POINT"] = "off"
    try:
        st, body, _, _ = call(f"/results/{SHIM}/qa")
        eq(body["games"][0]["turning_point"], None, "the API's switch holds the swing")
    finally:
        os.environ.pop("MTG_TURNING_POINT", None)


def queue_route() -> None:
    time.sleep(rq_settle() + 0.5)   # let the files settle past the queue's window
    eq((mtg_engine.REVIEW_KEYS, mtg_engine.REVIEW_KEYS_DROPPED), ({REVIEWER}, 2),
       "a reviewer key that is also an API or flags key is dropped")
    eq(call("/qa/queue")[0], 401, "no key")
    eq(call("/qa/queue", key="not-a-key")[0], 401, "an unknown key")
    st, body, _, _ = call("/qa/queue", key=FLAGGER)
    eq(st, 403, "a flags-only key cannot read the queue")
    assert "flag key" in body["error"], body
    # The web build inlines an admin key (WEB_API_KEY -> NEXT_PUBLIC_API_KEY),
    # so an admin key is in every visitor's browser: it must not read notes.
    st, body, raw, _ = call("/qa/queue", key=ADMIN)
    eq(st, 403, "an API key cannot read the queue")
    assert "reviewer key" in body["error"] and NOTE not in raw, body
    eq(call("/qa/queue", key=ADMIN, header="x-api-key")[0], 403, "nor via X-Api-Key")
    st, body, raw, hd = call("/qa/queue", key=REVIEWER, header="x-api-key")
    eq(st, 200, "reviewer key via X-Api-Key")
    eq(hd.get("Cache-Control"), "no-store", "never cached: it holds a person's words")
    items = body["items"]
    eq(items[0]["queue"], "human", "human flags rank first")
    eq(items[0]["note"], NOTE, "the reviewer sees the note")
    auto = [i for i in items if i["queue"] == "auto"]
    assert auto and all(i["source"].startswith("detector:") for i in auto), auto
    eq(body["counts"], {"human": 1, "auto": len(auto)}, "counts")
    st, body2, _, _ = call(f"/qa/queue?since={body['cursor']}", key=REVIEWER)
    eq((st, body2["items"], body2["cursor"]), (200, [], body["cursor"]), "caught up")
    st, p1, _, _ = call("/qa/queue?limit=1", key=REVIEWER)
    eq((st, len(p1["items"]) >= 1, p1["more"]), (200, True, True), "paged")
    for q in ("since=abc", "since=-5", "since=%C2%B2", "limit=0", "limit=abc", "limit=99999"):
        eq(call(f"/qa/queue?{q}", key=REVIEWER)[0], 400, q)
    eq(call("/qa/queue/extra", key=REVIEWER)[0], 404, "no other qa routes")

    # A reviewer key writes nothing: the same 403 a flags key gets.
    st, body, _, _ = call("/simulate", {"decks": ["a", "b"], "games": 1}, key=REVIEWER)
    eq(st, 403, f"a reviewer key cannot start a simulation: {body}")
    assert "reviewer key" in body["error"], body
    st, body, _, _ = call("/flags", {"run": FIXTURE, "game": 1, "anchor": {"event_index": 3},
                                     "note": "x"}, key=REVIEWER)
    eq(st, 403, f"nor file a flag: {body}")
    assert "reviewer key" in body["error"], body
    eq(call("/health")[1].get("review"), True, "/health says a reviewer key is loaded")

    saved = mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS, mtg_engine.REVIEW_KEYS
    mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS = set(), {}
    try:
        eq(call("/qa/queue")[0], 401, "open mode still needs a reviewer key")
        eq(call("/qa/queue", key="anything")[0], 401, "open mode: an unknown key too")
        st, body, _, _ = call("/simulate", {"decks": ["a", "b"], "games": 1}, key=REVIEWER)
        eq(st, 403, "open mode: a reviewer key still writes nothing")
        mtg_engine.REVIEW_KEYS = set()
        eq(call("/qa/queue", key=REVIEWER)[0], 401, "no reviewer keys: nobody reads it")
        eq(call("/health")[1].get("review"), False, "/health says so")
    finally:
        mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS, mtg_engine.REVIEW_KEYS = saved


def review_keys_never_open_public_bind() -> None:
    """Only MTG_API_KEYS closes the simulation faucet: reviewer keys alone
    never satisfy serve()'s refuse-to-bind-publicly check."""
    saved = mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS, os.environ.get("MTG_BIND")
    outcome: dict = {}
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    def attempt():
        try:
            mtg_engine.serve(port)
            outcome["ran"] = True
        except SystemExit as e:
            outcome["exit"] = str(e)

    try:
        mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS = set(), {}
        assert mtg_engine.REVIEW_KEYS and not mtg_engine.ALLOW_OPEN_PUBLIC
        os.environ["MTG_BIND"] = "0.0.0.0"
        t = threading.Thread(target=attempt, daemon=True)
        t.start()
        t.join(timeout=60)
    finally:
        mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS = saved[0], saved[1]
        os.environ["MTG_BIND"] = saved[2] or "127.0.0.1"
    assert "refusing to bind" in outcome.get("exit", ""), outcome


def rq_settle() -> float:
    from qa import review_queue
    return review_queue.SETTLE_SECONDS


def preflight_checks() -> None:
    """deploy/preflight.py: the newest run must have a clean qa.json (under
    --files), waited for with a bound; the image import check runs the whole
    QA analysis in memory."""
    sys.path.insert(0, str(ENGINE.parent / "deploy"))
    import preflight
    ok, detail = preflight.qa_report_ok(BASE, FIXTURE, wait=0)
    assert ok and "no errors" in detail, detail
    ok, detail = preflight.qa_report_ok(BASE, PENDING, wait=0)
    assert not ok and "no qa.json" in detail, detail

    # The race after a sim: pending at first, written while preflight waits.
    ticks = {"t": 0.0, "slept": 0}

    def sleep(s):
        ticks["t"] += s
        ticks["slept"] += 1
        if ticks["slept"] == 2:
            qa.run_one(RESULTS / PENDING, _TMP, quiet=True, queue=False)

    ok, detail = preflight.qa_report_ok(BASE, PENDING, wait=60, poll=5, sleep=sleep,
                                        clock=lambda: ticks["t"])
    assert ok and "after waiting" in detail, detail
    eq(ticks["slept"], 2, "polled until it appeared, no longer")

    p = qa.qa_path(PENDING, _TMP)
    d = json.loads(p.read_text(encoding="utf-8"))
    d["errors"] = [{"stage": "tutors", "error": "ValueError: boom"}]
    p.write_text(json.dumps(d), encoding="utf-8")
    ok, detail = preflight.qa_report_ok(BASE, PENDING, wait=0)
    assert not ok and "1 error(s)" in detail and "boom" in detail, detail
    old = lambda base, path: (200, {"meta": {}, "games": []})   # an engine before R1.1
    ok, detail = preflight.qa_report_ok(BASE, PENDING, wait=0, fetch_=old)
    assert not ok and "predates" in detail, detail
    ok, detail = preflight.qa_report_ok(BASE, "sim_20990101_000000_nope.json", wait=0)
    assert not ok and "HTTP 404" in detail, detail
    eq(preflight.check_imports(str(ENGINE)), 0, "every image import works, QA analysis included")

    # The review queue's two manifest entries: the gate is always live; the
    # reviewer keys are live when MTG_REVIEW_KEYS is set, a deliberate off not.
    route, keys = preflight.review_surfaces({"MTG_API_KEYS": ADMIN})
    eq((route["intent"], route["expect"], keys["intent"]), ("live", (401,), "off"), "unset")
    assert "web build" in keys["reason"], keys
    st, body = preflight.fetch(BASE, route["path"])
    assert st in route["expect"] and route["check"](body)[0], (st, body)
    old_gate = {"error": "an API key is required to read the review queue"}
    assert not route["check"](old_gate)[0], "the admin-key gate this review replaced fails"
    route, keys = preflight.review_surfaces({"MTG_REVIEW_KEYS": REVIEWER})
    eq((keys["intent"], keys["path"]), ("live", "/health"), "set")
    ok, detail = keys["check"](preflight.fetch(BASE, "/health")[1])
    assert ok, detail
    assert not keys["check"]({"review": False})[0], "set in the env, none loaded"
    names = [s["name"] for s in preflight.surfaces("r.json", "d.dck", env={"MTG_API_KEYS": "k"})]
    assert "review queue gate (GET /qa/queue)" in names and "reviewer keys" in names, names


def main() -> None:
    try:
        start_server()
        setup_data()
        report_route()
        queue_route()
        review_keys_never_open_public_bind()
        preflight_checks()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
