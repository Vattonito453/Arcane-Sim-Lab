#!/usr/bin/env python3
"""Does this deployment actually serve what we think it serves?

WHY THIS EXISTS. Twice in two days a feature was built, merged, deployed, and
silently dark in production, and nothing caught it:

  - the fitted prediction model was tracked in git but never entered the
    images, because both Dockerfiles copy the engine with `COPY engine/*.py`,
    a top-level glob. /results/{file}/prediction answered "no fitted model"
    for weeks while working perfectly on every developer machine.
  - rubric records were being written by the shim and dropped by the adapter,
    so the behaviour half of the scorecards was blank on runs that had the
    data sitting in their raw logs.

Neither failure was visible from the repo, and both endpoints returned HTTP
200 the whole time. A green test suite and a successful deploy proved nothing.

So this file is the missing artifact: an explicit statement of WHAT IS MEANT
TO BE LIVE, checked against a running deployment. A surface that is meant to
be live and is not is a FAILURE. A surface that is deliberately off carries
its reason here, so nobody has to re-investigate it and nobody mistakes a
decision for a bug.

Run it against the API from inside the api container (no external deps):

    python3 deploy/preflight.py
    python3 deploy/preflight.py --base http://api:8484 --files

Exit codes: 0 all intended-live surfaces are live; 1 something is dark.

MAINTAINING THIS. When you add a user-visible feature, add a SURFACE entry in
the same commit. When you deliberately turn something off, move it to
intent="off" with a reason rather than deleting the entry, so the fact that it
exists and is off stays visible.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8484"


# --------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------

def fetch(base, path, timeout=60):
    """Return (status, parsed_or_text). Never raises."""
    try:
        r = urllib.request.urlopen(base + path, timeout=timeout)
        body = r.read().decode("utf-8", "replace")
        try:
            return r.status, json.loads(body)
        except ValueError:
            return r.status, body
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            return e.code, "<unparseable http error>"
    except Exception as e:  # noqa: BLE001
        return 0, "EXC: %s" % e


# --------------------------------------------------------------------------
# Predicates. Each returns (ok: bool, detail: str) given the parsed body.
# They assert the endpoint DID ITS JOB, not merely that it answered.
# --------------------------------------------------------------------------

def nonempty_list(body):
    if not isinstance(body, list):
        return False, "expected a list, got %s" % type(body).__name__
    return (len(body) > 0), "%d items" % len(body)


def has_keys(*keys):
    def check(body):
        if not isinstance(body, dict):
            return False, "expected an object, got %s" % type(body).__name__
        missing = [k for k in keys if k not in body]
        if missing:
            return False, "missing %s" % missing
        return True, "keys present"
    return check


def available_true(body):
    """For endpoints that self-report readiness with {"available": bool}."""
    if not isinstance(body, dict):
        return False, "expected an object"
    if body.get("available") is True:
        n = len(body.get("decks") or [])
        return True, "available, %d decks scored" % n
    return False, "available=%s reason=%s" % (
        body.get("available"), body.get("reason"))


def kb_loaded(body):
    if not isinstance(body, dict):
        return False, "expected an object"
    n = body.get("rules") or 0
    # 3,152 numbered rules is the documented corpus. Any large number proves
    # the KB shipped; zero means rules/kb never made it into the image.
    return (n > 3000), "rules=%s keywords=%s" % (n, body.get("keywords"))


def deck_labels_present(body):
    """meta.decks holds container paths; deck_labels must carry real names.

    Regression guard: the telemetry and coaching deck pickers rendered
    "/data/decks/skrat s revenge 239c6293" straight at the user.
    """
    if not isinstance(body, dict):
        return False, "expected an object"
    labels = body.get("deck_labels")
    if not isinstance(labels, list) or not labels:
        return False, "deck_labels absent (engine older than the fix?)"
    bad = [x for x in labels if "/" in str(x) or str(x).endswith(".dck")]
    if bad:
        return False, "labels still look like paths: %s" % bad[:2]
    return True, "%s" % labels[:3]


def scorecards_ok(body):
    if not isinstance(body, dict) or "decks" not in body or "run" not in body:
        return False, "shape wrong"
    run = body.get("run") or {}
    decks = body.get("decks") or []
    if not decks:
        return False, "no decks scored"
    # The censoring split shipped with the honesty pass; its absence means a
    # stale engine is answering.
    if "timedOut" not in run or "turnCapped" not in run:
        return False, "run is missing the timedOut/turnCapped split"
    return True, "%d decks, behaviour=%s" % (len(decks), run.get("hasBehaviour"))


def cached_read_endpoint(body):
    """/ask and /coaching are READ-ONLY caches by design.

    They answer {"ok": false, "reason": "not generated"} until something has
    been generated, and that is correct, not broken. What we assert is that
    the endpoint is reachable and well-formed.
    """
    if not isinstance(body, dict):
        return False, "expected an object"
    if "ok" not in body:
        return False, "missing ok flag"
    return True, "reachable (ok=%s reason=%s)" % (
        body.get("ok"), body.get("reason"))


# --------------------------------------------------------------------------
# The manifest. THIS is the statement of intent.
# --------------------------------------------------------------------------
# intent="live" -> must pass, or preflight fails.
# intent="off"  -> deliberately not enabled; reason is mandatory and is
#                  printed so it never gets re-investigated as a bug.

def surfaces(run, deck):
    return [
        {
            "name": "rules KB",
            "intent": "live",
            "path": "/health",
            "check": kb_loaded,
            "note": "rules/kb ships in the image; 0 rules means it did not",
        },
        {
            "name": "deck index",
            "intent": "live",
            "path": "/decks",
            "check": nonempty_list,
        },
        {
            "name": "results index",
            "intent": "live",
            "path": "/results",
            "check": nonempty_list,
        },
        {
            "name": "run summary",
            "intent": "live",
            "path": "/results/%s/summary" % run,
            "check": has_keys("meta", "summary", "games"),
        },
        {
            "name": "deck display names",
            "intent": "live",
            "path": "/results/%s/summary" % run,
            "check": deck_labels_present,
            "note": "deck pickers must never render a server path",
        },
        {
            "name": "deck scorecards",
            "intent": "live",
            "path": "/results/%s/scorecards" % run,
            "check": scorecards_ok,
        },
        {
            "name": "playgroup prediction",
            "intent": "live",
            "path": "/results/%s/prediction" % run,
            "check": available_true,
            "note": "needs engine/models/precon_predict.json INSIDE the image",
        },
        {
            "name": "replay events",
            "intent": "live",
            "path": "/results/%s/game/1" % run,
            "check": has_keys("game", "meta"),
        },
        {
            "name": "win-condition analysis",
            "intent": "live",
            "path": "/analysis/%s" % run,
            "check": has_keys("decks", "summary"),
        },
        {
            "name": "board reconstruction",
            "intent": "live",
            "path": "/board/%s" % run,
            "check": has_keys("basis", "exit_match_rate"),
        },
        {
            "name": "deck telemetry",
            "intent": "live",
            "path": "/results/%s/telemetry?deck=%s" % (run, deck),
            "check": has_keys("games", "deck", "engine"),
            "note": "CLAUDE.md called this 'no UI yet'; it has had one for a while",
        },
        {
            "name": "card facts (Scryfall cache)",
            "intent": "live",
            "path": "/cards?names=Sol%20Ring&fetch=0",
            "check": has_keys("cards", "cache"),
        },
        {
            "name": "rules answer cache",
            "intent": "live",
            "path": "/ask?q=commander%20damage",
            "check": cached_read_endpoint,
            "note": "read-only by design; ok=false just means nothing cached yet",
        },
        {
            "name": "coaching report cache",
            "intent": "live",
            "path": "/coaching/%s?deck=%s" % (run, deck),
            "check": cached_read_endpoint,
            "note": "read-only by design; generation is the POST route",
        },
        # ------------------------------------------------------------------
        # Deliberately off. Each carries WHY, so it is never re-litigated.
        # ------------------------------------------------------------------
        {
            "name": "coaching generation (POST /coaching)",
            "intent": "off",
            "reason": "MTG_LLM_API_KEY is unset. Turning it on spends money on "
                      "a paid model key, which is the owner's call, not the "
                      "agent's. Set it in deploy/.env to enable.",
        },
        {
            "name": "rules assistant generation (POST /ask)",
            "intent": "off",
            "reason": "Same MTG_LLM_API_KEY. Retrieval works and is live; only "
                      "the generated answer is gated.",
        },
        {
            "name": "embedded worker",
            "intent": "off",
            "reason": "MTG_EMBEDDED_WORKER=0 on purpose: workers are separate "
                      "containers here so a 4 GB JVM cannot take the API down.",
        },
    ]


# --------------------------------------------------------------------------
# Files that must be inside the image (run with --files in the container)
# --------------------------------------------------------------------------

IMAGE_FILES = [
    ("/app/engine/models/precon_predict.json",
     "the fitted prediction model; a top-level COPY glob once missed it"),
    ("/app/rules/kb", "the Comprehensive Rules KB the /ask retrieval reads"),
    ("/app/engine/decks", "bundled decks"),
]


def check_files():
    print("\nIMAGE CONTENTS")
    bad = 0
    for path, why in IMAGE_FILES:
        ok = os.path.exists(path)
        if not ok:
            bad += 1
        print("  %-9s %-42s %s" % ("ok" if ok else "MISSING", path, why))
    return bad


def pick_run(base):
    """Newest result file, which is the one worth probing."""
    st, body = fetch(base, "/results")
    if not isinstance(body, list) or not body:
        return None
    names = []
    for r in body:
        n = r.get("file") if isinstance(r, dict) else r
        if n:
            names.append(n)
    return sorted(names)[-1] if names else None


def pick_deck(base, run):
    """A deck that is actually IN the probe run.

    Taking /decks[0] instead looks reasonable and is wrong: the global deck
    index contains decks this run never played, and telemetry for a deck that
    is not in the run correctly 404s. That produced a false DARK verdict on a
    healthy endpoint the first time this ran, which is exactly the kind of
    noise that teaches people to ignore a checker.
    """
    st, body = fetch(base, "/results/%s/summary" % run)
    if isinstance(body, dict):
        decks = (body.get("meta") or {}).get("decks") or []
        if decks:
            return str(decks[0]).replace("\\", "/").split("/")[-1]
    return ""


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("PREFLIGHT_BASE", DEFAULT_BASE))
    ap.add_argument("--files", action="store_true",
                    help="also check image contents (run inside the container)")
    args = ap.parse_args(argv)

    run = pick_run(args.base)
    if not run:
        print("FAIL: /results returned nothing; cannot probe per-run surfaces.")
        return 1
    deck = pick_deck(args.base, run)
    print("preflight against %s" % args.base)
    print("probe run: %s" % run)
    print("probe deck: %s" % (deck or "(none)"))

    failures = []
    off = []
    print("\nSURFACES")
    for s in surfaces(run, deck):
        if s["intent"] == "off":
            off.append(s)
            continue
        st, body = fetch(args.base, s["path"])
        if st != 200:
            ok, detail = False, "HTTP %s" % st
        else:
            try:
                ok, detail = s["check"](body)
            except Exception as e:  # noqa: BLE001
                ok, detail = False, "check raised %s" % e
        if not ok:
            failures.append((s, detail))
        print("  %-6s %-30s %s" % ("ok" if ok else "DARK", s["name"], detail))

    print("\nDELIBERATELY OFF (not failures)")
    for s in off:
        print("  off    %-30s %s" % (s["name"], s["reason"]))

    if args.files:
        failures += [("files", "")] * check_files()

    print()
    if failures:
        print("PREFLIGHT FAILED: %d surface(s) meant to be live are dark."
              % len(failures))
        for s, detail in failures:
            if isinstance(s, dict):
                print("  - %s: %s" % (s["name"], detail))
                if s.get("note"):
                    print("      hint: %s" % s["note"])
        return 1
    print("PREFLIGHT OK: every surface meant to be live is live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
