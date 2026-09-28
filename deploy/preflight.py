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

Exit codes: 0 all intended-live surfaces are live and every deployment
invariant holds; 1 something is dark or an invariant is broken.

DEPLOYMENT INVARIANTS (repair plan WS0 task 6). Two facts no HTTP surface
shows, checked after the surfaces:
  - the plan_feedback nudge is OFF (MTG_PLAN_FEEDBACK_APPLY is not "1" in this
    process's environment, which is the API container's when run as below;
    compose hands the worker the same .env value);
  - the newest result was piloted by a shim at least as new as the release
    pin. A run finished BEFORE the deploy fails this until a new sim finishes,
    so the post-deploy order is: deploy, smoke_test.py --sim, then preflight.

MAINTAINING THIS. When you add a user-visible feature, add a SURFACE entry in
the same commit. When you deliberately turn something off, move it to
intent="off" with a reason rather than deleting the entry, so the fact that it
exists and is off stays visible. When a release pins a newer shim, raise
SHIM_FLOOR below in the same commit as the SIMLAB_SHIM_REF default in
docker-compose.yml.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8484"


# --------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------

def fetch(base, path, timeout=60, body=None):
    """Return (status, parsed_or_text). Never raises. With `body`, POSTs it as
    JSON and sends NO credential: preflight probes a write route only to prove
    it exists and is gated, never to write."""
    try:
        if body is None:
            req = base + path
        else:
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
        r = urllib.request.urlopen(req, timeout=timeout)
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


def game_story_ok(body):
    """Every game carries its story (engine/game_story.py), and the run its
    commanders and pilot. A 200 without them is an engine older than R1, or
    one whose analyzer failed on every game (all stories empty)."""
    if not isinstance(body, dict):
        return False, "expected an object"
    games = body.get("games") or []
    if not games or not all(isinstance(g.get("knockouts"), list) and "turning_point" in g
                            for g in games):
        return False, "games carry no knockouts/turning_point (engine older than R1?)"
    if not isinstance(body.get("commanders"), dict) or not (body.get("pilot") or {}).get("label"):
        return False, "commanders or pilot missing"
    decided = [g for g in games if (g.get("result") or {}).get("winner")
               and not (g.get("result") or {}).get("draw")]
    if decided and not any(g["knockouts"] for g in decided):
        return False, "no knockouts in any decided game: the analyzer failed on every one"
    story = body.get("story") or {}
    return True, "label=%s detail=%s pilot=%s" % (
        story.get("turning_point_label"), story.get("knockout_detail"),
        body["pilot"].get("kind"))


def analysis_ok(body):
    """The wincon report, from an engine that carries qa.knockouts.

    ANALYSIS_VERSION 6 added per-game `knockouts` (repair plan WS1). A report
    without them is a stale engine, or one whose image is missing engine/qa/
    and fell back to the loss-line reading."""
    if not isinstance(body, dict):
        return False, "expected an object"
    missing = [k for k in ("decks", "summary", "games") if k not in body]
    if missing:
        return False, "missing %s" % missing
    version = body.get("version") or 0
    if version < 6:
        return False, "analysis version %s < 6 (no knockouts)" % version
    games = body.get("games") or []
    bare = [g.get("n") for g in games
            if not isinstance(g, dict) or not isinstance(g.get("knockouts"), list)]
    if bare:
        return False, "games without a knockouts list: %s" % bare[:5]
    kos = sum(len(g["knockouts"]) for g in games)
    return True, "v%s, %d games, %d knockouts" % (version, len(games), kos)


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


# "Flag this moment" (repair plan WS2 layer A task 5). Two facts: the route is
# deployed and gated (always meant to be live: admin keys can flag), and the
# playtesters' flags-only keys are loaded (live only once Vincent has set
# MTG_FLAG_KEYS; unset is a deliberate off, not a failure).
FLAG_KEYS_ENV = "MTG_FLAG_KEYS"


def _fully_open(env):
    """Neither key set: the engine takes anonymous writes (local dev only)."""
    return not (env.get("MTG_API_KEYS") or "").strip() and \
        not (env.get(FLAG_KEYS_ENV) or "").strip()


def flag_route_gated(body):
    """POST /flags with no credential and an empty body. A deployed route
    answers 401 from the flags gate (or, on a fully open dev server, 400 for
    the empty body); an engine that predates /flags answers 404."""
    if not isinstance(body, dict):
        return False, "expected an object"
    err = str(body.get("error") or "")
    if "flag key" in err or "pass run" in err:
        return True, "route present and gated (%s)" % err
    return False, "unexpected answer: %s" % err[:80]


def parse_flag_keys_env(env=None):
    """(keys loaded, malformed entries) for MTG_FLAG_KEYS, by the engine's own
    parser so the two can never disagree about the format."""
    env = os.environ if env is None else env
    raw = env.get(FLAG_KEYS_ENV) or ""
    engine_dir = _engine_dir()
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)
    from mtg_engine import parse_flag_keys
    keys, bad = parse_flag_keys(raw)
    return len(keys), bad


def flag_keys_loaded(env=None):
    """Predicate on GET /health: every MTG_FLAG_KEYS entry parses, and the
    running engine reports that it loaded flag keys."""
    def check(body):
        if not isinstance(body, dict):
            return False, "expected an object"
        n, bad = parse_flag_keys_env(env)
        if bad:
            return False, ("%d malformed %s entr(y/ies) skipped: the format is "
                           "label:key,label:key (deploy/HOSTING.md)" % (bad, FLAG_KEYS_ENV))
        if body.get("flags") is not True:
            return False, ("the engine reports flags=%s: it loaded no flag key. "
                           "Recreate the api container after editing .env."
                           % body.get("flags"))
        return True, "%d flag key(s) configured; the engine reports flags=true" % n
    return check


def flag_surfaces(env=None):
    """The two flags entries for the manifest, the second decided by the env."""
    env = os.environ if env is None else env
    route = {
        "name": "flag route (POST /flags)",
        "intent": "live",
        "path": "/flags",
        "post": {},
        # Production always sets MTG_API_KEYS, so only the gate's 401 passes
        # there. 400 is accepted only when this env says the engine is open.
        "expect": (401, 400) if _fully_open(env) else (401,),
        "check": flag_route_gated,
        "note": "an unkeyed POST must meet the flags gate; 404 means the "
                "engine image predates /flags",
    }
    if (env.get(FLAG_KEYS_ENV) or "").strip():
        keys = {
            "name": "playtester flag keys",
            "intent": "live",
            "path": "/health",
            "check": flag_keys_loaded(env),
            "note": "MTG_FLAG_KEYS reaches the api through docker-compose.yml",
        }
    else:
        keys = {
            "name": "playtester flag keys",
            "intent": "off",
            "reason": "MTG_FLAG_KEYS is unset, so no playtester holds a flags-only "
                      "key yet and only admin keys can flag a moment. Generating "
                      "one is the owner's call (deploy/HOSTING.md, \"Giving a "
                      "playtester a flag key\").",
        }
    return [route, keys]


# --------------------------------------------------------------------------
# The manifest. THIS is the statement of intent.
# --------------------------------------------------------------------------
# intent="live" -> must pass, or preflight fails.
# intent="off"  -> deliberately not enabled; reason is mandatory and is
#                  printed so it never gets re-investigated as a bug.
# Optional keys: "post" probes the path with an UNKEYED POST of that JSON body
# (to prove a write route exists and is gated; it never writes), and "expect"
# lists the statuses that count as answered (default (200,)).

def surfaces(run, deck, env=None):
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
            "name": "game story",
            "intent": "live",
            "path": "/results/%s/summary" % run,
            "check": game_story_ok,
            "note": "knockouts, out seats, turning point, commanders and pilot "
                    "(engine/game_story.py; MTG_TURNING_POINT / MTG_KNOCKOUT_DETAIL "
                    "set what is shown)",
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
            "check": analysis_ok,
            "note": "per-game knockouts need engine/qa/ INSIDE the image",
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
        {
            "name": "plan_feedback nudges",
            "intent": "off",
            "reason": "MTG_PLAN_FEEDBACK_APPLY is off on purpose: the nudge that "
                      "moves search targets from observed win methods was never "
                      "validated (repair plan RC4). The store still fills. "
                      "Asserted under DEPLOYMENT INVARIANTS, not just noted.",
        },
    ] + flag_surfaces(env)


# --------------------------------------------------------------------------
# Deployment invariants: configuration and provenance a green surface list
# cannot show. Each returns (ok: bool, detail: str).
# --------------------------------------------------------------------------

NUDGE_FLAG = "MTG_PLAN_FEEDBACK_APPLY"

# The oldest shim a production result may come from. 0.16.0 fixes the attack
# re-ask loop that 0.15.0 (the playtester run that prompted the repair plan)
# still had, and its new dials default to 0.15.0 behaviour. Raise this with
# every release pin (SIMLAB_SHIM_REF in docker-compose.yml). When compose also
# hands this container a version-tag SIMLAB_SHIM_REF newer than the floor,
# that tag is the bar instead, so a new pin is never checked against an old one.
SHIM_FLOOR = (0, 16, 0)
_SHIM_AGENT = re.compile(r"simlab-forge-shim/(\d+)\.(\d+)\.(\d+)")
_SHIM_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _fmt_version(v):
    return ".".join(str(x) for x in v)


def nudge_flag_off(env=None):
    """plan_feedback.apply_to_plan runs only when the flag is exactly "1"
    (engine/deck_plan.py), so anything else is off."""
    env = os.environ if env is None else env
    val = env.get(NUDGE_FLAG)
    if val == "1":
        return False, ("%s=1 in this container: plan_feedback nudges are ON. "
                       "They are unvalidated; set %s=0 in deploy/.env and "
                       "redeploy." % (NUDGE_FLAG, NUDGE_FLAG))
    return True, "%s=%s (off)" % (NUDGE_FLAG, "unset" if val is None else repr(val))


def shim_pin(env=None):
    """(version tuple, where it came from): the bar a result's shim must meet."""
    env = os.environ if env is None else env
    ref = (env.get("SIMLAB_SHIM_REF") or "").strip()
    m = _SHIM_TAG.match(ref)
    if m:
        tag = tuple(int(x) for x in m.groups())
        if tag > SHIM_FLOOR:
            return tag, "SIMLAB_SHIM_REF=%s" % ref
    return SHIM_FLOOR, "preflight SHIM_FLOOR"


PLAN_VERSION_FLAG = "MTG_PLAN_VERSION"
# Version-2 plans (the tutoring hotfix) carry threatLines, graveyardTargets and
# fix flags that only shim 0.17.0 and later read; an older shim would pilot the
# narrowed pilot lines without the reach, zone and graveyard checks.
PLAN_V2_SHIM_FLOOR = (0, 17, 0)


def plan_version_supported(pin, env=None):
    """(ok, detail): MTG_PLAN_VERSION is 1, or 2 with a shim pin >= 0.17.0."""
    env = os.environ if env is None else env
    raw = (env.get(PLAN_VERSION_FLAG) or "").strip()
    if raw in ("", "1"):
        return True, "%s=%s (version-1 plans)" % (PLAN_VERSION_FLAG, raw or "unset")
    if raw != "2":
        return False, "%s=%r is not a plan version (expected 1 or 2)" % (PLAN_VERSION_FLAG, raw)
    if pin < PLAN_V2_SHIM_FLOOR:
        return False, ("%s=2 needs shim >= %s, but the pin is %s. Tag and pin "
                       "the 0.17.0 shim first, or set %s=1." % (
                           PLAN_VERSION_FLAG, _fmt_version(PLAN_V2_SHIM_FLOOR),
                           _fmt_version(pin), PLAN_VERSION_FLAG))
    return True, "%s=2 with shim pin %s" % (PLAN_VERSION_FLAG, _fmt_version(pin))


def result_shim_versions(meta):
    """Every shim version a result's meta names: the top-level agent and, on a
    rotated run whose rotations disagreed, each rotation's own agent."""
    agents = [meta.get("agent")]
    for d in meta.get("rotations_detail") or []:
        if isinstance(d, dict):
            agents.append(d.get("agent"))
    found = []
    for a in agents:
        m = _SHIM_AGENT.search(str(a or ""))
        if m:
            found.append(tuple(int(x) for x in m.groups()))
    return found


def shim_at_least_pin(run, meta, pin, pin_source):
    """The newest result's shim version, against the release pin."""
    stale = ("A run that finished before this deploy fails this check until a "
             "new sim finishes: run engine/tests/smoke_test.py --sim, then "
             "preflight again.")
    if not isinstance(meta, dict):
        return False, "could not read meta for %s. %s" % (run, stale)
    versions = result_shim_versions(meta)
    if not versions:
        return False, ("%s names no shim version (meta.agent=%r): a stock-Forge "
                       "or salvaged run. %s" % (run, meta.get("agent"), stale))
    oldest = min(versions)
    if oldest < pin:
        return False, ("%s was piloted by shim %s, older than the pin %s (%s). "
                       "%s" % (run, _fmt_version(oldest), _fmt_version(pin),
                               pin_source, stale))
    return True, "%s: shim %s >= pin %s (%s)" % (
        run, _fmt_version(oldest), _fmt_version(pin), pin_source)


# --------------------------------------------------------------------------
# Files that must be inside the image (run with --files in the container)
# --------------------------------------------------------------------------

IMAGE_FILES = [
    ("/app/engine/models/precon_predict.json",
     "the fitted prediction model; a top-level COPY glob once missed it"),
    ("/app/rules/kb", "the Comprehensive Rules KB the /ask retrieval reads"),
    ("/app/engine/decks", "bundled decks"),
    ("/app/engine/qa/__init__.py",
     "the QA analyzers package; the same top-level glob would miss it"),
    ("/app/engine/qa/knockouts.py",
     "knockouts: analysis.win_method and the scorecards read it"),
]

# Modules that must IMPORT in the image, not merely exist on disk. analysis.py
# imports engine/qa/ at module load, so a missing or broken package would take
# /analysis down at request time while every file check above passed.
IMAGE_IMPORTS = ["qa", "qa.knockouts", "analysis", "scorecard", "game_story",
                 "commanders"]


def _engine_dir():
    """/app/engine in the container; the repo's engine/ when run locally."""
    if os.path.isdir("/app/engine"):
        return "/app/engine"
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "engine")


def check_imports(engine_dir=None):
    """Import the engine modules the image must carry, and run the knockouts
    detector on a two-turn synthetic game, so "imports" means "works"."""
    import importlib
    engine_dir = engine_dir or _engine_dir()
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)
    print("\nIMAGE IMPORTS (%s)" % engine_dir)
    bad = 0
    for name in IMAGE_IMPORTS:
        try:
            importlib.import_module(name)
            print("  %-9s %s" % ("ok", name))
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("  %-9s %s: %s: %s" % ("BROKEN", name, type(e).__name__, e))
    try:
        from qa import knockouts
        game = {
            "players": ["Ai(1)-A", "Ai(2)-B"],
            "result": {"winner": "Ai(1)-A", "draw": False},
            "turns": [
                {"turn": 1, "active_player": "Ai(1)-A", "events": [
                    {"seq": 1, "action": "damage",
                     "raw": "Bear (7) deals 40 combat damage to Ai(2)-B."},
                    {"seq": 2, "action": "life_change",
                     "raw": "Life: Ai(2)-B 40 > 0"},
                    {"seq": 3, "action": "game_outcome",
                     "raw": "Ai(2)-B has lost because life total reached 0"}]},
            ],
        }
        metrics, _flags = knockouts.detect({"games": [game]})
        cause = metrics["by_cause"]
        ok = cause == {"combat_damage": 1}
        if not ok:
            bad += 1
        print("  %-9s knockouts.detect on a synthetic game: %s" %
              ("ok" if ok else "WRONG", cause))
    except Exception as e:  # noqa: BLE001
        bad += 1
        print("  %-9s knockouts.detect: %s: %s" % ("BROKEN", type(e).__name__, e))
    return bad


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
        st, body = fetch(args.base, s["path"], body=s.get("post"))
        if st not in s.get("expect", (200,)):
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

    # The game-story display switches (engine/game_story.py) are set from the
    # week-3 hand audit, without a code change, so their state is printed
    # rather than asserted.
    st, health = fetch(args.base, "/health")
    sw = health.get("story") if (st == 200 and isinstance(health, dict)) else None
    print("\nGAME STORY SWITCHES (set from the knockout / turning-point audit)")
    if isinstance(sw, dict):
        tp = sw.get("turning_point")
        print("  %-6s %-30s %s" % ("info", "MTG_TURNING_POINT", "%s: %s" % (
            tp, {"swing": 'labelled "Biggest swing" (audit not passed yet)',
                 "audited": 'labelled "Turning point" (audit passed)',
                 "off": "held: not shown"}.get(tp, "?"))))
        print("  %-6s %-30s %s" % ("info", "MTG_KNOCKOUT_DETAIL",
                                   "on: cause and killer shown" if sw.get("knockout_detail")
                                   else "off: who went out and when only"))
        if sw.get("invalid"):
            print("  %-6s %-30s unrecognised value in %s; the default is in force" % (
                "warn", "switch value", ", ".join(sw["invalid"])))
    else:
        print("  %-6s %-30s engine older than R1 (no story in /health)" % ("info", "switches"))

    # Deployment invariants. The probe run IS the newest result (pick_run), so
    # the shim check reads the same file the surfaces above were probed on.
    pin, pin_source = shim_pin()
    st, summary = fetch(args.base, "/results/%s/summary" % run)
    meta = summary.get("meta") if (st == 200 and isinstance(summary, dict)) else None
    invariants = [
        ({"name": "plan_feedback nudge off",
          "note": "plans are built in the worker; compose passes it the same "
                  "%s as this container" % NUDGE_FLAG},
         nudge_flag_off()),
        ({"name": "newest run on pinned shim",
          "note": "post-deploy order: deploy, smoke_test.py --sim, then preflight"},
         shim_at_least_pin(run, meta, pin, pin_source)),
        ({"name": "plan version supported",
          "note": "version-2 plans need shim >= 0.17.0 (tasks/25 WS5 T1)"},
         plan_version_supported(pin)),
    ]
    broken = 0
    print("\nDEPLOYMENT INVARIANTS")
    for s, (ok, detail) in invariants:
        if not ok:
            failures.append((s, detail))
            broken += 1
        print("  %-6s %-30s %s" % ("ok" if ok else "FAIL", s["name"], detail))

    if args.files:
        failures += [("files", "")] * check_files()
        failures += [("imports", "")] * check_imports()

    print()
    if failures:
        dark = len(failures) - broken
        print("PREFLIGHT FAILED: %d surface(s) meant to be live are dark; "
              "%d deployment invariant(s) broken." % (dark, broken))
        for s, detail in failures:
            if isinstance(s, dict):
                print("  - %s: %s" % (s["name"], detail))
                if s.get("note"):
                    print("      hint: %s" % s["note"])
        return 1
    print("PREFLIGHT OK: every surface meant to be live is live, and every "
          "deployment invariant holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
