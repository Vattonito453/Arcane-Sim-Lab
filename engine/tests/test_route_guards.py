#!/usr/bin/env python3
"""Every result route answers a bad or missing filename with a 404.

The week-3 security review found GET /board/{traversal} answering 500 with
"bad result filename": the traversal guard (_result_path) raises ValueError,
and /board caught only FileNotFoundError, so the guard's refusal reached the
generic handler. It leaked nothing, but a refusal is not a server error.
These checks pin, over an in-process server on 127.0.0.1:

  * /board, /results/{file}, /results/{file}/summary, /analysis: a traversal,
    a non-.json name and a missing file are all 404, never 500;
  * /board still reconstructs a real result (200 with basis and
    exit_match_rate), so the guard did not swallow the route;
  * the summary and game payloads carry the published standings, and the
    job-status shape is unaffected for an idle queue.

No network beyond loopback, no JVM, no Forge.

Run: py engine/tests/test_route_guards.py   -> ALL ASSERTIONS PASSED
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

_TMP = tempfile.mkdtemp(prefix="simlab_guards_")
os.environ["MTG_DATA_DIR"] = _TMP
os.environ["MTG_EMBEDDED_WORKER"] = "0"
os.environ["MTG_BIND"] = "127.0.0.1"
os.environ["MTG_API_KEYS"] = "guard-test-key-0001"
for k in ("MTG_FLAG_KEYS", "MTG_ALLOW_OPEN_PUBLIC", "MTG_ALLOW_ORIGIN"):
    os.environ.pop(k, None)

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))
import mtg_engine  # noqa: E402

RESULTS = Path(_TMP) / "sim_results"
RESULTS.mkdir(parents=True, exist_ok=True)
FIXTURE = "sim_20260724_093703_fixture.json"
shutil.copy(ENGINE / "tests" / "fixtures" / "sim_sample.json", RESULTS / FIXTURE)
# What a traversal would reach: a JSON file just outside sim_results.
(Path(_TMP) / "secret.json").write_text('{"games": [{}]}', encoding="utf-8")

BASE = ""


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


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


def get(path: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body


BAD = ["..%2Fsecret.json", "%2E%2E%2Fsecret.json", "..%5Csecret.json",
       "secret", "sim_missing.json", "sim_20260724_093703_fixture.txt"]


def test_bad_names_are_404_on_every_route():
    for name in BAD:
        for route in (f"/board/{name}", f"/results/{name}", f"/results/{name}/summary",
                      f"/results/{name}/game/1", f"/analysis/{name}?fetch=0"):
            code, body = get(route)
            check(code == 404, (route, code, body))
            check("secret" not in json.dumps(body) or "no such" in json.dumps(body),
                  (route, body))
    print(f"  {len(BAD)} bad names x 5 result routes: every one a 404, no 500: OK")


def test_board_still_works():
    code, body = get(f"/board/{FIXTURE}")
    check(code == 200, (code, body))
    check("basis" in body and "exit_match_rate" in body, sorted(body)[:10])
    print("  /board still reconstructs a real result: OK")


def test_payloads_carry_standings():
    code, summ = get(f"/results/{FIXTURE}/summary")
    check(code == 200 and summ["standings"]["version"] == 1, summ.get("standings"))
    code, game = get(f"/results/{FIXTURE}/game/1")
    check(code == 200 and game["standings"] == summ["standings"], game.get("standings"))
    code, idx = get("/results")
    row = [e for e in idx if e["file"] == FIXTURE][0]
    check(row["standings"] == summ["standings"], row.get("standings"))
    code, st = get("/sim-status")
    check(code == 200 and st.get("state") == "idle", st)
    print("  summary, game and index carry one standings object: OK")


def test_done_job_status():
    """A finished job's status carries the published standings (the running
    page's "Done." line) and each deck's own name and commanders (its title
    read "Kess Reanimator 305b76d7 vs ..." from the import paths)."""
    import jobqueue
    decks = Path(_TMP) / "decks"
    decks.mkdir(exist_ok=True)
    (decks / "kess_reanimator_305b76d7.dck").write_text(
        "[metadata]\nName=Kess, Reanimator\n[Commander]\n1 Kess, Dissident Mage\n[Main]\n1 Sol Ring\n",
        encoding="utf-8")
    paths = ["/data/decks/kess_reanimator_305b76d7.dck", "/data/decks/missing_1a2b3c4d.dck"]
    jid = jobqueue.enqueue({"decks": paths, "games": 3})
    check(jobqueue.claim()["id"] == jid, "claim")
    summary = {"games": 3, "draws": 1, "timeouts": 1,
               "wins": {"Kess, Reanimator": 2, "Missing": 0}}
    check(jobqueue.finish(jid, {"summary": summary, "result_file": FIXTURE}), "finish")
    code, st = get(f"/sim-status?id={jid}")
    check(code == 200 and st["state"] == "done", st)
    check(st["deck_labels"] == ["Kess, Reanimator", "Missing"], st.get("deck_labels"))
    check(st["commanders"] == {"Kess, Reanimator": ["Kess, Dissident Mage"]}, st.get("commanders"))
    s = st["standings"]
    check(s["decided"] == 2 and s["undecided"]["clock"] == 1, s)
    check(s["decks"][0]["deck"] == "Kess, Reanimator" and s["decks"][0]["rate"] == 1.0, s["decks"])
    check(s["leader"]["kind"] == "leader", s["leader"])
    print("  a finished job's status: standings, deck names, commanders: OK")


def main():
    start_server()
    test_bad_names_are_404_on_every_route()
    test_board_still_works()
    test_payloads_carry_standings()
    test_done_job_status()
    print("test_route_guards: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
