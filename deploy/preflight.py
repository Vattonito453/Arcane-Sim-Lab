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
  - with --files: the newest result has a qa.json (QA layer A, R1.1) with no
    errors, read through GET /results/{file}/qa. The worker writes it in a
    detached child after the run finishes, so the check waits for it (up to
    --qa-wait, 150 s by default) rather than racing the worker.

IN THE WORKER CONTAINER, which serves no API, run the image half only:

    python3 deploy/preflight.py --image-only

It checks the same files and imports as --files, including the in-memory QA
analysis the worker runs after every job.

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


def prediction_ok(body):
    """The playgroup prediction, with its pilot label (WS11 task 11).

    Live means one of two things: figures with the label that says which
    pilot the model was fitted on, or a prediction withheld because the
    committed rank check for the run's pilot failed. The second is a decision
    (decision 19), recorded in engine/models/rank_checks.json, not a dark
    surface. A withheld prediction because that record is MISSING from the
    image is a failure, and so is an answer with no label (an engine older
    than R1)."""
    if not isinstance(body, dict):
        return False, "expected an object"
    if "label" not in body or "pilot" not in body:
        if body.get("available") is False:
            return False, "available=%s reason=%s" % (
                body.get("available"), body.get("reason"))
        return False, "no pilot label (engine older than R1?)"
    pilot = (body.get("pilot") or {}).get("id")
    if body.get("suppressed"):
        if body.get("suppressed_by") == "rank_check":
            return True, "withheld by rank check for pilot %s: %s" % (
                pilot, body.get("suppressed_reason"))
        return False, "withheld: %s" % body.get("suppressed_reason")
    if body.get("available") is True:
        n = len(body.get("decks") or [])
        return True, "available, %d decks scored; pilot %s; rank check %s" % (
            n, pilot, (body.get("rank_check") or {}).get("status"))
    return False, "available=%s reason=%s" % (body.get("available"), body.get("reason"))


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

    ANALYSIS_VERSION 6 added per-game `knockouts` (repair plan WS1), and 7
    the week-3 audit's analyzer fixes (knockout card attribution, the raw-rise
    rule for the turning point). A report below 7 is a stale engine, or one
    whose image is missing engine/qa/ and fell back to the loss-line
    reading."""
    if not isinstance(body, dict):
        return False, "expected an object"
    missing = [k for k in ("decks", "summary", "games") if k not in body]
    if missing:
        return False, "missing %s" % missing
    version = body.get("version") or 0
    if version < 6:
        return False, "analysis version %s < 6 (no knockouts)" % version
    if version < 7:
        return False, "analysis version %s < 7 (knockouts before the week-3 audit fixes)" % version
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


_DISCLOSURE_KEYS = ("could_not_load", "load_basis", "ai_wont_play", "commander_ai_wont_play")


def disclosures_ok(body):
    """Per deck, the cards Forge could not load and the cards its AI doesn't
    cast on its own (engine/disclosure.py; repair plan WS11 task 4, R1.1).

    Two ways this is dark while answering 200: an engine older than R1.1 (no
    `disclosures`), and an api container that cannot read the Forge card
    index the worker builds into $MTG_DATA_DIR/forge_index on the shared
    volume (`index` null). The api image has no Forge jar, so without that
    volume every AI list, and every old run's load list, reads "not checked"
    on every page. Works on the run summary and on GET /decks/{file}."""
    if not isinstance(body, dict):
        return False, "expected an object"
    d = body.get("disclosures")
    if not isinstance(d, dict):
        return False, "no disclosures (engine older than R1.1, or computing them failed)"
    if not d.get("index"):
        return False, ("no Forge card index readable here: the worker builds it "
                       "into $MTG_DATA_DIR/forge_index on the shared volume")
    rows = d.get("decks") if "decks" in d else {"deck": d}
    if not isinstance(rows, dict) or not rows:
        return False, "no decks in the disclosures"
    bad = [n for n, r in rows.items()
           if not isinstance(r, dict) or any(k not in r for k in _DISCLOSURE_KEYS)]
    if bad:
        return False, "decks missing a list: %s" % bad[:2]
    unchecked = [n for n, r in rows.items() if r.get("ai_wont_play") is None]
    listed = sum(len(r.get("ai_wont_play") or []) + len(r.get("could_not_load") or [])
                 for r in rows.values())
    return True, "index %s, decks=%d, cards listed=%d%s" % (
        d.get("index"), len(rows), listed,
        "; AI list not checked for %s (deck file gone?)" % unchecked[:2] if unchecked else "")


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


# The review queue read (GET /qa/queue, R1.1). It holds playtesters' own
# words, so only a reviewer key from MTG_REVIEW_KEYS reads it: an API key is
# refused because the web build inlines one. Two facts, like the flags: the
# route is deployed and gated (always), and a reviewer key is loaded (live
# only once Vincent has set MTG_REVIEW_KEYS; unset is a deliberate off).
REVIEW_KEYS_ENV = "MTG_REVIEW_KEYS"


def review_route_gated(body):
    """GET /qa/queue with no credential: the reviewer gate's 401. An engine
    that predates R1.1 answers 404; one from before the reviewer-key rule
    asks for an API key, which the web build makes public."""
    if not isinstance(body, dict):
        return False, "expected an object"
    err = str(body.get("error") or "")
    if "reviewer key" in err:
        return True, "route present and gated (%s)" % err
    return False, "unexpected answer: %s" % err[:80]


def review_keys_loaded(body):
    if not isinstance(body, dict):
        return False, "expected an object"
    if body.get("review") is not True:
        return False, ("the engine reports review=%s: it loaded no reviewer key. A key "
                       "that is also in MTG_API_KEYS or MTG_FLAG_KEYS is dropped; "
                       "recreate the api container after editing .env." % body.get("review"))
    return True, "the engine reports review=true"


def review_surfaces(env=None):
    """The two review-queue entries for the manifest, the second decided by the env."""
    env = os.environ if env is None else env
    route = {
        "name": "review queue gate (GET /qa/queue)",
        "intent": "live",
        "path": "/qa/queue",
        "expect": (401,),
        "check": review_route_gated,
        "note": "an unkeyed GET must meet the reviewer gate; 404 means the engine "
                "image predates R1.1",
    }
    if (env.get(REVIEW_KEYS_ENV) or "").strip():
        keys = {
            "name": "reviewer keys",
            "intent": "live",
            "path": "/health",
            "check": review_keys_loaded,
            "note": "MTG_REVIEW_KEYS reaches the api through docker-compose.yml",
        }
    else:
        keys = {
            "name": "reviewer keys",
            "intent": "off",
            "reason": "MTG_REVIEW_KEYS is unset, so nobody can read the review queue "
                      "over HTTP; the files are on the volume. The nightly reviewer "
                      "(layer B) needs one, and an API key will not do: the web "
                      "build inlines one (deploy/HOSTING.md, \"QA layer A\").",
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
            "check": prediction_ok,
            "note": "needs engine/models/precon_predict.json and rank_checks.json "
                    "INSIDE the image; a rank-check failure withholds it by design",
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
            "name": "card disclosures (run)",
            "intent": "live",
            "path": "/results/%s/summary" % run,
            "check": disclosures_ok,
            "note": "cards Forge could not load / its AI doesn't cast on its own; "
                    "needs the worker-built Forge index on the shared /data volume",
        },
        {
            "name": "card disclosures (deck)",
            "intent": "live",
            "path": "/decks/%s" % deck,
            "check": disclosures_ok,
        },
        {
            "name": "deck telemetry",
            "intent": "live",
            "path": "/results/%s/telemetry?deck=%s" % (run, deck),
            # "engine" (the charge-counter and proliferate rows) is gone:
            # WS11 task 8. "decided" is the published denominator.
            "check": has_keys("games", "deck", "watched", "decided"),
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
    ] + flag_surfaces(env) + review_surfaces(env)


# --------------------------------------------------------------------------
# Deployment invariants: configuration and provenance a green surface list
# cannot show. Each returns (ok: bool, detail: str).
# --------------------------------------------------------------------------

NUDGE_FLAG = "MTG_PLAN_FEEDBACK_APPLY"

# The oldest shim a production result may come from. 0.17.0 is the R1 pin:
# the tutoring hotfix behind plan-data flags (G0a PASS), on top of 0.16.0's
# fix for 0.15.0's attack re-ask loop. With version-1 plans it plays as
# 0.16.0 did, so a MTG_PLAN_VERSION=1 rollback still meets it. Raise this with
# every release pin (SIMLAB_SHIM_REF in docker-compose.yml). When compose also
# hands this container a version-tag SIMLAB_SHIM_REF newer than the floor,
# that tag is the bar instead, so a new pin is never checked against an old one.
SHIM_FLOOR = (0, 17, 0)
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
    ("/app/engine/models/rank_checks.json",
     "rank checks per pilot; without it the prediction is withheld on plan runs"),
    ("/app/rules/kb", "the Comprehensive Rules KB the /ask retrieval reads"),
    ("/app/engine/decks", "bundled decks"),
    ("/app/engine/qa/__init__.py",
     "the QA analyzers package; the same top-level glob would miss it"),
    ("/app/engine/qa/knockouts.py",
     "knockouts: analysis.win_method and the scorecards read it"),
    ("/app/engine/qa/run.py",
     "QA layer A: the worker runs it after every finished run (qa.json)"),
    ("/app/engine/qa/review_queue.py",
     "the review queue behind GET /qa/queue and QA's auto flags"),
]

# Modules that must IMPORT in the image, not merely exist on disk. analysis.py
# imports engine/qa/ at module load, so a missing or broken package would take
# /analysis down at request time while every file check above passed. The
# same list is checked in BOTH images: `--files` here in the api container,
# `--image-only` in the worker (which runs qa/run.py after every job).
IMAGE_IMPORTS = ["qa", "qa.context", "qa.knockouts", "qa.tutors", "qa.run",
                 "qa.review_queue", "analysis", "scorecard", "game_story", "board",
                 "validity", "combo_bands", "commanders", "pilot", "predict",
                 # Week 4: the run summary imports standings unguarded (a
                 # missing module is a 500 on every run page), and every
                 # disclosure list, the telemetry exemption and the coach's
                 # cut rule read disclosure.
                 "standings", "disclosure"]

# QA layer A (repair plan WS2 layer A task 6): the newest finished run must
# have a qa.json with no errors. The worker writes it in a detached child
# after the job finishes, so a preflight run straight after a sim can arrive
# first: the check polls for up to QA_WAIT_SECONDS before failing (the
# worker's own ceiling is 120 s; the smoke test's --sim run waits for its
# qa.json too, so after the documented order the wait is normally zero).
QA_SCHEMA = "simlab.qa/1"
QA_WAIT_SECONDS = 150.0
QA_POLL_SECONDS = 5.0


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
        game = None
    try:
        # The whole QA layer A analysis, in memory (nothing is written): the
        # context, every detector and the qa.json assembly.
        from qa import run as qa_run
        doc = qa_run.analyze("sim_00000000_000000_preflight.json",
                             result={"meta": {}, "games": [game]}, load_forge=False)
        kos = ((doc.get("games") or [{}])[0].get("knockouts")) or []
        ok = (doc.get("schema") == QA_SCHEMA and not doc.get("errors")
              and [k.get("cause") for k in kos] == ["combat_damage"])
        if not ok:
            bad += 1
        print("  %-9s qa.run.analyze on a synthetic game: %s, %d error(s)%s" % (
            "ok" if ok else "WRONG", doc.get("analyzer"), len(doc.get("errors") or []),
            "" if not doc.get("errors") else ": %s" % doc["errors"][:2]))
    except Exception as e:  # noqa: BLE001
        bad += 1
        print("  %-9s qa.run.analyze: %s: %s" % ("BROKEN", type(e).__name__, e))
    return bad


def qa_report_ok(base, run, wait=QA_WAIT_SECONDS, poll=QA_POLL_SECONDS,
                 fetch_=None, sleep=None, clock=None):
    """(ok, detail): the probe run (the newest result) has a qa.json with no
    errors, served by GET /results/{run}/qa. A 404 {"qa": "pending"} is
    polled until `wait` runs out, because the worker writes qa.json in a
    detached child after the job finishes (see QA_WAIT_SECONDS)."""
    import time as _time
    fetch_ = fetch_ or fetch
    sleep = sleep or _time.sleep
    clock = clock or _time.monotonic
    deadline = clock() + max(0.0, wait)
    waited = False
    while True:
        st, body = fetch_(base, "/results/%s/qa" % run)
        if st == 200 and isinstance(body, dict) and body.get("schema") == QA_SCHEMA:
            errs = body.get("errors") or []
            if errs:
                shown = "; ".join("[%s] %s" % (e.get("stage"), e.get("error"))
                                  for e in errs[:3] if isinstance(e, dict))
                return False, ("qa.json for %s has %d error(s): %s. Rerun it with "
                               "engine/qa/run.py %s in the worker container to see the "
                               "traceback." % (run, len(errs), shown, run))
            return True, "%s: %s, %d flag(s), no errors%s" % (
                run, body.get("analyzer"), len(body.get("flags") or []),
                " (after waiting for the worker)" if waited else "")
        if st == 200:
            return False, ("GET /results/{file}/qa answered with something that is not a "
                           "qa report: the engine predates QA layer A (R1.1)")
        if st == 404 and isinstance(body, dict) and body.get("qa") == "pending":
            if clock() >= deadline:
                return False, ("no qa.json for %s after waiting %d s. The worker writes "
                               "it after each run and its sweeper backfills; check "
                               "`docker compose logs worker` for 'QA', or run "
                               "engine/qa/run.py %s in the worker container." % (
                                   run, int(wait), run))
            waited = True
            sleep(poll)
            continue
        return False, "HTTP %s: %s" % (st, str(body)[:160])


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
                    help="also check image contents (run inside the container) and "
                         "that the newest run has a clean qa.json")
    ap.add_argument("--image-only", action="store_true",
                    help="only the image contents and imports, no HTTP (the worker "
                         "container, which serves no API)")
    ap.add_argument("--qa-wait", type=float, default=QA_WAIT_SECONDS,
                    help="with --files: seconds to wait for the newest run's qa.json "
                         "(default %(default)s)")
    args = ap.parse_args(argv)

    if args.image_only:
        bad = check_files() + check_imports()
        print()
        if bad:
            print("PREFLIGHT FAILED: %d image check(s) failed." % bad)
            return 1
        print("PREFLIGHT OK: every file and module this image must carry is there and works.")
        return 0

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
            tp, {"swing": 'labelled "Biggest board swing", shim runs only (the '
                          'week-3 audit failed the turning point, 8 of 20; '
                          'studies/knockout_audit/RESULTS.md)',
                 "audited": 'labelled "Turning point" (only after a re-audit passes: '
                            'the week-3 audit failed it, 8 of 20)',
                 "off": "held: not shown"}.get(tp, "?"))))
        print("  %-6s %-30s %s" % ("info", "MTG_KNOCKOUT_DETAIL",
                                   "on: cause and killer shown (the week-3 audit passed "
                                   "knockouts, 39 of 40)" if sw.get("knockout_detail")
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
    if args.files:
        invariants.append(
            ({"name": "newest run has a clean qa.json",
              "note": "QA layer A (R1.1): post-deploy order is smoke_test.py --sim, "
                      "then preflight; the check waits up to --qa-wait seconds"},
             qa_report_ok(args.base, run, wait=args.qa_wait)))
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
