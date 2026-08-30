#!/usr/bin/env python3
"""MTG Rules Engine — backend brains for any front end.

Wraps the rules KB (../rules/kb) and the Forge simulation pipeline behind one
zero-dependency API. Use it three ways:

  1. Python import:      from mtg_engine import Engine; e = Engine(); e.rule("903.10a")
  2. CLI:                python3 mtg_engine.py rule 903.10a
                         python3 mtg_engine.py search "commander damage"
                         python3 mtg_engine.py keyword station
                         python3 mtg_engine.py turn-structure
  3. HTTP (front ends):  python3 mtg_engine.py serve 8484
       GET  /rule/903.10a         exact rule + subrules
       GET  /search?q=trample     scored free-text search
       GET  /keyword/foretell     keyword ability/action entry
       GET  /glossary/monarch     glossary term
       GET  /turn-structure       ordered phases/steps with rules attached
       GET  /health               KB stats
       GET  /decks                deck index; /decks/{file} one deck's cards
       GET  /results              index of adapted sim result files
       GET  /results/{file}       one full sim result (games -> turns -> events)
                                  ?snapshots=1 adds board_snapshot events
       GET  /results/{file}/summary   run without event logs (~KB, not MB)
       GET  /results/{file}/prediction predicted real-playgroup win rates
       GET  /results/{file}/scorecards  per-deck: outcomes, timing, behaviour
       GET  /results/{file}/game/{n}  one game's events
       GET  /results/{file}/telemetry?deck=sub&watch=a|b  win-con telemetry for one deck
       GET  /cards?names=a|b|c    Scryfall card facts (cached); ?fetch=0 for cache-only
       GET  /board/{file}         board-reconstruction accuracy report
       GET  /analysis/{file}      wincon report: win methods, combo assembly/conversion
       GET  /ask?q=...            cached rules answer (never generates)
       GET  /coaching/{file}?deck=x.dck   cached coaching report (never generates)
       POST /simulate             {"decks":[...], "games":N, "deck_dir":"..."} -> sim JSON
                                  (seat-rotated by default, SIM_CALIBRATION.md Bias 1)
       POST /decks                {"name":..., "text":..., "commander"?} -> validated .dck
       POST /ask                  {"q":"..."} -> grounded rules answer (authed, quota'd)
       POST /coaching             {"result_file":..., "deck":...} -> coaching report (authed)
       DELETE /decks/{file}       remove an IMPORTED deck (authed; bundled refuse)
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "rules" / "kb"


def _claim_result(out: str, run_id: str | None, t0: float) -> Path | None:
    """The result file belonging to THIS run, or None.

    Claiming by "newest sim_*.json written since I started" is only correct
    while exactly one process writes to this directory. Add a second worker, a
    duplicate job, or someone running run_sim.py by hand on the box, and the
    window hands this job another run's file — and the job is then marked done
    carrying someone else's win rates, undetectably.

    run_sim.py stamps the job id into the result filename, so match on that.
    Freshness is still required on top of identity: recover_orphans() requeues
    a job under its original id, so a previous attempt's file can be sitting
    right there. No id (a hand-run sim) falls back to the old window, which is
    as good as it can be when there is nothing to match on.
    """
    d = Path(out)
    if run_id:
        safe = re.sub(r"[^A-Za-z0-9-]", "", run_id)[:64]
        cands = list(d.glob(f"sim_*_{safe}.json")) + list(d.glob(f"sim_*_{safe}_rotated.json"))
    else:
        cands = list(d.glob("sim_*.json"))
    fresh = sorted(p for p in cands if p.stat().st_mtime >= t0)
    return fresh[-1] if fresh else None


class Engine:
    def __init__(self, kb_dir: Path | str = KB):
        self.kb = Path(kb_dir)
        self._rules = json.loads((self.kb / "all_rules.json").read_text(encoding="utf-8"))
        self._glossary = json.loads((self.kb / "glossary.json").read_text(encoding="utf-8"))
        mech = json.loads((self.kb / "mechanics.json").read_text(encoding="utf-8"))
        self._keywords = {e["name"].lower(): e for e in mech["keyword_abilities"]}
        self._keywords.update({e["name"].lower(): e for e in mech["keyword_actions"]})
        self._turns = json.loads((self.kb / "turn_structure.json").read_text(encoding="utf-8"))
        self._chunks = None  # lazy — 3,887 lines

    # ---------- lookups ----------

    def rule(self, number: str) -> dict:
        """Exact rule + its direct subrules (903.10 also returns 903.10a...)."""
        number = number.rstrip(".")
        hits = {k: v for k, v in self._rules.items()
                if k == number or re.fullmatch(re.escape(number) + r"[a-z]", k)}
        if not hits:
            return {"error": f"rule {number} not found", "suggestion": self._nearest_rule(number)}
        return {"rule": number, "entries": [
            {"rule": k, "text": v["text"] if isinstance(v, dict) else str(v)} for k, v in sorted(hits.items())
        ]}

    def keyword(self, name: str) -> dict:
        e = self._keywords.get(name.lower().strip())
        return e if e else {"error": f"keyword '{name}' not found",
                            "close": [k for k in self._keywords if name.lower()[:4] in k][:5]}

    def glossary(self, term: str) -> dict:
        for k, v in self._glossary.items():
            if k.lower() == term.lower().strip():
                return {"term": k, **v}
        close = [k for k in self._glossary if term.lower() in k.lower()][:8]
        return {"error": f"term '{term}' not found", "close": close}

    def turn_structure(self) -> dict:
        return self._turns

    def search(self, query: str, k: int = 8) -> list[dict]:
        """Keyword-overlap scored search over the retrieval chunks."""
        if self._chunks is None:
            self._chunks = [json.loads(line) for line in
                            (self.kb / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        words = [w for w in re.findall(r"[a-z0-9']+", query.lower()) if len(w) > 2]
        if not words:
            return []
        scored = []
        for c in self._chunks:
            t = c["text"].lower()
            score = sum(t.count(w) for w in words)
            exact = 3 if query.lower() in t else 0
            if score:
                scored.append((score + exact, c))
        scored.sort(key=lambda x: -x[0])
        return [{"score": s, "id": c["id"], "rule": c.get("rule") or c.get("term"),
                 "text": c["text"][:400]} for s, c in scored[:k]]

    def validate_game_log(self, path: str) -> dict:
        """Check every rule_ref in a training game_log resolves in the KB."""
        log = json.loads(Path(path).read_text(encoding="utf-8"))
        refs, missing = set(), []
        def walk(o):
            if isinstance(o, dict):
                rr = o.get("rule_refs")
                if isinstance(rr, list):  # skip descriptive strings (e.g. schema notes)
                    for r in rr:
                        tok = re.split(r"\s", str(r))[0].strip("?.,;()")
                        if re.match(r"^\d{3}(\.\d+[a-z]?)?$", tok):
                            refs.add(tok)
                        else:
                            refs.add(str(r))  # keep non-numeric refs visible in report
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(log)
        for r in sorted(refs):
            base = r.rstrip(".")
            if base not in self._rules and not any(k.startswith(base) for k in self._rules):
                missing.append(r)
        return {"file": path, "refs_checked": len(refs), "missing": missing, "ok": not missing}

    # ---------- simulation ----------

    def simulate(self, decks: list[str], games: int = 10, deck_dir: str | None = None,
                 fmt: str = "Commander", forge_jar: str | None = None, out: str = "./sim_results",
                 run_id: str | None = None, rotate: bool = True) -> dict:
        import subprocess
        cmd = [sys.executable, str(Path(__file__).parent / "run_sim.py"),
               "--decks", *decks, "--games", str(games), "--format", fmt, "--out", out,
               # Passed explicitly so the clock the timeout maths assumes and
               # the clock the sim runs under cannot drift apart.
               "--clock", str(SIM_CLOCK_SECONDS)]
        if run_id:
            cmd += ["--run-id", run_id]
        if deck_dir:
            cmd += ["--deck-dir", deck_dir]
        if forge_jar:
            cmd += ["--forge-jar", forge_jar]
        # SEAT ROTATION IS THE DEFAULT — SIM_CALIBRATION.md "Bias 1": a fixed
        # seat order gives seat 1 an 11% win rate and seat 4 36%, so an
        # unrotated 4-player result is not a verdict on the deck. Debug-only
        # opt-out (a single fixed-seat run finishes faster to iterate on):
        #   MTG_SIM_ROTATE=0
        if rotate and os.environ.get("MTG_SIM_ROTATE") != "0":
            cmd += ["--rotate"]
        # HUMANIZED IS THE DEFAULT: run_sim's agent defaults to 'auto' (plan
        # agents whenever the shim jar exists, labeled stock fallback
        # otherwise). Deploy-time opt-outs only:
        #   MTG_SIM_HUMANIZE=0    force stock Forge AI
        #   MTG_SIM_HUMANIZE=1    force plan agents (fail loudly if no shim)
        #   MTG_SIM_AGENT=shim    shim with stock AI (typed logs, no plans)
        if os.environ.get("MTG_SIM_HUMANIZE") == "0":
            cmd += ["--agent", "forge"]
        elif os.environ.get("MTG_SIM_HUMANIZE") == "1":
            cmd += ["--humanize"]
        elif os.environ.get("MTG_SIM_AGENT") in ("forge", "shim"):
            cmd += ["--agent", os.environ["MTG_SIM_AGENT"]]
        # A hung JVM must not wedge the worker forever, but the ceiling has to
        # be derived from the work, not guessed. A flat 2 h could not fit the
        # runs the API itself accepts: 16 games at a 900 s clock is 14,400 s
        # worst case, and SIM_MAX_GAMES at the MEASURED median pace is over
        # 10,000 s, so the largest allowed request could not finish (A14).
        rotations = len(decks) if (rotate and os.environ.get("MTG_SIM_ROTATE") != "0") else 1
        timeout = sim_timeout_seconds(games, rotations)
        t0 = time.time()
        killed = False
        # start_new_session: the JVM is a GRANDCHILD (engine -> run_sim -> java),
        # so killing the direct child left a 4 GB JVM running to completion,
        # starving the next job on a 2-vCPU box. The comment this replaces
        # assumed Forge would die on EPIPE at its next stdout write; Java's
        # PrintStream swallows IOExceptions, so it does not (A15). A session of
        # our own means one signal reaches the whole tree.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            out_txt, err_txt = proc.communicate(timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            killed = True
            _kill_process_group(proc)
            try:
                out_txt, err_txt = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                out_txt, err_txt = "", ""
            rc = -1
            err_txt = (err_txt or "") + (
                f"\nsimulation killed after {int(timeout)} s. This is the "
                f"ceiling for {games} game(s) across {rotations} rotation(s); "
                f"override with MTG_SIM_TIMEOUT_SECONDS.")
        out_txt, err_txt = out_txt or "", err_txt or ""

        claimed = _claim_result(out, run_id, t0)
        if claimed is None and killed and run_id:
            # Completed rotations were written to disk before the kill and used
            # to be thrown away wholesale. Re-parse them into a result marked
            # incomplete, so the user keeps the games that did run (A14).
            try:
                import run_sim
                recovered = run_sim.salvage(
                    Path(out), run_id, decks=decks, fmt=fmt,
                    clock=SIM_CLOCK_SECONDS,
                    games_expected=sum(run_sim.plan_games(games, rotations)))
            except Exception as e:  # noqa: BLE001 — salvage must never mask the kill
                recovered = None
                err_txt += f"\nsalvage failed: {e}"
            if recovered is not None:
                claimed = recovered
                err_txt += (f"\nrecovered {len(json.loads(recovered.read_text())['games'])} "
                            f"completed game(s) from the rotations that finished; "
                            f"the result is marked incomplete.")
        payload = None
        if claimed:
            try:
                payload = json.loads(claimed.read_text())
            except Exception:  # noqa: BLE001
                payload = None
        if payload:
            # Outcome feedback: fold this run's decided games into the plan
            # store, so future plans for these decks (and their archetypes)
            # can lean toward how they are OBSERVED to win. Never blocks a
            # result: feedback is an upgrade, not a requirement.
            try:
                import plan_feedback
                plan_feedback.record_run(payload)
            except Exception:  # noqa: BLE001
                pass
        return {"stdout": (out_txt + "\n" + err_txt)[-2000:], "returncode": rc,
                "result_file": str(claimed) if claimed else None,
                "killed": killed, "timeout": timeout,
                # A salvaged result is still a result: hand it back even though
                # rc is nonzero, so the worker can store it as a partial run
                # rather than reporting a total loss.
                "result": payload if (rc == 0 or killed) else None}

    # ---------- helpers ----------

    def _nearest_rule(self, number: str) -> list[str]:
        prefix = number.split(".")[0]
        return [k for k in self._rules if k.startswith(prefix + ".")][:6]

    def stats(self) -> dict:
        return {"rules": len(self._rules), "keywords": len(self._keywords),
                "glossary_terms": len(self._glossary), "kb_dir": str(self.kb)}


# ---------- HTTP server (stdlib only) ----------

BUNDLED_DECKS = Path(__file__).parent / "decks"
# Imported decks go on the shared data volume, NOT into the API's image. The
# worker is a separate container: a deck written inside the API image passes the
# allowlist, enqueues, and then the worker cannot find the file. Both processes
# mount MTG_DATA_DIR, so that is the only place an imported deck is reachable.
IMPORTED_DECKS = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent))) / "decks"


def _deck_dirs() -> list[Path]:
    """Where decks live, in lookup order: imported (shared volume) then bundled."""
    return [IMPORTED_DECKS, BUNDLED_DECKS]


def _find_deck(filename: str) -> Path | None:
    """Resolve a deck filename to a real path, refusing traversal."""
    if filename != Path(filename).name or not filename.endswith(".dck"):
        return None
    for d in _deck_dirs():
        p = d / filename
        if p.is_file():
            return p
    return None


def _list_decks() -> list[dict]:
    import combos
    decks: dict[str, dict] = {}
    for d in _deck_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.dck")):
            if f.name in decks:
                continue          # first match wins: imported shadows bundled
            # AppleDouble sidecars: macOS tar emits "._name.dck" for any file
            # carrying extended attributes, and they extract as real files on
            # Linux. They are binary metadata, not decklists.
            if f.name.startswith("._"):
                continue
            name = f.stem
            try:
                # errors="replace" on purpose: one deck file in a foreign
                # encoding must not take down the whole deck list. This endpoint
                # returned a 500 for all 29 decks because a single unreadable
                # sidecar raised UnicodeDecodeError.
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if line.startswith("Name="):
                    name = line[5:].strip()
                    break
            # Commander name feeds the picker's art tiles; a deck without a
            # [Commander] section honestly reports null (name-only tile).
            try:
                _, commanders = combos.parse_dck(text)
            except Exception:  # noqa: BLE001 — one odd file must not 500 the list
                commanders = []
            decks[f.name] = {"file": f.name, "name": name,
                             "commander": commanders[0] if commanders else None,
                             "source": "imported" if d == IMPORTED_DECKS else "bundled"}
    return [decks[k] for k in sorted(decks)]


def _read_deck_cards(path: Path) -> dict:
    """One deck's contents with counts expanded — what the playtest sandbox
    shuffles. Pure data: no legality, no validation, no rules."""
    name = path.stem
    commanders: list[str] = []
    main: list[str] = []
    section = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if section == "metadata":
            if line.lower().startswith("name="):
                name = line.split("=", 1)[1].strip()
            continue
        m = re.match(r"(\d+)\s+(.+?)(?:\|.*)?$", line)
        if not m:
            continue
        count, card = int(m.group(1)), m.group(2).strip()
        if section == "commander":
            commanders.extend([card] * count)
        elif section == "main":
            main.extend([card] * count)
    # Imported decks are deletable; bundled decks ship inside the image and
    # are not — the front end needs to know which it is looking at.
    source = "imported" if path.parent == IMPORTED_DECKS else "bundled"
    return {"file": path.name, "name": name, "source": source,
            "commanders": commanders, "main": main}


def _queued_count() -> int:
    """How many jobs are waiting or running — the backpressure signal."""
    try:
        import jobqueue
        import sqlite3
        with sqlite3.connect(jobqueue.DB_PATH, timeout=5) as c:
            row = c.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0   # never let a bookkeeping failure block a legitimate request


def _job_status(job_id: str | None) -> dict:
    """Dashboard-friendly view of a queue job (latest job when id is None)."""
    import jobqueue
    job = jobqueue.get(job_id)
    if not job:
        return {"state": "idle"}
    out = {"state": job["state"], "id": job["id"], "decks": job["decks"],
           "games": job["games"], "started": job["started"],
           "elapsed": job.get("elapsed"), "error": job["error"]}
    if job["state"] == "queued":
        # Report the truth. Calling a queued job "running" meant that behind a
        # backlog you watched an elapsed timer tick for a job Forge had not
        # started, with no way to tell the difference.
        out["queued_ahead"] = jobqueue.position(job["id"])
    if job.get("result"):
        out["result"] = job["result"].get("summary")
        out["result_file"] = job["result"].get("result_file")
        if job["result"].get("incomplete"):
            out["incomplete"] = True
            out["warning"] = job["result"].get("warning")
    out["progress"] = _job_progress(job)
    return out


def _job_progress(job: dict) -> dict:
    """How far along, how long this size usually takes, and is it still moving.

    A four-deck gauntlet is tens of minutes of a silent JVM. With only an
    elapsed timer on screen there is no way to tell "still working" from
    "died twenty minutes ago", so people conclude it failed and queue it
    again, which on a 2-vCPU box makes the original slower. Everything here
    exists to answer that one question honestly, including admitting when we
    cannot tell.
    """
    decks = job.get("decks") or []
    requested = job.get("games") or 0
    rotations = max(1, len(decks)) if os.environ.get("MTG_SIM_ROTATE") != "0" else 1
    expected_games = max(requested, rotations)
    if rotations > 1 and expected_games % rotations:
        expected_games += rotations - (expected_games % rotations)
    low, high = estimate_sim_seconds(requested, rotations)
    prog: dict = {
        "expected_games": expected_games,
        "rotations": rotations,
        "typical_seconds": [low, high],
        "ceiling_seconds": int(sim_timeout_seconds(requested, rotations)),
    }
    if job["state"] != "running":
        return prog

    # Games finished so far, counted across EVERY rotation log rather than the
    # current one. The live view resets to "game 1" at each rotation boundary,
    # which on its own reads like the run restarting (audit A28).
    done, last_activity = _count_live_progress(job["id"])
    prog["games_done"] = done
    elapsed = job.get("elapsed") or 0
    prog["elapsed"] = int(elapsed)
    if last_activity is not None:
        prog["seconds_since_activity"] = int(max(0, time.time() - last_activity))
    if done:
        # Pace from THIS run, which beats any stored average: a slow pod is
        # slow for reasons (stax, big boards) that a global constant cannot know.
        per_game = elapsed / done
        prog["seconds_per_game"] = int(per_game)
        prog["eta_seconds"] = int(max(0, (expected_games - done) * per_game))
    # "Slower than usual" is not "broken", and the difference is the whole
    # point: a sim is only suspect when nothing has been WRITTEN for a long
    # time, not when it has simply been running a while.
    stalled_after = max(SIM_CLOCK_SECONDS * 1.5, 600)
    prog["stalled"] = bool(last_activity is not None
                           and prog.get("seconds_since_activity", 0) > stalled_after)
    prog["over_typical"] = bool(elapsed > high)
    return prog


def _count_live_progress(job_id: str) -> tuple[int, float | None]:
    """(finished games across all rotations, mtime of the newest log)."""
    if not _JOB_ID_RE.match(job_id or ""):
        return 0, None
    done = 0
    newest: float | None = None
    patterns = (f"shim_raw_{job_id}*.jsonl", f"forge_raw_{job_id}*.log")
    for pat in patterns:
        for p in RESULTS_DIR.glob(pat):
            try:
                st = p.stat()
            except OSError:
                continue
            newest = st.st_mtime if newest is None else max(newest, st.st_mtime)
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if p.suffix == ".jsonl":
                # One {"rec":"result"} per finished game; counted by substring
                # so a half-written trailing line cannot inflate it.
                done += text.count('"rec": "result"') + text.count('"rec":"result"')
            else:
                done += text.count("Game Result:")
    return done, newest


RESULTS_DIR = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent))) / "sim_results"

# Per-game wall clock the sim runs under (run_sim --clock). Any single game may
# legitimately take this long, so the outer ceiling has to be a multiple of it.
SIM_CLOCK_SECONDS = int(os.environ.get("MTG_SIM_CLOCK_SECONDS", "900"))
# One JVM start per rotation. Measured 25-35 s warm, ~93 s on the first launch
# of a cold container (engine/SIM_PERFORMANCE.md Finding 2); 150 s is a ceiling,
# not an estimate, because this figure only guards against a hang.
JVM_LAUNCH_CEILING_SECONDS = 150
# Typical, not worst case: what a real game costs when it finishes on its own.
# Used ONLY to tell a user how long to expect, never to kill anything.
# 240, not 120 (re-measured 2026-08-28): the plan agent deliberates more than
# the stock AI these figures were first measured on. Across 186 agent-era
# games (cEDH all-plan pods median 272 s, precon mixed pods median 312 s, both
# including a ~35-60 s JVM launch that this constant must exclude) the in-JVM
# game lands at 220-260 s. The old 120 made every healthy run read as stuck at
# double its estimate.
TYPICAL_GAME_SECONDS = 240
TYPICAL_JVM_LAUNCH_SECONDS = 35


def sim_timeout_seconds(games: int, rotations: int) -> float:
    """Outer kill ceiling for one run_sim invocation (audit A14).

    Every game may take the full clock before Forge draws it, so a run of N
    games cannot be given less than N * clock without killing legitimate work.
    That is the whole bug: one flat 7200 s covered ALL rotations, and the
    largest request the API accepts could not finish inside it, losing every
    completed game when the kill landed.

    An explicit MTG_SIM_TIMEOUT_SECONDS still wins, for an operator who knows
    their box, but it is no longer the default.
    """
    override = os.environ.get("MTG_SIM_TIMEOUT_SECONDS")
    if override:
        return float(override)
    rotations = max(1, rotations)
    played = max(games, rotations)          # run_sim rounds up to whole rotations
    return played * SIM_CLOCK_SECONDS + rotations * JVM_LAUNCH_CEILING_SECONDS + 300


def estimate_sim_seconds(games: int, rotations: int) -> tuple[int, int]:
    """(low, high) seconds a run of this size TYPICALLY takes.

    For telling a user what to expect, so a long run does not read as a failed
    one. Deliberately separate from sim_timeout_seconds: that one is a ceiling
    against hangs and is many times larger than any real run.
    """
    rotations = max(1, rotations)
    played = max(games, rotations)
    launches = rotations * TYPICAL_JVM_LAUNCH_SECONDS
    return (int(played * TYPICAL_GAME_SECONDS * 0.6 + launches),
            int(played * TYPICAL_GAME_SECONDS * 1.6 + launches))


def _kill_process_group(proc) -> None:
    """SIGTERM then SIGKILL the whole session, so the JVM goes too (A15)."""
    import signal
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, AttributeError, OSError):
        proc.kill()
        return
    for sig, grace in ((signal.SIGTERM, 10), (signal.SIGKILL, 0)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        if not grace:
            return
        try:
            proc.wait(timeout=grace)
            return
        except Exception:  # noqa: BLE001 — still alive, escalate
            continue

# ---------- deployment configuration (all env-driven; safe local defaults) ----------

# Comma-separated API keys permitted to POST /simulate and /decks. When empty the
# server is OPEN — fine for localhost, never for a public deployment, so serve()
# refuses to bind a non-loopback interface without keys unless explicitly allowed.
API_KEYS = {k.strip() for k in os.environ.get("MTG_API_KEYS", "").split(",") if k.strip()}
ALLOW_ORIGIN = os.environ.get("MTG_ALLOW_ORIGIN", "*")
GZIP_MIN = int(os.environ.get("MTG_GZIP_MIN_BYTES", "1024"))
# Simulations are the expensive resource: a 4GB JVM for 10-60 minutes.
SIM_PER_HOUR = int(os.environ.get("MTG_SIM_PER_HOUR", "6"))
SIM_MAX_GAMES = int(os.environ.get("MTG_SIM_MAX_GAMES", "64"))
SIM_MAX_QUEUED = int(os.environ.get("MTG_SIM_MAX_QUEUED", "3"))
READ_PER_MIN = int(os.environ.get("MTG_READ_PER_MIN", "240"))
# Rules-assistant generation is the only paid-token path besides coaching;
# GET /ask is cache-only so crawlers can never spend money.
ASK_PER_HOUR = int(os.environ.get("MTG_ASK_PER_HOUR", "30"))
COACH_PER_HOUR = int(os.environ.get("MTG_COACH_PER_HOUR", "20"))
ALLOW_OPEN_PUBLIC = os.environ.get("MTG_ALLOW_OPEN_PUBLIC", "0") == "1"

_rate_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def _bearer(header: str) -> str:
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def _rate_ok(bucket: str, limit: int, window: float) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, retry_after_seconds).

    In-process by design: one API container is the documented topology. Running
    several replicas needs a shared store (see deploy_plan.md).
    """
    now = time.time()
    with _rate_lock:
        hits = [t for t in _hits.get(bucket, []) if now - t < window]
        if len(hits) >= limit:
            _hits[bucket] = hits
            return False, max(1, int(window - (now - hits[0])))
        hits.append(now)
        _hits[bucket] = hits
        return True, 0


def _list_results() -> list[dict]:
    """Index of adapted sim result files, newest first.

    Carries the provenance every list surface needs to tell runs apart (audit
    A26): whether the run was seat-rotated, which agent piloted it, and the
    validity verdict from validity.py (A25). Without these the index was a list
    of interchangeable-looking files, so no front end COULD flag a seat-biased
    or clock-polluted run even if it wanted to — the 7/31-8/2 rotation-off
    window was indistinguishable from a good run in every listing.
    """
    import validity
    out = []
    for f in sorted(RESULTS_DIR.glob("sim_*.json"), reverse=True):
        entry = {"file": f.name, "bytes": f.stat().st_size,
                 "modified": int(f.stat().st_mtime)}
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            meta = d.get("meta", {})
            entry["decks"] = meta.get("decks", [])
            entry["games"] = len(d.get("games", []))
            entry["summary"] = d.get("summary")
            # NOT meta.source verbatim: on a non-rotated run that field holds
            # the full java command line, absolute home paths and all, which
            # has no business in an API response. The only thing a list surface
            # needs from it is whether the run was rotated.
            entry["rotated"] = meta.get("source") == "rotated"
            entry["humanized"] = meta.get("humanized")
            entry["agent"] = meta.get("agent")
            v = validity.assess(d)
            entry["validity"] = {"quality": v["quality"], "flags": v["flags"],
                                 "usable_for_ranking": v["usable_for_ranking"],
                                 "reasons": v["reasons"]}
        except Exception as e:  # noqa: BLE001 — surface bad files in the index
            entry["error"] = f"unreadable: {e}"
        out.append(entry)
    return out


def _read_result(name: str, snapshots: bool = False) -> dict:
    """One full sim result JSON by bare filename (no path traversal).

    With snapshots=True, board.py adds an end-of-turn board_snapshot event to each
    turn. That reconstruction is inference (Forge logs no battlefield entries), so
    meta.board_snapshots records how it was derived.
    """
    if name != Path(name).name or not name.endswith(".json"):
        raise ValueError("bad result filename")
    f = RESULTS_DIR / name
    if not f.is_file():
        raise FileNotFoundError(name)
    data = json.loads(f.read_text(encoding="utf-8"))
    if snapshots and "board_snapshots" not in data.get("meta", {}):
        import board
        data = board.annotate(data, fetch=False)  # cache-only: never blocks a request
    # Attached in memory, never written back: the verdict is derived from the
    # current rules in validity.py, so baking it into the file would freeze a
    # judgement that is supposed to be recomputed when those rules improve.
    import validity
    data["validity"] = validity.assess(data)
    return data


def _read_result_summary(name: str) -> dict:
    """A run without its event logs — what the results page actually needs.

    A full run file averages 2.6 MB and reaches 5.7 MB; the summary is a few KB,
    so the results table no longer costs a multi-megabyte download.
    """
    from scorecard import true_round
    data = _read_result(name)
    games = []
    for i, g in enumerate(data.get("games", []), 1):
        turns = g.get("turns", [])
        games.append({
            "n": i,
            "players": g.get("players", []),
            "result": g.get("result"),
            "turns": len(turns),
            "ended_turn": turns[-1].get("turn") if turns else None,
            # Table rounds, the unit a Magic player counts in. ended_turn is
            # Forge's per-player counter and reads ~4x high to a person.
            "ended_round": true_round(g),
            "events": sum(len(t.get("events", [])) for t in turns),
        })
    return {"meta": data.get("meta", {}), "summary": data.get("summary"),
            "games": games, "file": name, "validity": data.get("validity")}


def _read_result_scorecards(name: str) -> dict:
    """Per-deck scorecards: what each deck DID, not just whether it won.

    Small by construction (a few KB for a 4-deck run) because it carries
    aggregates, never event logs. The behaviour sections are absent for runs
    older than shim 0.9.0, and absent is not zero -- the UI must say so.
    """
    from scorecard import scorecards
    return scorecards(_read_result(name))


def _read_result_prediction(name: str) -> dict:
    """Predicted REAL-PLAYGROUP win rate per deck in a finished run.

    The sim's own win rate is not the number a player wants. Measured on 66
    precons against 10,982 real playgroup games, stock Forge spans a wider
    range than humans do and inflates weak decks most; one measured cause is
    that it blocks 14.7% of attacking creatures, so ~85% get through and any
    deck that wins by attacking looks better than it is.

    Returns the corrected number, an interval from the model's out-of-sample
    error, and a plain-language explanation. Degrades honestly: if no model
    has been fitted, or a deck file cannot be found, it says so rather than
    inventing a figure.
    """
    data = _read_result(name)
    summary = data.get("summary") or {}
    rates = summary.get("win_rates") or {}
    try:
        from predict import Predictor, deck_features
    except Exception as e:  # pragma: no cover - import guard
        return {"file": name, "available": False, "reason": f"predict unavailable: {e}"}
    model = Predictor.load()
    if model is None:
        return {"file": name, "available": False,
                "reason": "no fitted model; run studies/precon_predict/analyze.py"}
    decks = []
    for deck, rate in sorted(rates.items()):
        row = {"deck": deck, "sim_win_rate": round(100.0 * rate, 1)}
        path = _find_deck(deck) or _find_deck(deck + ".dck")
        if not path:
            row.update(available=False, reason="deck file not found")
            decks.append(row)
            continue
        try:
            vals = deck_features(path)
            vals["sim"] = 100.0 * rate
            row.update(model.predict(vals), available=True,
                       explanation=model.explain(vals))
        except Exception as e:
            row.update(available=False, reason=str(e))
        decks.append(row)
    return {"file": name, "available": True, "decks": decks,
            "model": {"features": model.features,
                      "basis": model.m.get("ground_truth"),
                      "trained_on_decks": model.m.get("n_decks"),
                      "human_games": model.m.get("human_games")}}


def _read_result_telemetry(name: str, deck: str, watch: list[str] | None = None) -> dict:
    """Win-condition telemetry for one deck in one result.

    Derived from an immutable file and deterministic for a given query string,
    so the route serves it with the same immutable cache header as its sibling
    summary/game payloads. Goes through _read_result() — the path-traversal
    guard lives there and this must stay on that single path.
    """
    data = _read_result(name)
    import deck_telemetry
    report = deck_telemetry.compute(data, deck, watch)
    report["file"] = name
    report["decks"] = data.get("meta", {}).get("decks", [])
    return report


def _read_result_game(name: str, n: int, snapshots: bool = False) -> dict:
    """One game out of a run — the payload a replay actually needs."""
    data = _read_result(name, snapshots=snapshots)
    games = data.get("games", [])
    if n < 1 or n > len(games):
        raise IndexError(f"game {n} not in {name} (has {len(games)})")
    return {"meta": data.get("meta", {}), "file": name, "n": n,
            "games_total": len(games), "game": games[n - 1]}


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _read_live(job_id: str, n: int | None = None) -> dict:
    """GET /sim-live — the game currently being played, from the partial log.

    A stock-Forge run streams stdout to forge_raw_<job_id>.log; a shim run
    (humanized is the default agent) streams typed JSONL to
    shim_raw_<job_id>.jsonl instead. Both parsers are pure functions over
    whatever prefix exists so far, so "watching live" is just parsing the
    partial file: the trailing game has no result yet and comes back with the
    turns played up to this instant.

    A rotated run (the default — SIM_CALIBRATION.md) is several sub-runs, one
    JVM per seat order, and each writes its own <id>_rot<i> file rather than
    one continuous log; run_sim.py names them predictably so this can glob for
    the newest one, which is always the rotation currently in flight. Progress
    resets to game 1 at each rotation boundary — a live view, not a summary.

    Shaped like /results/{file}/game/{n} so the front end can reuse the same
    timeline fold for a live game and a finished one.
    """
    if not _JOB_ID_RE.match(job_id or ""):
        raise ValueError("bad job id")            # keeps the id out of path building
    f = RESULTS_DIR / f"forge_raw_{job_id}.log"
    j = RESULTS_DIR / f"shim_raw_{job_id}.jsonl"
    if not f.is_file():
        rots = sorted(RESULTS_DIR.glob(f"forge_raw_{job_id}_rot*.log"),
                      key=lambda p: p.stat().st_mtime)
        if rots:
            f = rots[-1]
    if not j.is_file():
        rots = sorted(RESULTS_DIR.glob(f"shim_raw_{job_id}_rot*.jsonl"),
                      key=lambda p: p.stat().st_mtime)
        if rots:
            j = rots[-1]
    if f.is_file():
        from forge_log_adapter import parse_forge_log
        text = f.read_text(encoding="utf-8", errors="replace")
        parsed = parse_forge_log(text, source="live")
    elif j.is_file():
        # parse_shim_jsonl skips a truncated trailing line, so reading a file
        # the shim is mid-write is safe.
        from shim_log_adapter import parse_shim_jsonl
        text = j.read_text(encoding="utf-8", errors="replace")
        parsed = parse_shim_jsonl(text, source="live")
    else:
        raise FileNotFoundError("no live log for this job yet")
    games = parsed.get("games") or []
    if not games:
        # Forge is still loading its card database; nothing has been played yet.
        return {"job_id": job_id, "games_done": 0, "n": 0, "game": None,
                "in_progress": True, "bytes": len(text)}

    # Clamp rather than 404. A viewer plays games back in order while Forge runs
    # ahead of it, so it asks for game N as a matter of course before N exists;
    # that is a normal race, not a bad request. games_seen tells it where it is.
    idx = len(games) if n is None else max(1, min(n, len(games)))
    game = dict(games[idx - 1])
    live = game.get("result") is None
    if live:
        # The client's types require a result object; say plainly it is unfinished
        # rather than inventing a winner.
        game["result"] = {"winner": None, "draw": False, "duration_ms": 0, "raw": ""}
    game["n"] = idx
    return {"job_id": job_id, "games_done": sum(1 for g in games if g.get("result")),
            "n": idx, "games_seen": len(games), "game": game,
            "in_progress": live, "bytes": len(text)}


def _read_analysis(name: str, fetch: bool = True) -> dict:
    """GET /analysis/{file} — wincon report for a finished run.

    Result files never change, so the report is computed once and cached beside
    them ("analysis_<file>"; _list_results globs sim_*.json, so no collision).
    First computation may make one Spellbook POST per previously-unseen deck;
    everything after that is disk reads.
    """
    result = _read_result(name)          # validates the name against traversal
    import analysis
    cache = RESULTS_DIR / f"analysis_{name}"
    src = RESULTS_DIR / name
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        # The maths and payload evolve; a cached report from an older analysis
        # version silently serving the old shape is worse than recomputing.
        if cached.get("version") == analysis.ANALYSIS_VERSION:
            return cached
    result.setdefault("file", name)
    rep = analysis.analyse(result, fetch=fetch)
    try:
        cache.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass                              # read-only volume: serve uncached
    return rep


def _deck_combos(content: str) -> dict:
    """Combo block for an import response. Never fatal — the deck is already
    saved, and 'unknown' is an honest answer when Spellbook is unreachable."""
    try:
        import combos
        main, commanders = combos.parse_dck(content)
        found = combos.find_combos(main, commanders)
        if found is None:
            return {"status": "unknown"}
        # "One card away": which single add unlocks the most known combos. The
        # deck's own names, normalized, subtracted from each almost-combo's
        # card list leave exactly the missing piece.
        import cards
        def norm(n: str) -> str:
            return cards.normalize_name(n.split(" // ")[0]).lower()
        have = {norm(n) for n, _ in main} | {norm(n) for n in commanders}
        by_missing: dict = {}
        for c in found["almost_included"]:
            missing = [n for n in c["cards"] if norm(n) not in have]
            if len(missing) != 1:
                continue          # colour-identity or multi-card gaps: not a swap
            slot = by_missing.setdefault(missing[0], {
                "missing": missing[0], "unlocks": 0,
                "example": c["cards"], "produces": c["produces"][:3]})
            slot["unlocks"] += 1
        one_away = sorted(by_missing.values(), key=lambda x: -x["unlocks"])[:6]
        return {"status": "ok",
                "included": found["included"],
                "almost_included": len(found["almost_included"]),
                "one_away": one_away}
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"combo lookup skipped: {e}\n")
        return {"status": "unknown"}


def _cards_lookup(names: list[str], fetch: bool = True) -> dict:
    """Scryfall facts for the UI: type lines, P/T, mana cost, oracle text, art."""
    import cards
    found = cards.get_many(names, fetch=fetch)
    return {"cards": found,
            "missing": sorted({cards.normalize_name(n) for n in names
                               if cards.normalize_name(n) not in found
                               and not cards.is_token(n)}),
            "cache": cards.stats()}


def _import_deck(payload: dict) -> dict:
    """POST /decks — convert a pasted list via convert_decklist.convert().

    Tolerant by contract: hard parse failures come back as {"ok": false, "error"},
    never a 500; the caller's text is never modified (fixes are suggestions)."""
    from convert_decklist import convert
    text = payload.get("text", "")
    name = (payload.get("name") or "").strip() or "Imported Deck"
    commander = payload.get("commander") or None
    try:
        content, report = convert(text, name, commander)
    except SystemExit as e:  # convert() sys.exit()s on hard failures
        return {"ok": False, "error": str(e)}
    # Name-only slugs collide: two callers importing "Zombies" overwrite each
    # other. Suffix with a content hash so distinct lists get distinct files and
    # re-importing the same list is idempotent.
    import hashlib
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "deck"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    slug = f"{base}_{digest}.dck"
    saved = bool(payload.get("save", True))
    if saved:
        IMPORTED_DECKS.mkdir(parents=True, exist_ok=True)
        (IMPORTED_DECKS / slug).write_text(content, encoding="utf-8")
    return {"ok": True, "file": slug, "saved": saved, "report": report,
            "cards_cached": _warm_card_cache(content),
            "combos": _deck_combos(content)}


def _deck_card_names(dck: str) -> list[str]:
    """Card names out of a .dck body — the "N Name" lines under [Commander]/[Main]."""
    names, section = [], ""
    for line in dck.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.lower()
            continue
        if section not in ("[commander]", "[main]"):
            continue
        m = re.match(r"^\d+\s+(.+)$", line)
        if m:
            names.append(m.group(1).strip())
    return names


def _warm_card_cache(dck: str) -> int:
    """Pull every card in a freshly imported deck into the Scryfall cache.

    Import is the one moment we know the full card list before anyone needs it,
    so it is the cheapest place to pay for art and type lines: ~100 names is two
    batched /cards/collection calls, and it means the replay tabletop and the
    board's type grouping render from a warm cache instead of fetching mid-scrub.
    Never fatal — the deck is already written, and every consumer of card facts
    degrades to names only.
    """
    try:
        import cards
        return cards.fetch_missing(_deck_card_names(dck))
    except Exception as e:  # noqa: BLE001 — Scryfall down must not fail an import
        sys.stderr.write(f"card cache warm skipped: {e}\n")
        return 0


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>MTG Engine</title><style>
body{font-family:-apple-system,Segoe UI,sans-serif;background:#14171c;color:#e6e6e6;max-width:760px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.3rem} .card{background:#1d2129;border:1px solid #2c313c;border-radius:10px;padding:1rem;margin:1rem 0}
label.deck{display:block;padding:.35rem .5rem;border-radius:6px;cursor:pointer} label.deck:hover{background:#262b36}
button{background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:.6rem 1.4rem;font-size:1rem;cursor:pointer}
button:disabled{background:#555} input[type=number]{width:5rem;background:#262b36;color:#fff;border:1px solid #3a404d;border-radius:6px;padding:.4rem}
table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #2c313c;padding:.45rem;text-align:left}
.bar{background:#3b82f6;height:10px;border-radius:5px} #status{color:#9aa4b2} .err{color:#f87171;white-space:pre-wrap}
</style></head><body>
<h1>&#9876;&#65039; MTG Engine &mdash; Deck Simulator</h1>
<div class="card"><b>Pick 2&ndash;4 decks</b><div id="decks">loading&hellip;</div></div>
<div class="card">Games: <input id="games" type="number" value="10" min="1" max="200">
&nbsp;<button id="run" onclick="runSim()">Run simulation</button> <span id="status"></span></div>
<div class="card" id="results" style="display:none"></div>
<div class="card"><b>Rules lookup</b><br><input id="q" style="width:70%" placeholder="e.g. 903.10a or 'commander damage'">
<button onclick="lookup()">Search</button><pre id="ruleout" style="white-space:pre-wrap"></pre></div>
<script>
async function load(){const d=await(await fetch('/decks')).json();
document.getElementById('decks').innerHTML=d.map(x=>`<label class="deck"><input type="checkbox" value="${x.file}"> ${x.name} <span style="color:#9aa4b2">(${x.file})</span></label>`).join('');}
async function runSim(){const decks=[...document.querySelectorAll('#decks input:checked')].map(c=>c.value);
if(decks.length<2||decks.length>4){alert('Pick 2-4 decks');return}
document.getElementById('run').disabled=true;
const rsp=await(await fetch('/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decks,games:+document.getElementById('games').value})})).json();
poll(rsp.job_id);}
async function poll(id){const s=await(await fetch('/sim-status'+(id?'?id='+id:''))).json();const st=document.getElementById('status');
if(s.state==='running'){st.textContent=`running ${s.games||''} game(s)… ${s.started?Math.round((Date.now()/1000)-s.started)+'s':'queued'}`;setTimeout(()=>poll(id),4000);}
else if(s.state==='done'){st.textContent=`done in ${s.elapsed}s`;document.getElementById('run').disabled=false;show(s);}
else if(s.state==='error'){st.innerHTML='<span class="err">'+(s.error||'failed')+'</span>';document.getElementById('run').disabled=false;}
else st.textContent='';}
function show(s){const r=s.result;const el=document.getElementById('results');el.style.display='block';
const rows=Object.entries(r.win_rates).sort((a,b)=>b[1]-a[1]).map(([p,w])=>
`<tr><td>${p.replace(/^Ai\\(\\d+\\)-/,'')}</td><td>${r.wins[p]}</td><td style="width:45%"><div class="bar" style="width:${w*100}%"></div></td><td>${(w*100).toFixed(0)}%</td></tr>`).join('');
el.innerHTML=`<b>${r.games} games, ${r.draws} draws</b><table><tr><th>Deck</th><th>Wins</th><th></th><th>Rate</th></tr>${rows}</table>
<small style="color:#9aa4b2">full event log: ${s.result_file||''}</small>`;}
async function lookup(){const q=document.getElementById('q').value.trim();if(!q)return;
const url=/^\\d{3}(\\.|$)/.test(q)?'/rule/'+encodeURIComponent(q):'/search?q='+encodeURIComponent(q);
document.getElementById('ruleout').textContent=JSON.stringify(await(await fetch(url)).json(),null,1);}
load();poll();
</script></body></html>"""


def serve(port: int = 8484) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs, unquote

    engine = Engine()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"   # keep-alive; requires accurate Content-Length

        # ---- request context ----
        @property
        def client_key(self) -> str:
            """Identity for rate limiting: credential when present, else client IP.

            Hashed in full, never truncated. A prefix would collapse callers into
            one bucket the moment credentials share a prefix — every RS256 JWT
            from the same issuer starts with the same base64 header, so
            `token[:12]` would give all authenticated users a single shared quota.
            """
            k = _bearer(self.headers.get("Authorization", "")) or self.headers.get("X-Api-Key", "")
            if k:
                import hashlib
                return "key:" + hashlib.sha256(k.encode()).hexdigest()[:16]
            return f"ip:{self.client_address[0]}"

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
            if ALLOW_ORIGIN != "*":
                self.send_header("Vary", "Origin")

        def _send(self, obj, code=200, cache: str | None = None):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            enc = None
            # Results and card payloads are large and highly compressible.
            if len(body) > GZIP_MIN and "gzip" in self.headers.get("Accept-Encoding", ""):
                import gzip as _gz
                body, enc = _gz.compress(body, 6), "gzip"
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if enc:
                self.send_header("Content-Encoding", enc)
            self._cors()
            if cache:
                self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # client navigated away mid-download; not an error worth logging

        def _send_html(self, html: str):
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # ---- gates ----
        def _authed(self) -> bool:
            """True when the caller may perform expensive/writing operations."""
            if not API_KEYS:
                return True   # open mode; serve() has already warned about this
            key = _bearer(self.headers.get("Authorization", "")) or \
                self.headers.get("X-Api-Key", "")
            return key in API_KEYS

        def _deny(self, code: int, msg: str, retry: int = 0):
            if retry:
                self.send_response(code)
                self.send_header("Retry-After", str(retry))
                self.send_header("Content-Type", "application/json")
                self._cors()
                body = json.dumps({"error": msg, "retry_after": retry}).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._send({"error": msg}, code)

        def do_GET(self):
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.strip("/").split("/") if p]
            q = parse_qs(u.query)
            ok, retry = _rate_ok(f"read:{self.client_key}", READ_PER_MIN, 60.0)
            if not ok:
                return self._deny(429, "too many requests", retry)
            try:
                if not parts:
                    return self._send_html(DASHBOARD_HTML)
                if parts[0] == "health":
                    return self._send(engine.stats())
                if parts[0] == "decks":
                    if len(parts) > 1:
                        # _find_deck refuses traversal; imported shadows bundled.
                        p = _find_deck(parts[1])
                        if p is None:
                            return self._send({"error": "no such deck"}, 404)
                        return self._send(_read_deck_cards(p))
                    return self._send(_list_decks())
                if parts[0] == "sim-status":
                    return self._send(_job_status(q.get("id", [None])[0]))
                if parts[0] == "sim-live":
                    raw_n = q.get("game", [None])[0]
                    try:
                        return self._send(_read_live(q.get("id", [""])[0],
                                                     int(raw_n) if raw_n else None))
                    except FileNotFoundError as e:
                        return self._send({"error": str(e)}, 404)
                    except (IndexError, ValueError) as e:
                        return self._send({"error": str(e)}, 400)
                if parts[0] == "rule" and len(parts) > 1:
                    return self._send(engine.rule(parts[1]))
                if parts[0] == "keyword" and len(parts) > 1:
                    return self._send(engine.keyword(parts[1]))
                if parts[0] == "glossary" and len(parts) > 1:
                    return self._send(engine.glossary(parts[1]))
                if parts[0] == "turn-structure":
                    return self._send(engine.turn_structure())
                if parts[0] == "search":
                    return self._send(engine.search(q.get("q", [""])[0], int(q.get("k", ["8"])[0])))
                if parts[0] == "ask":
                    # Cache-only read: never generates, so a crawler cannot
                    # spend tokens on GETs. POST /ask (authed) generates.
                    question = q.get("q", [""])[0].strip()
                    if not question:
                        return self._send({"error": "pass ?q=<question>"}, 400)
                    import rules_qa
                    stored = rules_qa.cached_answer(question)
                    if stored is not None:
                        return self._send(stored)
                    return self._send({
                        "ok": False, "reason": "not generated",
                        "hits": rules_qa.retrieve(question, engine=engine)})
                if parts[0] == "results":
                    if len(parts) == 1:
                        return self._send(_list_results())
                    snaps = q.get("snapshots", ["0"])[0] not in ("0", "", "false")
                    IMMUTABLE = "public, max-age=31536000, immutable"  # results never change
                    try:
                        # /results/{file}/game/{n} — one game, not the whole run
                        if len(parts) >= 4 and parts[2] == "game":
                            return self._send(
                                _read_result_game(parts[1], int(parts[3]), snapshots=snaps),
                                cache=IMMUTABLE)
                        if len(parts) >= 3 and parts[2] == "summary":
                            return self._send(_read_result_summary(parts[1]), cache=IMMUTABLE)
                        if len(parts) >= 3 and parts[2] == "prediction":
                            return self._send(_read_result_prediction(parts[1]),
                                              cache=IMMUTABLE)
                        if len(parts) >= 3 and parts[2] == "scorecards":
                            return self._send(_read_result_scorecards(parts[1]),
                                              cache=IMMUTABLE)
                        # /results/{file}/telemetry?deck=sub&watch=a|b|c
                        if len(parts) >= 3 and parts[2] == "telemetry":
                            deck = q.get("deck", [""])[0].strip()
                            if not deck:
                                return self._send(
                                    {"error": "pass ?deck=<deck substring>"}, 400)
                            raw_watch = q.get("watch", [""])[0]
                            watch = [w.strip() for w in raw_watch.split("|") if w.strip()]
                            return self._send(
                                _read_result_telemetry(parts[1], deck, watch),
                                cache=IMMUTABLE)
                        return self._send(_read_result(parts[1], snapshots=snaps),
                                          cache=IMMUTABLE)
                    except FileNotFoundError:
                        return self._send({"error": "no such result"}, 404)
                    except (IndexError, ValueError) as e:
                        return self._send({"error": str(e)}, 404)
                if parts[0] == "cards":
                    raw = q.get("names", [""])[0]
                    names = [n for n in re.split(r"[|\n]", raw) if n.strip()]
                    if not names:
                        return self._send({"error": "pass ?names=a|b|c"}, 400)
                    fetch = q.get("fetch", ["1"])[0] not in ("0", "", "false")
                    return self._send(_cards_lookup(names, fetch=fetch))
                if parts[0] == "analysis" and len(parts) > 1:
                    fetch = q.get("fetch", ["1"])[0] not in ("0", "", "false")
                    try:
                        # No immutable header: the report is versioned and can be
                        # recomputed with new maths for the same result file. A
                        # client that pinned v1 forever kept rendering it after
                        # the engine moved to v2. Computation is disk-cached
                        # server-side, so serving it fresh is cheap.
                        return self._send(_read_analysis(parts[1], fetch=fetch))
                    except (FileNotFoundError, ValueError):
                        # ValueError is the traversal guard — same 404 as /results.
                        return self._send({"error": "no such result"}, 404)
                if parts[0] == "coaching" and len(parts) > 1:
                    # Cache-only read; POST /coaching (authed) generates.
                    deck = q.get("deck", [""])[0].strip()
                    if not deck:
                        return self._send({"error": "pass ?deck=<deck.dck>"}, 400)
                    import coach
                    stored = coach.cached_report(parts[1], deck)
                    if stored is not None:
                        return self._send(stored)
                    return self._send({"ok": False, "reason": "not generated"})
                if parts[0] == "board" and len(parts) > 1:
                    import board
                    try:
                        return self._send(board.validate(_read_result(parts[1]), fetch=False))
                    except FileNotFoundError:
                        return self._send({"error": "no such result"}, 404)
                return self._send({"error": "unknown endpoint"}, 404)
            except Exception as e:  # noqa: BLE001
                return self._send({"error": str(e)}, 500)

        def do_POST(self):
            u = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            try:
                route = u.path.strip("/")
                if route in ("simulate", "decks", "ask", "coaching") and not self._authed():
                    return self._deny(401, "an API key is required for this endpoint")

                if route == "coaching":
                    result_file = str(payload.get("result_file") or "").strip()
                    deck = str(payload.get("deck") or "").strip()
                    if not result_file or not deck:
                        return self._send(
                            {"error": "pass {\"result_file\": ..., \"deck\": ...}"}, 400)
                    if _find_deck(deck) is None:
                        return self._send({"error": f"unknown deck: {deck}"}, 400)
                    ok, retry = _rate_ok(f"coach:{self.client_key}",
                                         COACH_PER_HOUR, 3600.0)
                    if not ok:
                        return self._deny(
                            429, f"coaching quota is {COACH_PER_HOUR}/hour", retry)
                    import coach
                    try:
                        return self._send(coach.report(result_file, deck))
                    except (FileNotFoundError, ValueError):
                        return self._send({"error": "no such result"}, 404)

                if route == "ask":
                    question = str(payload.get("q") or "").strip()
                    if not question:
                        return self._send({"error": "pass {\"q\": \"...\"}"}, 400)
                    if len(question) > 500:
                        return self._send(
                            {"error": "question too long (500 chars max)"}, 413)
                    ok, retry = _rate_ok(f"ask:{self.client_key}", ASK_PER_HOUR, 3600.0)
                    if not ok:
                        return self._deny(
                            429, f"ask quota is {ASK_PER_HOUR}/hour", retry)
                    import rules_qa
                    return self._send(rules_qa.answer(question, engine=engine))

                if route == "simulate":
                    import jobqueue
                    decks = payload.get("decks") or []
                    games = int(payload.get("games") or 0)
                    # Validate before spending anything: each job is a 4GB JVM for
                    # 10-60 minutes, so the cheap checks come first.
                    if not 2 <= len(decks) <= 4:
                        return self._send({"error": "pick 2 to 4 decks"}, 400)
                    unknown = [d for d in decks if _find_deck(d) is None]
                    if unknown:
                        return self._send({"error": f"unknown decks: {unknown}"}, 400)
                    if not 1 <= games <= SIM_MAX_GAMES:
                        return self._send(
                            {"error": f"games must be 1..{SIM_MAX_GAMES}"}, 400)
                    queued = _queued_count()
                    if queued >= SIM_MAX_QUEUED:
                        return self._deny(
                            503, f"{queued} simulations already queued; try later", 120)
                    ok, retry = _rate_ok(f"sim:{self.client_key}", SIM_PER_HOUR, 3600.0)
                    if not ok:
                        return self._deny(
                            429, f"simulation quota is {SIM_PER_HOUR}/hour", retry)
                    # Tell the worker where each deck actually lives. Imported
                    # decks are on the shared volume, not in the worker's image.
                    resolved = {d: _find_deck(d) for d in decks}
                    dirs = {str(p.parent) for p in resolved.values() if p}
                    job: dict = {"decks": decks, "games": games}
                    if len(dirs) == 1:
                        job["deck_dir"] = dirs.pop()
                    else:
                        # Mixed bundled/imported: pass absolute paths instead.
                        job["decks"] = [str(resolved[d]) for d in decks]
                    job_id = jobqueue.enqueue(job)
                    # Set the expectation at the point of asking, not after
                    # twenty silent minutes. Also states the played count,
                    # which is rounded up to whole seat rotations and has
                    # never matched the requested number (audit A27).
                    rots = max(1, len(decks)) if os.environ.get("MTG_SIM_ROTATE") != "0" else 1
                    played = max(games, rots)
                    if rots > 1 and played % rots:
                        played += rots - (played % rots)
                    low, high = estimate_sim_seconds(games, rots)
                    return self._send({"ok": True, "job_id": job_id, "state": "queued",
                                       "games_requested": games,
                                       "games_to_play": played,
                                       "rotations": rots,
                                       "typical_seconds": [low, high]})

                if route == "decks":
                    ok, retry = _rate_ok(f"imp:{self.client_key}", 30, 3600.0)
                    if not ok:
                        return self._deny(429, "deck-import quota is 30/hour", retry)
                    if len(payload.get("text", "")) > 100_000:
                        return self._send({"error": "decklist too large"}, 413)
                    return self._send(_import_deck(payload))
                return self._send({"error": "unknown endpoint"}, 404)
            except Exception as e:  # noqa: BLE001
                return self._send({"error": str(e)}, 500)

        def do_DELETE(self):
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.strip("/").split("/") if p]
            try:
                if len(parts) == 2 and parts[0] == "decks":
                    # Destructive and writing: same gate as the other writes.
                    if not self._authed():
                        return self._deny(
                            401, "an API key is required for this endpoint")
                    p = _find_deck(parts[1])
                    if p is None:
                        return self._send({"error": "no such deck"}, 404)
                    if p.parent != IMPORTED_DECKS:
                        # Bundled decks live inside the image; deleting them
                        # would silently reappear on the next deploy.
                        return self._send(
                            {"error": "bundled decks cannot be deleted, "
                                      "only imported ones"}, 400)
                    p.unlink()
                    return self._send({"ok": True, "deleted": parts[1]})
                return self._send({"error": "unknown endpoint"}, 404)
            except Exception as e:  # noqa: BLE001
                return self._send({"error": str(e)}, 500)

        def do_OPTIONS(self):  # CORS preflight for cross-origin front ends
            self.send_response(204)
            # Same origin policy as the real responses. Hardcoding "*" here let a
            # deployment that set MTG_ALLOW_ORIGIN preflight from any origin.
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            # Authorization and X-Api-Key must be listed or the browser drops the
            # header before the request is sent: _authed() would then see no
            # credential and 401 every keyed POST from the front end.
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, Authorization, X-Api-Key")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()

        def log_message(self, fmt, *args):  # quieter default
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # Check the bind posture BEFORE starting a worker, so a refusal costs nothing.
    # Binding a public interface with no API keys turns POST /simulate into a free
    # compute faucet (a 4GB JVM per request). Refuse by default; MTG_ALLOW_OPEN_PUBLIC=1
    # is the deliberate override for a trusted private network.
    host = os.environ.get("MTG_BIND", "0.0.0.0")
    public = host not in ("127.0.0.1", "localhost", "::1")
    if public and not API_KEYS and not ALLOW_OPEN_PUBLIC:
        sys.exit(
            f"refusing to bind {host}:{port} with no API keys.\n"
            "  set MTG_API_KEYS=key1,key2  (recommended), or\n"
            "  set MTG_BIND=127.0.0.1 for local-only, or\n"
            "  set MTG_ALLOW_OPEN_PUBLIC=1 to override on a trusted network."
        )
    import worker
    worker.ensure_embedded()  # no-op when MTG_EMBEDDED_WORKER=0 (deployed mode)

    mode = f"{len(API_KEYS)} API key(s)" if API_KEYS else "OPEN — no auth"
    print(f"MTG engine API on http://{host}:{port}  [{mode}]")
    print(f"  limits: {SIM_PER_HOUR} sims/hour/caller, <={SIM_MAX_GAMES} games, "
          f"{SIM_MAX_QUEUED} queued max, {READ_PER_MIN} reads/min")
    if not API_KEYS:
        print("  WARNING: /simulate and /decks are unauthenticated", file=sys.stderr)

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True   # don't let in-flight requests block shutdown
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down…")
        srv.shutdown()


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    e = Engine()
    if cmd == "rule":
        print(json.dumps(e.rule(rest[0]), indent=2, ensure_ascii=False))
    elif cmd == "keyword":
        print(json.dumps(e.keyword(rest[0]), indent=2, ensure_ascii=False))
    elif cmd == "glossary":
        print(json.dumps(e.glossary(" ".join(rest)), indent=2, ensure_ascii=False))
    elif cmd == "search":
        print(json.dumps(e.search(" ".join(rest)), indent=2, ensure_ascii=False))
    elif cmd == "turn-structure":
        print(json.dumps(e.turn_structure(), indent=2, ensure_ascii=False))
    elif cmd == "validate-log":
        print(json.dumps(e.validate_game_log(rest[0]), indent=2))
    elif cmd == "stats":
        print(json.dumps(e.stats(), indent=2))
    elif cmd == "serve":
        serve(int(rest[0]) if rest else 8484)
    else:
        print(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
