#!/usr/bin/env python3
"""POST /flags ("Flag this moment") and the flags-only key set MTG_FLAG_KEYS.

Repair plan WS2 layer A task 5, decision 11: a playtester gets a key that can
flag a replay moment and do nothing else. MTG_API_KEYS is one flat set, and
any key in it can start a 4 GB simulation, so the flags key must live in its
own set and every other write must refuse it. These checks pin:

  * the MTG_FLAG_KEYS format (label:key entries) and what a malformed entry does;
  * the auth matrix: admin and flags keys may flag; a flags key is refused by
    POST /simulate, /decks, /ask, /coaching and DELETE /decks with a 403, in
    open mode too; no key or an unknown key cannot flag once any key is set;
  * the reporter comes from the key, never from the request body;
  * validation: run name (traversal guard, existence), game range, both anchor
    shapes, the stale-replay cross-check, seats, note length and stripping,
    body shape and size, each with a clear 4xx;
  * the written file: path, fields, unique ids, no temp files left behind;
  * the per-key rate limit, and that one key's quota is not another's;
  * no public read of human notes;
  * flag keys alone never satisfy the refuse-to-bind-publicly check.

An in-process server on 127.0.0.1 with a throwaway MTG_DATA_DIR holding a
copy of the committed 2-game fixture and one synthetic run with agent events.
No network beyond loopback, no JVM, no Forge.

Run: py engine/tests/test_flags.py   -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import http.client
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

ADMIN = "admin-key-for-tests-0001"
RICHARD = "flag-key-richard-0001"
BARE = "flag-key-unlabelled-0001"
LIMITED = "flag-key-ratelimited-0001"
OTHER = "flag-key-other-0001"

# Set before the engine import: API_KEYS, FLAG_KEYS and the data paths are
# read at import time, exactly as in production.
_TMP = tempfile.mkdtemp(prefix="simlab_flags_")
os.environ["MTG_DATA_DIR"] = _TMP
os.environ["MTG_EMBEDDED_WORKER"] = "0"
os.environ["MTG_BIND"] = "127.0.0.1"
os.environ["MTG_API_KEYS"] = ADMIN
# Three malformed entries: a label with a space, an empty key, an empty label.
os.environ["MTG_FLAG_KEYS"] = (f"richard:{RICHARD}, {BARE} ,limited:{LIMITED},"
                               f"other:{OTHER},bad label:zzz,nolabel:,:nokey")
for k in ("MTG_FLAG_PER_HOUR", "MTG_ALLOW_OPEN_PUBLIC", "MTG_ALLOW_ORIGIN"):
    os.environ.pop(k, None)

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))
import mtg_engine  # noqa: E402

RESULTS = Path(_TMP) / "sim_results"
RESULTS.mkdir(parents=True, exist_ok=True)
FIXTURE = "sim_20260724_093703_fixture.json"
SYNTH = "sim_20260101_000000_synthetic.json"
shutil.copy(ENGINE / "tests" / "fixtures" / "sim_sample.json", RESULTS / FIXTURE)
# A file just outside sim_results: what a traversal would reach.
(Path(_TMP) / "secret.json").write_text('{"games": [{}]}', encoding="utf-8")

A, B = "Ai(1)-Kess, Reanimator", "Ai(2)-Skrat's Revenge"
SYNTH_RUN = {
    "meta": {"agent": "simlab-forge-shim/0.17.0", "decks": ["kess.dck", "skrat.dck"]},
    "summary": {},
    "games": [{
        "players": [A, B],
        "result": {"winner": A, "draw": False, "duration_ms": 1000, "raw": ""},
        "events_pregame": [{"seq": 1, "action": "mulligan", "raw": f"{A} has kept a hand of 7 cards"}],
        "turns": [
            {"turn": 1, "active_player": A, "events": [
                {"seq": 2, "action": "phase", "raw": f"{A}'s Untap step"},
                {"seq": 3, "action": "land_drop", "raw": f"{A} played Swamp (11)"}]},
            {"turn": 2, "active_player": B, "events": [
                {"seq": 5, "action": "phase", "raw": f"{B}'s Untap step"},
                {"seq": 6, "action": "stack_add", "raw": f"{B} cast Sol Ring (40)"}]},
            {"turn": 3, "active_player": A, "events": [
                {"seq": 8, "action": "phase", "raw": f"{A}'s Untap step"}]},
        ],
        "agent_events": [{"turn": 1, "kind": "tutor_cast"},
                         {"turn": 2, "kind": "attack", "seq": 77}],
    }],
}
(RESULTS / SYNTH).write_text(json.dumps(SYNTH_RUN), encoding="utf-8")

BASE = ""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server() -> None:
    global BASE
    port = _free_port()
    threading.Thread(target=mtg_engine.serve, args=(port,), daemon=True).start()
    BASE = f"http://127.0.0.1:{port}"
    for _ in range(200):  # the KB loads before the socket binds
        try:
            urllib.request.urlopen(BASE + "/health", timeout=2).read()
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("server did not start")


def call(path: str, body=None, key: str | None = None, method: str | None = None,
         header: str = "bearer", raw: bytes | None = None) -> tuple[int, object, dict]:
    """(status, parsed body, headers). Never raises on an HTTP status."""
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data,
                                 method=method or ("POST" if data is not None else "GET"))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if key:
        if header == "bearer":
            req.add_header("Authorization", f"Bearer {key}")
        else:
            req.add_header("X-Api-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, payload, hdrs = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        status, payload, hdrs = e.code, e.read(), dict(e.headers)
    try:
        return status, json.loads(payload), hdrs
    except ValueError:
        return status, payload.decode("utf-8", "replace"), hdrs


def flag(body: dict | None = None, key: str | None = RICHARD, **kw):
    b = {"run": FIXTURE, "game": 1, "anchor": {"event_index": 10}, "note": "looks odd"}
    if body:
        b.update(body)
    return call("/flags", b, key=key, **kw)


def queue_files() -> list[Path]:
    q = mtg_engine.REVIEW_QUEUE_HUMAN
    return sorted(q.glob("*.json")) if q.is_dir() else []


def fresh() -> None:
    mtg_engine._hits.clear()


# ------------------------------------------------------------------ units --

def test_parse_flag_keys():
    keys, bad = mtg_engine.parse_flag_keys(os.environ["MTG_FLAG_KEYS"])
    assert bad == 3, bad
    assert keys[RICHARD] == "richard" and keys[LIMITED] == "limited", keys
    assert keys[BARE].startswith("flagkey-") and len(keys[BARE]) == len("flagkey-") + 8, keys
    assert BARE not in keys[BARE], "an unlabelled reporter must not reveal the key"
    assert mtg_engine.FLAG_KEYS == keys and mtg_engine.FLAG_KEYS_MALFORMED == 3
    assert mtg_engine.parse_flag_keys("") == ({}, 0)
    assert mtg_engine.parse_flag_keys(None) == ({}, 0)
    assert mtg_engine.parse_flag_keys(" , ,") == ({}, 0)
    # A key holding ":" cannot be told from a label, so it is refused, not guessed.
    assert mtg_engine.parse_flag_keys("a:b:c") == ({}, 1)
    assert mtg_engine.parse_flag_keys("x" * 41 + ":k") == ({}, 1)
    assert mtg_engine.parse_flag_keys("v.a_t-1:k") == ({"k": "v.a_t-1"}, 0)
    print("  MTG_FLAG_KEYS parses label:key, tags bare keys, skips malformed: OK")


def test_reporter_from_key_only():
    assert mtg_engine.flag_reporter(RICHARD) == "richard"
    assert mtg_engine.flag_reporter(ADMIN).startswith("admin-")
    assert ADMIN not in mtg_engine.flag_reporter(ADMIN)
    assert mtg_engine.flag_reporter("nope") is None
    assert mtg_engine.flag_reporter("") is None  # keys are configured
    print("  reporter derives from the key; unknown or missing key is refused: OK")


def test_clean_note():
    c = mtg_engine.clean_flag_note
    assert c(None) == "" and c("  ") == ""
    assert c("a\x1b[31mb\x00c\x7f") == "a[31mbc", repr(c("a\x1b[31mb\x00c\x7f"))
    assert c("line1\r\nline2\rline3\tend") == "line1\nline2\nline3 end"
    assert c("safe‮gnp.exe​") == "safegnp.exe"   # bidi override, zero-width
    assert c("x\ud800y") == "xy"                            # lone surrogate
    assert c("é Ω 漢 🙂") == "é Ω 漢 🙂"                    # real text survives
    assert len(c("n" * 1000)) == 1000
    for bad, code in (("n" * 1001, 413), (5, 400), (["a"], 400)):
        try:
            c(bad)
            raise AssertionError(f"{bad!r:.20} accepted")
        except mtg_engine.FlagRejected as e:
            assert e.code == code, (e.code, e.msg)
    # The limit counts what is stored: 1000 visible characters plus controls pass.
    assert len(c("n" * 1000 + "\x00" * 50)) == 1000
    print("  note: controls and format characters stripped, newlines kept, 1000 max: OK")


# ------------------------------------------------------------------- HTTP --

def test_auth_matrix():
    fresh()
    # Who may flag.
    st, body, _ = flag(key=RICHARD)
    assert st == 200 and body["ok"] and body["reporter"] == "richard", (st, body)
    st, body, _ = flag(key=ADMIN)
    assert st == 200 and body["reporter"].startswith("admin-"), (st, body)
    st, body, _ = flag(key=BARE)
    assert st == 200 and body["reporter"].startswith("flagkey-"), (st, body)
    st, body, _ = flag(key=RICHARD, header="x-api-key")
    assert st == 200 and body["reporter"] == "richard", (st, body)
    st, body, _ = flag(key=None)
    assert st == 401 and "flag key is required" in body["error"], (st, body)
    st, body, _ = flag(key="not-a-key")
    assert st == 401 and "not recognised" in body["error"], (st, body)
    # A malformed MTG_FLAG_KEYS entry never became a key.
    st, _, _ = flag(key="zzz")
    assert st == 401, st

    # What a flags key may NOT do. Every body below would be refused past the
    # gate too (empty pod, oversized decklist), so nothing is ever enqueued or
    # written even if the gate were broken; the status proves which layer spoke.
    writes = [("/simulate", {"decks": [], "games": 0}, "POST"),
              ("/decks", {"name": "x", "text": "n" * 100_001}, "POST"),
              ("/ask", {"q": ""}, "POST"),
              ("/coaching", {"result_file": "", "deck": ""}, "POST"),
              ("/decks/definitely_not_a_deck.dck", None, "DELETE")]
    for path, body_in, method in writes:
        for fk in (RICHARD, BARE):
            st, body, _ = call(path, body_in, key=fk, method=method)
            assert st == 403 and "flag key" in body["error"], (path, fk, st, body)
            assert "—" not in body["error"], "engine copy reaches the UI: no em dash"
        st, body, _ = call(path, body_in, key=None, method=method)
        assert st == 401, (path, st, body)
        st, body, _ = call(path, body_in, key=ADMIN, method=method)
        assert st not in (401, 403), (path, "admin must pass the gate", st, body)
    print("  admin, labelled and bare flags keys flag; flags keys get 403 on every other write: OK")


def test_open_mode():
    fresh()
    saved_api, saved_flags = mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS
    try:
        mtg_engine.API_KEYS = set()          # open mode: sims need no key...
        st, body, _ = call("/simulate", {"decks": [], "games": 0}, key=RICHARD)
        assert st == 403, ("a flags key is never an admin credential", st, body)
        st, _, _ = call("/simulate", {"decks": [], "games": 0})
        assert st == 400, st                 # ...anonymous passes the gate as before
        st, body, _ = flag(key=None)         # flag keys configured: flags stay keyed
        assert st == 401, (st, body)
        mtg_engine.FLAG_KEYS = {}            # fully open (local dev)
        st, body, _ = flag(key=None)
        assert st == 200 and body["reporter"] == "open-mode", (st, body)
        st, body, _ = flag(key="junk")       # a presented but unknown key: refused
        assert st == 401, (st, body)
    finally:
        mtg_engine.API_KEYS, mtg_engine.FLAG_KEYS = saved_api, saved_flags
    print("  open mode: flags key still 403 on /simulate; anonymous flags only when fully open: OK")


def test_reporter_in_body_is_ignored():
    fresh()
    st, body, _ = flag({"reporter": "vincent", "id": "../../evil", "created": "1999"},
                       key=RICHARD)
    assert st == 200 and body["reporter"] == "richard", (st, body)
    rec = json.loads((mtg_engine.REVIEW_QUEUE_HUMAN / f"{body['id']}.json").read_text("utf-8"))
    assert rec["reporter"] == "richard" and rec["id"] == body["id"], rec
    assert rec["created"] != "1999" and "evil" not in rec["id"], rec
    print("  reporter, id and created come from the server, not the body: OK")


def test_validation():
    fresh()
    cases = [
        ({"run": None}, 400, "pass run"),
        ({"run": 7}, 400, "pass run"),
        ({"run": "sim_nope.json"}, 404, "no such run"),
        ({"game": None}, 400, "game must be"),
        ({"game": "1"}, 400, "game must be"),
        ({"game": True}, 400, "game must be"),
        ({"game": 1.0}, 400, "game must be"),
        ({"game": 0}, 400, "not in this run"),
        ({"game": 3}, 400, "not in this run (it has 2)"),
        ({"anchor": None}, 400, "pass anchor"),
        ({"anchor": [10]}, 400, "pass anchor"),
        ({"anchor": {}}, 400, "event_index"),
        ({"anchor": {"event_index": -1}}, 400, "is not in game 1"),
        ({"anchor": {"event_index": 1446}}, 400, "it has 1446 events"),
        ({"anchor": {"event_index": "10"}}, 400, "whole number"),
        ({"anchor": {"event_index": 10, "player": "Ai(9)-Nobody"}}, 400, "seats"),
        ({"anchor": {"event_index": 10, "player": 3}}, 400, "seats"),
        ({"anchor": {"event_index": 10, "event_seq": 999999}}, 409, "out of date"),
        ({"anchor": {"event_index": 10, "turn": 40}}, 409, "out of date"),
        ({"anchor": {"agent_event_index": 0}}, 400, "needs turn"),
        ({"anchor": {"turn": 999, "agent_event_index": 0}}, 400, "not in game 1"),
        # The fixture is a stdout run: no agent events at all.
        ({"anchor": {"turn": 1, "agent_event_index": 0}}, 400, "0 pilot decisions"),
        ({"note": "n" * 1001}, 413, "limit is 1000"),
        ({"note": {"text": "x"}}, 400, "note must be text"),
    ]
    before = len(queue_files())
    for patch, code, needle in cases:
        st, body, _ = flag(patch)
        assert st == code and needle in body.get("error", ""), (patch, st, body)
        assert "—" not in body["error"], body
    assert len(queue_files()) == before, "a refused flag must write nothing"

    # Body framing: not JSON, not an object, too large.
    st, body, _ = call("/flags", raw=b"{not json", key=RICHARD)
    assert st == 400 and "JSON" in body["error"], (st, body)
    st, body, _ = call("/flags", raw=b"[1, 2]", key=RICHARD)
    assert st == 400 and "object" in body["error"], (st, body)
    big = json.dumps({"run": FIXTURE, "game": 1, "anchor": {"event_index": 1},
                      "note": "n" * (mtg_engine.FLAG_BODY_MAX + 1)}).encode()
    st, body, _ = call("/flags", raw=big, key=RICHARD)
    assert st == 413, (st, body)
    # The same bad body on another route now gets a 400 instead of a dropped
    # connection (the parse used to sit outside the handler's try).
    st, body, _ = call("/simulate", raw=b"{not json", key=ADMIN)
    assert st == 400, (st, body)
    print(f"  {len(cases)} invalid bodies refused with clear 4xx and nothing written: OK")


def test_traversal():
    fresh()
    probes = ["../secret.json", "..\\secret.json", "/etc/passwd", "sim_results/../secret.json",
              "./" + FIXTURE, FIXTURE + "/../secret.json", "C:secret.json",
              FIXTURE.replace(".json", ".txt"), "..", "", "x\x00.json"]
    for run in probes:
        st, body, _ = flag({"run": run})
        # 400 for anything that is not a bare *.json name; 404 only for a bare
        # name that does not exist (e.g. "C:secret.json" on POSIX, "x\0.json").
        assert (st == 400) or (st == 404 and body["error"] == "no such run"), (run, st, body)
    # The file a traversal would reach is untouched and unread into any flag.
    assert json.loads((Path(_TMP) / "secret.json").read_text("utf-8")) == {"games": [{}]}
    print(f"  {len(probes)} traversal and bad-name probes refused: OK")


def test_written_file():
    fresh()
    before = {p.name for p in queue_files()}
    note = "Why bounce Hullbreaker\nwith a dozen Beasts\x1b[0m on board?"
    # Fixture game 1, event 10: derive what the server should record from the
    # file itself, the same flat order the replay uses.
    g = json.loads((RESULTS / FIXTURE).read_text("utf-8"))["games"][0]
    flat = [(0, "", e) for e in g["events_pregame"]] + \
        [(t["turn"], t["active_player"], e) for t in g["turns"] for e in t["events"]]
    ei = next(i for i, (turn, _, e) in enumerate(flat) if turn == 5)
    turn, active, ev = flat[ei]
    other = next(p for p in g["players"] if p != active)
    st, body, _ = flag({"anchor": {"event_index": ei, "event_seq": ev["seq"], "turn": turn,
                                   "player": other}, "note": note})
    assert st == 200, (st, body)
    new = [p for p in queue_files() if p.name not in before]
    assert [p.name for p in new] == [f"{body['id']}.json"], (new, body)
    rec = json.loads(new[0].read_text("utf-8"))
    for k in ("id", "run", "game", "anchor", "turn", "player", "note", "reporter", "created"):
        assert k in rec, (k, rec)
    assert rec["schema"] == "simlab.flag/1" and rec["source"] == "flag_this_play", rec
    assert rec["run"] == FIXTURE and rec["game"] == 1 and rec["turn"] == turn, rec
    assert rec["player"] == other and rec["active_player"] == active, rec
    assert rec["note"] == "Why bounce Hullbreaker\nwith a dozen Beasts[0m on board?", rec["note"]
    assert rec["reporter"] == "richard", rec
    assert rec["anchor"] == {"game": 1, "turn": turn, "player": other,
                             "agent_event_index": None, "seq": None,
                             "event_index": ei, "event_seq": ev["seq"]}, rec["anchor"]
    assert rec["event"] == {"action": ev["action"], "raw": ev["raw"][:500]}, rec["event"]
    # Round 2 of Kilo's turns at turn 5 in a 4-seat pod (turns 1 and 5).
    assert rec["round"] == 2, rec["round"]
    assert rec["created"].endswith("Z") and rec["id"].startswith("flag-"), rec
    assert body["anchor"] == rec["anchor"] and body["created"] == rec["created"]

    # The QA-schema anchor on the synthetic shim run: agent event without a
    # replay position; player defaults to the turn's active seat; seq carries
    # through from the agent event.
    st, body, _ = flag({"run": SYNTH, "anchor": {"turn": 2, "agent_event_index": 1}})
    assert st == 200, (st, body)
    rec = json.loads((mtg_engine.REVIEW_QUEUE_HUMAN / f"{body['id']}.json").read_text("utf-8"))
    assert rec["anchor"] == {"game": 1, "turn": 2, "player": B, "agent_event_index": 1,
                             "seq": 77, "event_index": None, "event_seq": None}, rec["anchor"]
    assert rec["event"] is None and rec["round"] == 1 and rec["note"] == "looks odd", rec
    # A pregame moment: turn 0, no active player, round 0, player null.
    st, body, _ = flag({"run": SYNTH, "anchor": {"event_index": 0}, "note": ""})
    assert st == 200, (st, body)
    rec = json.loads((mtg_engine.REVIEW_QUEUE_HUMAN / f"{body['id']}.json").read_text("utf-8"))
    assert (rec["turn"], rec["round"], rec["player"], rec["active_player"], rec["note"]) == \
        (0, 0, None, None, ""), rec
    # The last event of the synthetic game resolves to turn 3, A's round 2.
    st, body, _ = flag({"run": SYNTH, "anchor": {"event_index": 5, "event_seq": 8}})
    assert st == 200 and body["anchor"]["turn"] == 3, (st, body)
    rec = json.loads((mtg_engine.REVIEW_QUEUE_HUMAN / f"{body['id']}.json").read_text("utf-8"))
    assert rec["round"] == 2 and rec["player"] == A, rec

    # Identical requests get distinct ids; no temp file survives any write.
    ids = {flag()[1]["id"] for _ in range(5)}
    assert len(ids) == 5, ids
    leftovers = [p.name for p in mtg_engine.REVIEW_QUEUE_HUMAN.iterdir()
                 if not p.name.endswith(".json") or p.name.startswith(".")]
    assert leftovers == [], leftovers
    for p in queue_files():
        json.loads(p.read_text("utf-8"))  # every file is whole, parseable JSON
    print("  the queue file: path, fields, derived anchor, unique ids, no temp files: OK")


def test_rate_limit():
    fresh()
    saved = mtg_engine.FLAG_PER_HOUR
    mtg_engine.FLAG_PER_HOUR = 3
    try:
        for i in range(3):
            st, body, _ = flag(key=LIMITED)
            assert st == 200, (i, st, body)
        before = len(queue_files())
        st, body, hdrs = flag(key=LIMITED)
        assert st == 429 and "3/hour" in body["error"], (st, body)
        assert int(hdrs.get("Retry-After", 0)) > 0 and body["retry_after"] > 0, (hdrs, body)
        assert len(queue_files()) == before, "a throttled flag must write nothing"
        # One key's quota is not another's.
        st, body, _ = flag(key=OTHER)
        assert st == 200, (st, body)
        # Validation failures spend quota too (validating parses a result file):
        # two refused bodies and one good flag exhaust a fresh quota of 3.
        fresh()
        for patch in ({"game": 99}, {"anchor": {"event_index": -1}}):
            st, _, _ = flag(patch, key=LIMITED)
            assert st == 400, st
        st, _, _ = flag(key=LIMITED)
        assert st == 200, st
        st, _, _ = flag(key=LIMITED)
        assert st == 429, st
        # An unauthenticated caller is refused before the limiter: 401, never 429.
        st, _, _ = flag(key=None)
        assert st == 401, st
    finally:
        mtg_engine.FLAG_PER_HOUR = saved
        fresh()
    print("  per-key quota: 429 with Retry-After past the limit, other keys unaffected: OK")


def test_no_public_read():
    fresh()
    st, body, _ = flag({"note": "private words 7f3c"})
    assert st == 200, (st, body)
    fid = body["id"]
    for path in ("/flags", f"/flags/{fid}", "/qa/queue", "/simkb/review_queue/human",
                 f"/simkb/review_queue/human/{fid}.json", "/review_queue",
                 f"/results/..%2fsimkb%2freview_queue%2fhuman%2f{fid}.json"):
        for key in (None, RICHARD, ADMIN):
            st, got, _ = call(path, key=key)
            assert st in (400, 404), (path, key, st)
            assert "private words" not in json.dumps(got), (path, key)
    print("  no route reads a human note back, with or without a key: OK")


def test_health_reports_flags_boolean():
    fresh()
    st, body, _ = call("/health")
    assert st == 200 and body.get("flags") is True, (st, body)
    blob = json.dumps(body)
    for k in (RICHARD, BARE, LIMITED, ADMIN, "richard"):
        assert k not in blob, f"/health leaked {k}"
    print("  /health says flags=true and names no key or label: OK")


def test_refuses_public_bind_with_only_flag_keys():
    saved_api, saved_bind = mtg_engine.API_KEYS, os.environ.get("MTG_BIND")
    outcome: dict = {}

    def attempt():
        try:
            mtg_engine.serve(_free_port())
            outcome["ran"] = True
        except SystemExit as e:
            outcome["exit"] = str(e)

    try:
        mtg_engine.API_KEYS = set()
        assert mtg_engine.FLAG_KEYS and not mtg_engine.ALLOW_OPEN_PUBLIC
        os.environ["MTG_BIND"] = "0.0.0.0"
        t = threading.Thread(target=attempt, daemon=True)
        t.start()
        t.join(timeout=60)
    finally:
        mtg_engine.API_KEYS = saved_api
        os.environ["MTG_BIND"] = saved_bind or "127.0.0.1"
    assert "refusing to bind" in outcome.get("exit", ""), outcome
    print("  flag keys alone never satisfy the public-bind check: OK")


def main() -> int:
    try:
        test_parse_flag_keys()
        test_reporter_from_key_only()
        test_clean_note()
        start_server()
        test_auth_matrix()
        test_open_mode()
        test_reporter_in_body_is_ignored()
        test_validation()
        test_traversal()
        test_written_file()
        test_rate_limit()
        test_no_public_read()
        test_health_reports_flags_boolean()
        test_refuses_public_bind_with_only_flag_keys()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print("flags: ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
