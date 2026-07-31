#!/usr/bin/env python3
"""End-to-end smoke test against a RUNNING engine API.

test_adapter.py covers log parsing in isolation. This covers the part that only
breaks when the pieces are wired together: routes, auth, the guards, and the
queue -> Forge -> adapted JSON -> per-game payload path that the front end walks.

    python3 engine/tests/smoke_test.py                        # reads only, fast
    python3 engine/tests/smoke_test.py --sim                  # + one real 2-game sim
    python3 engine/tests/smoke_test.py --base http://host:3000/engine
    python3 engine/tests/smoke_test.py --key <MTG_API_KEYS value>

--sim runs Forge for real rather than faking a result: a 2-deck 2-game run
measured 10 s and a 3-deck run 27 s on an M-series laptop, so there is no reason
to mock it, and mocking would only prove the mock works. It needs a worker
(MTG_EMBEDDED_WORKER unset, or a separate worker.py) and an installed Forge.

Stdlib only, like the rest of engine/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 60

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  ok    {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")
    return ok


def call(base: str, path: str, method: str = "GET", body: dict | None = None,
         key: str | None = None, timeout: int = TIMEOUT) -> tuple[int, object]:
    """(status, parsed-json-or-raw-text). Never raises on an HTTP error status."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    except Exception as e:  # noqa: BLE001 — connection refused etc.
        return 0, str(e)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode("utf-8", "replace")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default="http://127.0.0.1:8484",
                   help="API base URL (use .../engine when going through the proxy)")
    p.add_argument("--key", default=None, help="API key, if the server has MTG_API_KEYS set")
    p.add_argument("--sim", action="store_true", help="also run one real 2-game simulation")
    p.add_argument("--sim-timeout", type=int, default=600)
    a = p.parse_args()
    base = a.base.rstrip("/")

    print(f"smoke test: {base}")

    print("\nrules knowledge base")
    st, health = call(base, "/health")
    if not check("GET /health is 200", st == 200, f"status {st}: {health}"):
        print("\nengine unreachable — start it first:\n"
              "  python3 engine/mtg_engine.py serve 8484")
        return 1
    check("health reports a loaded corpus",
          isinstance(health, dict) and health.get("rules", 0) > 3000,
          f"rules={health.get('rules') if isinstance(health, dict) else '?'}")
    st, rule = call(base, "/rule/903.10a")
    check("GET /rule/903.10a resolves",
          st == 200 and isinstance(rule, dict) and bool(rule.get("entries")))
    st, srch = call(base, "/search?" + urllib.parse.urlencode({"q": "commander damage", "k": "5"}))
    # A ranked list of {score, id, rule, text}, not an envelope object.
    check("GET /search returns ranked hits",
          st == 200 and isinstance(srch, list) and len(srch) > 0
          and all("rule" in h and "score" in h for h in srch),
          str(srch)[:120])
    check("GET /search honours k", isinstance(srch, list) and len(srch) <= 5,
          f"got {len(srch) if isinstance(srch, list) else '?'}")
    st, turns = call(base, "/turn-structure")
    check("GET /turn-structure is 200", st == 200 and bool(turns))

    print("\ndecks")
    st, decks = call(base, "/decks")
    ok_decks = check("GET /decks lists decks", st == 200 and isinstance(decks, list) and bool(decks))
    if ok_decks:
        check("deck entries carry file and name",
              all(isinstance(d, dict) and "file" in d and "name" in d for d in decks))

    print("\nresults index and payloads")
    st, results = call(base, "/results")
    ok_res = check("GET /results is a list", st == 200 and isinstance(results, list))
    newest = results[0]["file"] if ok_res and results else None
    if not newest:
        print("  note  no result files on this engine — payload checks skipped."
              "\n        run with --sim, or copy one into MTG_DATA_DIR/sim_results.")
    else:
        enc = urllib.parse.quote(newest)
        st, summary = call(base, f"/results/{enc}/summary")
        ok_sum = check(f"GET /results/{newest}/summary is 200", st == 200, str(summary)[:120])
        if ok_sum and isinstance(summary, dict):
            games = summary.get("games") or []
            check("summary carries per-game entries", bool(games))
            # The pod roster: every seat that played must appear in wins, winless
            # or not, or consumers size the pod wrong and the even-seats baseline
            # comes out as 100%. See forge_log_adapter.summarize().
            seats = {pl for g in games for pl in (g.get("players") or [])}
            wins = (summary.get("summary") or {}).get("wins") or {}
            def bare(s: str) -> str:
                return s.split("-", 1)[1] if s.startswith("Ai(") and "-" in s else s
            check("every seat appears in summary.wins",
                  bool(seats) and len({bare(s) for s in seats} - {bare(w) for w in wins}) == 0,
                  f"seats={sorted(bare(s) for s in seats)} wins={sorted(bare(w) for w in wins)}")
            if games:
                st, one = call(base, f"/results/{enc}/game/1")
                ok_game = check("GET /results/{file}/game/1 is 200", st == 200, str(one)[:120])
                if ok_game and isinstance(one, dict):
                    g = one.get("game") or {}
                    check("game payload has players and turns",
                          bool(g.get("players")) and bool(g.get("turns")))
                    names = {e.get("object") for t in g.get("turns", [])
                             for e in t.get("events", []) if e.get("object")}
                    if names:
                        q = urllib.parse.urlencode({"names": "|".join(sorted(names)[:20])})
                        st, cd = call(base, f"/cards?{q}")
                        check("GET /cards returns facts for cast cards",
                              st == 200 and isinstance(cd, dict) and bool(cd.get("cards")),
                              str(cd)[:120])
        st, oob = call(base, f"/results/{enc}/game/99999")
        check("out-of-range game number is 404", oob is not None and st == 404, f"status {st}")

        # Wincon analysis: win methods always classify; combo detection depends
        # on Spellbook reachability, so only its PRESENCE is asserted.
        st, an = call(base, f"/analysis/{enc}", timeout=180)
        ok_an = check("GET /analysis/{file} is 200", st == 200, str(an)[:120])
        if ok_an and isinstance(an, dict):
            methods = (an.get("summary") or {}).get("methods") or {}
            check("analysis classifies every game",
                  sum(methods.values()) == (an.get("summary") or {}).get("games"),
                  str(methods))
            check("analysis carries per-deck combo status",
                  bool(an.get("decks")) and all("combo_status" in d
                                                for d in an["decks"].values()))
            check("analysis states its inference ceiling", "inferred" in (an.get("note") or ""))
            check("analysis is versioned and carries the draw model",
                  isinstance(an.get("version"), int)
                  and any(d.get("draws") for d in an["decks"].values()),
                  f"version={an.get('version')}")
        st, _ = call(base, "/analysis/..%2f..%2fetc%2fpasswd")
        check("analysis blocks path traversal", st in (400, 404), f"status {st}")

    print("\nguards")
    st, _ = call(base, "/no-such-endpoint")
    check("unknown endpoint is 404", st == 404, f"status {st}")
    for probe in ("/results/..%2f..%2fetc%2fpasswd", "/results/%2fetc%2fpasswd",
                  "/results/....%2f%2fetc%2fpasswd"):
        st, _ = call(base, probe)
        check(f"path traversal blocked: {probe}", st in (400, 403, 404), f"status {st}")
    st, body = call(base, "/simulate", "POST", {"decks": [], "games": 0}, key=a.key)
    # 401 when the server has keys and we were given none; 400 once past auth.
    check("POST /simulate rejects an empty pod", st in (400, 401), f"status {st}: {body}")
    if ok_decks and decks:
        st, body = call(base, "/simulate", "POST",
                        {"decks": [decks[0]["file"], "definitely_not_a_deck.dck"], "games": 1},
                        key=a.key)
        check("POST /simulate rejects an unknown deck", st in (400, 401), f"status {st}: {body}")
        st, body = call(base, "/simulate", "POST",
                        {"decks": [d["file"] for d in decks[:2]], "games": 100000}, key=a.key)
        check("POST /simulate rejects an oversized game count", st in (400, 401),
              f"status {st}: {body}")

    if a.sim:
        print("\nlive simulation (real Forge)")
        if not (ok_decks and len(decks) >= 2):
            check("two decks available to sim", False, "need at least 2 decks")
        else:
            pod = [d["file"] for d in decks[:2]]
            st, job = call(base, "/simulate", "POST", {"decks": pod, "games": 2}, key=a.key)
            ok_q = check(f"queued a 2-game run of {pod}",
                         st == 200 and isinstance(job, dict) and bool(job.get("job_id")),
                         f"status {st}: {job}")
            if ok_q and isinstance(job, dict):
                jid = job["job_id"]
                started = time.time()
                state, last = "queued", {}
                while time.time() - started < a.sim_timeout:
                    st, last = call(base, f"/sim-status?id={urllib.parse.quote(jid)}")
                    state = last.get("state") if isinstance(last, dict) else "?"
                    if state in ("done", "error", "failed"):
                        break
                    time.sleep(5)
                took = int(time.time() - started)
                ok_done = check(f"job finished (state={state}, {took}s)", state == "done",
                                str(last)[:300])
                if ok_done and isinstance(last, dict):
                    res = last.get("result") or {}
                    check("run summary reports the games it was asked for",
                          res.get("games") == 2, str(res)[:200])
                    rf = last.get("result_file") or ""
                    name = rf.rsplit("/", 1)[-1]
                    if check("job names a result file", bool(name), rf):
                        st, idx = call(base, "/results")
                        check("new result appears in the index",
                              st == 200 and isinstance(idx, list)
                              and any(e.get("file") == name for e in idx), name)
                        st, sm = call(base, f"/results/{urllib.parse.quote(name)}/summary")
                        check("new result is readable", st == 200 and isinstance(sm, dict),
                              str(sm)[:120])

    total = passed + len(failed)
    print(f"\n{passed}/{total} checks passed")
    if failed:
        print("failed:")
        for f in failed:
            print(f"  - {f}")
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
