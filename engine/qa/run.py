#!/usr/bin/env python3
"""QA layer A: a qa.json for every finished run (repair plan WS2 layer A, R1.1).

    py -u engine/qa/run.py <result>          one run: a path, or a result name
                                             in $MTG_DATA_DIR/sim_results
    py -u engine/qa/run.py --all             every sim_*.json in sim_results
                                             with no qa.json, one written by
                                             another analyzer version, or one
                                             written with --no-queue
    py -u engine/qa/run.py --all --force     every run, rewritten

Options: --data-dir DIR (default $MTG_DATA_DIR, else engine/, the same
default every engine module uses), --nice N (POSIX: lower this process's
priority by N), --no-queue (write qa.json only), --quiet.

--no-queue is for a COPY of the data: the worker's sweeper never re-files a
run that has a qa.json, so on the live volume it keeps that run's flags out
of the review queue until `--all` (which redoes a qa.json written without
the queue) or `--force` runs without it.

It works the same on the dev box and inside either VM container:
    sudo docker exec deploy-worker-1 python3 -u /app/engine/qa/run.py --all

WHAT IT DOES. Builds the run context once (qa/context.py), runs every
detector against it with its own time budget, and writes

    $MTG_DATA_DIR/simkb/runs/<result_stem>/qa.json

atomically (temp file, fsync, rename), LAST, so a qa.json that exists is a
finished analysis. Before it, flags at or above the queue threshold are filed
in review_queue/auto/ (qa/review_queue.py). A detector that raises, or runs
past its budget, is recorded in qa.json's `errors` and the rest still run;
a result that cannot even be read (truncated by a kill, not a result at all)
still gets a qa.json whose errors say so. The worker launches this after
jobqueue.finish (worker.launch_qa), niced, detached, with a 120 s watchdog,
and its idle loop re-runs it for any finished run that has none
(worker.sweep_qa). Each attempt is counted in attempts.json beside qa.json,
so a run whose analysis is killed every time is not retried forever.

qa.json, schema "simlab.qa/1" (tasks/25-repair-plan.md, WS2 "qa.json (key
fields)"). What today's detectors fill; a field a later detector owns (the
timeline, funnel, lines, refusals, runaway loops, a knockout's board) is
absent or null, never guessed:

  schema, analyzer        "simlab.qa/1", "qa/<ANALYZER_VERSION>"
  run, run_stem           the result file name, and the directory name above
  generated, seconds      when, and how long the analysis took
  status                  "complete" (no errors) or "partial"
  run_state               games played and expected, incomplete, salvaged
  inputs                  what the context was built from (file names only,
                          never server paths: the route is public)
  basis                   "shim-zones" (every game carries the shim's zone
                          stream: the board is a read), "stdout" (inferred
                          from Forge's log), "mixed", or null (no games)
  board_accuracy          board.validate on the games QA read:
                          {basis, exit_match_rate, assumed_share, exits_total,
                          entries_total}
  pilot                   pilot.disclose(meta) (the one pilot derivation),
                          plus commit (the shim commit when the result records
                          one, else null), flags (per deck file, the fix flags
                          the shim reported, else null), plan_hashes (sha1 of
                          each deck's plan when the plans file is found, else
                          null), lines_file and overrides_version (null: no
                          lines file and no overrides loader exist yet)
  fidelity                from what run_sim recorded: unsupported (cards Forge
                          refused, per deck), commander_missing (refused, or
                          no commander in the deck file), commander_never_cast,
                          and commander_flagged (null until the refusals
                          detector, week 5). A field the result predates is null
  games[]                 n, winner, draw, timed_out, method (the final
                          knockout's cause code: "combat_damage", "poison",
                          "alt_win", ...; "draw"; null when no knockout was
                          read), knockouts (qa.knockouts, each with an anchor;
                          null when the detector did not run for that game),
                          turning_point (the "Biggest board swing" exactly as
                          game_story builds it under the default switches;
                          GET /results/{file}/qa applies the API's own
                          switches, so it serves what the pages show)
  decks{<deck>}           games, and tutors: the plan's key figures (casts,
                          unreachable, reach_ok, reach_unknown,
                          offered_by_forge, x_zero, failed_to_target,
                          closer_overridden, gy_steers_no_use, tutors_drawn,
                          pre_main2, used_same_turn, cast_per_drawn), a family
                          this run cannot measure left null (tutor casts need
                          the shim's agent events, tutor spells its zone
                          stream), plus the detector's own buckets by pilot
  flags[]                 {id, detector ("tutor.unreachable"), kind ("rules" |
                          "judgement"), trust, severity, anchor {game, turn,
                          player, agent_event_index, seq, event_seq}, round,
                          deck, card, detail, evidence, detector_version}.
                          anchor.seq is the agent event's shim seq (null until
                          WS1 task 7 stamps it); event_seq is the Forge log
                          event's seq, the one a replay can seek to. evidence
                          lists agent event indices
  detectors{<name>}       status (ok | error | timeout | skipped), seconds,
                          budget_s, version, kind, flags, and a small metrics
                          summary
  review_queue            what enqueue() did: threshold, cap, eligible,
                          already_queued, written
  errors[]                {stage, error[, game]}: every detector error and
                          timeout, an unreadable result, a failed queue write
  notes[]                 {stage, note}: what the analysis could not judge
                          although nothing failed (a card missing from the
                          card cache leaves a graveyard steer unjudged, so
                          the run is under-flagged, not clean: on the
                          playtester's run a cold cache gave 5 flags, a warm
                          one 14). Layer A writes these; never a human note

Exit status: 0 qa.json written with no errors; 1 written with errors (with
--all: any run had errors or was not written); 2 nothing written (no such
result, bad arguments).

Stdlib only, like the rest of engine/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

SCHEMA = "simlab.qa/1"
ANALYZER_VERSION = "0.1.0"
ANALYZER = f"qa/{ANALYZER_VERSION}"

# The worker's watchdog kills this process at 120 s (worker.QA_TIMEOUT_SECONDS).
# Every stage is capped by what is left of GLOBAL_BUDGET, so the main thread
# regains control, records the overrun and writes qa.json well before that.
GLOBAL_BUDGET = 100.0
WRITE_RESERVE = 5.0
# Per-stage budgets, seconds. Measured on the dev box on the largest local
# result (8.9 MB, 16 games): context 0.1 s, knockouts 0.1 s, tutors 0.1 s,
# board 0.1 s; the 2-vCPU VM is slower, but not by 100x.
BUDGETS = {"context": 45.0, "knockouts": 25.0, "tutors": 25.0, "board_accuracy": 20.0}
MAX_ATTEMPTS = 3

# Detector flag kinds -> (qa.json detector name, severity). Severity decides
# what reaches the review queue (qa/review_queue.py: medium and up by
# default). A kind not listed here is "<module>.<kind>" at low severity, so a
# new kind is recorded in qa.json but queued only once someone rates it here.
FLAG_TYPES = {
    ("tutors", "tutor_unreachable"): ("tutor.unreachable", "high"),
    ("tutors", "tutor_x_zero"): ("tutor.x_zero", "high"),
    ("tutors", "tutor_cast_never_searches"): ("tutor.cast_never_searches", "high"),
    ("tutors", "tutor_gy_steer_no_use"): ("tutor.gy_steer_no_use", "high"),
    ("tutors", "tutor_failed_target"): ("tutor.failed_target", "medium"),
    ("tutors", "tutor_closer_override"): ("tutor.closer_override", "medium"),
    ("knockouts", "deckout"): ("knockout.deckout", "medium"),
    ("knockouts", "unclassified_loss"): ("knockout.unclassified_loss", "medium"),
    ("knockouts", "undated_knockout"): ("knockout.undated", "low"),
}
# Nothing is "trusted" until its judged precision is measured (layer B's
# mistakes/<detector>/stats.json); every flag starts experimental.
TRUST: dict[str, str] = {}
DETECTOR_VERSIONS = {"knockouts": "knockouts/1", "tutors": "tutors/1",
                     "board_accuracy": "board/1"}

_SEV_RANK = {"low": 0, "medium": 1, "high": 2}
# game_story's default switches: qa.json stores the swing as the pages show it
# by default; the GET route re-applies the API's own switches (public()).
_STORY_DEFAULT = {"turning_point": "swing", "turning_point_label": "Biggest board swing",
                  "knockout_detail": True, "invalid": []}


# ------------------------------------------------------------------ paths --

def data_dir(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("MTG_DATA_DIR", str(ENGINE)))


def run_name(path_or_name: str | Path) -> str:
    """The result file name a run is known by ("x.json.out", a local copy
    of a pulled result, is run "x.json")."""
    name = Path(path_or_name).name
    return name[:-4] if name.endswith(".json.out") else name


def run_stem(name: str) -> str:
    name = run_name(name)
    return name[:-5] if name.endswith(".json") else name


def runs_root(ddir: str | Path | None = None) -> Path:
    return data_dir(ddir) / "simkb" / "runs"


def qa_path(name: str, ddir: str | Path | None = None) -> Path:
    return runs_root(ddir) / run_stem(name) / "qa.json"


def attempts_path(name: str, ddir: str | Path | None = None) -> Path:
    return runs_root(ddir) / run_stem(name) / "attempts.json"


def resolve_result(arg: str | Path, ddir: str | Path | None = None) -> Path | None:
    """A path that exists, else a bare name in <data dir>/sim_results."""
    p = Path(arg)
    if p.is_file():
        return p
    if p.name == str(arg):
        q = data_dir(ddir) / "sim_results" / p.name
        if q.is_file():
            return q
    return None


# -------------------------------------------------------------- file i/o --

def _atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".qa-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=1, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_qa(name: str, ddir: str | Path | None = None) -> dict:
    """The stored qa.json for a run. FileNotFoundError when there is none."""
    return json.loads(qa_path(name, ddir).read_text(encoding="utf-8"))


def read_attempts(name: str, ddir: str | Path | None = None) -> dict:
    try:
        d = json.loads(attempts_path(name, ddir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def note_attempt(name: str, ddir: str | Path | None = None) -> dict:
    """Count one more attempt, before any work: the sweeper reads this to
    leave a run alone while an attempt may still be running, and to stop
    retrying one that is killed every time."""
    prev = read_attempts(name, ddir)
    try:
        done = int(prev.get("attempts") or 0)
    except (TypeError, ValueError):
        done = 0   # garbled: count afresh rather than crash every attempt
    rec = {"attempts": done + 1,
           "last_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "last_started_epoch": time.time(), "pid": os.getpid(),
           "analyzer": ANALYZER}
    try:
        _atomic_write(attempts_path(name, ddir), rec)
    except OSError as e:
        print(f"qa: could not record the attempt for {name}: {e}", file=sys.stderr, flush=True)
    return rec


# ---------------------------------------------------------------- stages --

def _timed(name: str, fn, budget: float, errors: list[dict], info: dict):
    """Run fn() in a daemon thread for at most `budget` seconds.

    Returns its value, or None when it raised, overran or was never started
    (the run's budget already spent); each of those is recorded in `errors`
    and `info`. An overrunning thread cannot be stopped from outside; it is
    left behind as a daemon and dies with the process, which exits as soon as
    qa.json is written."""
    info.setdefault("budget_s", round(budget, 1))
    if budget <= 0:
        info.update(status="skipped", seconds=0.0)
        errors.append({"stage": name, "error": "not run: the analysis's "
                       f"{GLOBAL_BUDGET:.0f} s budget was spent before this stage"})
        return None
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - recorded, never raised
            box["error"] = e
            box["tb"] = traceback.format_exc()

    th = threading.Thread(target=target, name=f"qa-{name}", daemon=True)
    t0 = time.perf_counter()
    th.start()
    th.join(budget)
    secs = round(time.perf_counter() - t0, 3)
    info["seconds"] = secs
    if th.is_alive():
        info["status"] = "timeout"
        errors.append({"stage": name, "error": f"exceeded its {budget:.0f} s budget"})
        return None
    if "error" in box:
        e = box["error"]
        info["status"] = "error"
        errors.append({"stage": name, "error": f"{type(e).__name__}: {e}"})
        sys.stderr.write(f"qa: stage {name} failed:\n{box.get('tb', '')}")
        sys.stderr.flush()
        return None
    info["status"] = "ok"
    return box.get("value")


class _Clock:
    def __init__(self, total: float) -> None:
        self.t0 = time.perf_counter()
        self.total = total

    def left(self) -> float:
        return self.total - (time.perf_counter() - self.t0) - WRITE_RESERVE

    def budget(self, stage: str, budgets: dict) -> float:
        return max(0.0, min(budgets.get(stage, 20.0), self.left()))


# --------------------------------------------------------- the pieces --

def _basis_of(result: dict) -> str | None:
    games = [g for g in (result.get("games") or []) if isinstance(g, dict)]
    if not games:
        return None
    zoned = sum(1 for g in games if g.get("zones"))
    return "shim-zones" if zoned == len(games) else ("stdout" if not zoned else "mixed")


def _board_basis(b: str | None) -> str | None:
    if not b:
        return None
    if b == "zone_stream":
        return "shim-zones"
    if b == "inferred":
        return "stdout"
    return "mixed"


def _plan_hashes(plans: dict) -> dict | None:
    out = {}
    for deck, plan in sorted((plans or {}).items()):
        blob = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        out[deck] = hashlib.sha1(blob.encode("utf-8")).hexdigest()
    return out or None


def _fix_flags(meta: dict) -> dict | None:
    """{deck file: the fix flags its seat's shim reported}, first report per
    deck. None when the run records none (shims before 0.17.0)."""
    out: dict = {}
    rots = meta.get("rotations_detail")
    rows = [r for r in rots if isinstance(r, dict)] if isinstance(rots, list) else []
    if not rows:
        rows = [{"seats": meta.get("seats") or meta.get("decks") or [],
                 "fixFlags": meta.get("fixFlags")}]
    for r in rows:
        seats, flags = r.get("seats") or [], r.get("fixFlags")
        if not isinstance(flags, list):
            continue
        for deck, f in zip(seats, flags):
            if isinstance(f, dict):
                out.setdefault(Path(str(deck)).name, f)
    return out or None


def _commit(meta: dict) -> str | None:
    for src in [meta] + [r for r in (meta.get("rotations_detail") or []) if isinstance(r, dict)]:
        for k in ("shim_commit", "shimCommit", "commit"):
            v = src.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def pilot_block(meta: dict, plans: dict) -> dict:
    import pilot as pilot_mod
    p = dict(pilot_mod.disclose(meta))
    p.update(commit=_commit(meta), flags=_fix_flags(meta), plan_hashes=_plan_hashes(plans),
             lines_file=None, overrides_version=None)
    return p


def fidelity_block(meta: dict) -> dict:
    """What Forge refused or never played, from run_sim's fidelity meta."""
    labels = {}
    for row in meta.get("commander_fidelity") or []:
        if isinstance(row, dict) and row.get("deck"):
            labels[Path(str(row["deck"])).name] = row.get("player") or row.get("deck")
    if "unsupported_cards" in meta:
        unsupported = []
        attributed = set()
        for f, cards_ in sorted((meta.get("unsupported_by_deck") or {}).items()):
            for c in cards_ or []:
                attributed.add(c)
                unsupported.append({"deck": labels.get(Path(f).name) or Path(f).stem,
                                    "file": Path(f).name, "card": c,
                                    "reason": "forge_refused"})
        for c in meta.get("unsupported_cards") or []:
            if c not in attributed:
                unsupported.append({"deck": None, "file": None, "card": c,
                                    "reason": "forge_refused"})
    else:
        unsupported = None
    if "commander_fidelity" in meta:
        from validity import _commander_findings
        missing, never = _commander_findings(meta)
        commander_missing = [{"deck": p, "commanders": names,
                              "reason": "no_commander" if names is None else "refused"}
                             for p, names in missing]
        never_cast = [{"deck": p, "commanders": names, "games": n} for p, names, n in never]
    else:
        commander_missing = never_cast = None
    return {"unsupported": unsupported, "commander_missing": commander_missing,
            "commander_never_cast": never_cast, "commander_flagged": None}


def run_state(meta: dict, result: dict) -> dict:
    games = result.get("games") or []
    return {"games_played": len(games),
            "games_expected": meta.get("games_expected") or meta.get("games_requested"),
            "incomplete": bool(meta.get("incomplete")),
            "salvaged": bool(meta.get("salvaged_from_kill")),
            "rotated": meta.get("source") == "rotated"}


def _round_at(game: dict, turn) -> int | None:
    """Table round of a turn (scorecard.true_round, the one copy of the rule)."""
    if not isinstance(turn, int):
        return None
    from scorecard import true_round
    for i, t in enumerate(game.get("turns") or []):
        if t.get("turn") == turn:
            return true_round(game, i)
    return None


def _anchor(game_n: int, turn, player, aei=None, seq=None, event_seq=None) -> dict:
    return {"game": game_n, "turn": turn, "player": player,
            "agent_event_index": aei, "seq": seq, "event_seq": event_seq}


def normalize_flags(raw_flags: list[dict], module: str, kind: str, games: list[dict],
                    stem: str, errors: list[dict], seen: dict[str, int]) -> list[dict]:
    """A detector's flags in qa.json's shape. analyzer_error flags are the
    detector's own per-game errors: they go to `errors`, not to review."""
    from qa.context import strip_seat
    out = []
    for f in raw_flags or []:
        if not isinstance(f, dict):
            continue
        fkind = f.get("kind")
        if fkind == "analyzer_error":
            errors.append({"stage": module, "game": f.get("game"),
                           "error": str(f.get("detail") or "analyzer error")})
            continue
        det, sev = FLAG_TYPES.get((module, fkind), (f"{module}.{fkind}", "low"))
        a_in = f.get("anchor") if isinstance(f.get("anchor"), dict) else {}
        game_n = f.get("game") or a_in.get("game")
        turn = f.get("turn") if f.get("turn") is not None else a_in.get("turn")
        player = f.get("player") if f.get("player") is not None else a_in.get("player")
        aei = a_in.get("agent_event_index")
        anchor = _anchor(game_n, turn, player, aei, a_in.get("seq"), f.get("seq"))
        rnd = f.get("round")
        if rnd is None and isinstance(game_n, int) and 1 <= game_n <= len(games):
            rnd = _round_at(games[game_n - 1], turn)
        where = (f"a{aei}" if isinstance(aei, int) else
                 f"s{f['seq']}" if isinstance(f.get("seq"), int) else f"t{turn}")
        base = f"{stem}#g{game_n}{where}.{det}"
        n = seen.get(base, 0) + 1
        seen[base] = n
        fid = base if n == 1 else f"{base}~{n}"
        out.append({
            "id": fid, "detector": det, "kind": kind,
            "trust": TRUST.get(det, "experimental"), "severity": sev,
            "anchor": anchor, "round": rnd,
            "deck": strip_seat(player) if player else None,
            "card": f.get("card"), "detail": f.get("detail"),
            "evidence": [aei] if isinstance(aei, int) else [],
            "detector_version": DETECTOR_VERSIONS.get(module, f"{module}/1"),
        })
    return out


def _public_knockout(k: dict, game_n: int) -> dict:
    return {"player": k.get("player"), "turn": k.get("turn"), "round": k.get("round"),
            "cause": k.get("cause"), "by": k.get("by"), "card": k.get("card"),
            "basis": k.get("basis"), "dated_by": k.get("dated_by"),
            "reason": k.get("reason"),
            "anchor": _anchor(game_n, k.get("turn"), k.get("player"), None, None,
                              k.get("seq"))}


def games_block(result: dict, ko_metrics: dict | None) -> list[dict]:
    import game_story
    per = {}
    if isinstance(ko_metrics, dict):
        per = {g.get("n"): g for g in ko_metrics.get("per_game") or [] if isinstance(g, dict)}
    out = []
    for n, g in enumerate(result.get("games") or [], 1):
        g = g if isinstance(g, dict) else {}
        res = g.get("result") if isinstance(g.get("result"), dict) else {}
        entry = {"n": n, "winner": res.get("winner"), "draw": bool(res.get("draw")),
                 "timed_out": bool(res.get("timedOut")), "turns": len(g.get("turns") or []),
                 "method": None, "knockouts": None, "turning_point": None}
        one = per.get(n)
        if one is not None and not one.get("error"):
            kos = one.get("knockouts") or []
            entry["knockouts"] = [_public_knockout(k, n) for k in kos]
            if entry["draw"]:
                entry["method"] = "draw"
            elif kos:
                entry["method"] = kos[-1].get("cause")
            story = game_story.from_analysis(g, one, _STORY_DEFAULT)
            entry["turning_point"] = story.get("turning_point")
        elif entry["draw"]:
            entry["method"] = "draw"
        out.append(entry)
    return out


_CAST_FAMILY = ("casts", "unreachable", "reach_ok", "reach_unknown", "offered_by_forge",
                "x_zero", "failed_to_target", "closer_overridden", "gy_steers_no_use")
_SPELL_FAMILY = ("tutors_drawn", "pre_main2", "used_same_turn", "cast_per_drawn")


def _tutor_summary(buckets: dict, measurable: dict) -> dict:
    from qa import tutors as T
    pooled = T.new_bucket()
    for b in buckets.values():
        T._add(pooled, T._strip_ratios(b))
    T.finalize(pooled)
    unknown = (pooled.get("reach_basis") or {}).get("unknown", 0)
    pre = sum(v.get("own_before_main2", 0) + v.get("opp_before_main2", 0)
              for v in (pooled.get("phase") or {}).values())
    used = sum(v.get("used_same_turn", 0) for v in (pooled.get("fetch_use") or {}).values())
    s = {"casts": pooled["tutor_cast"], "unreachable": pooled["unreachable"],
         "reach_ok": pooled["tutor_cast"] - pooled["unreachable"] - unknown,
         "reach_unknown": unknown,
         "offered_by_forge": pooled["searched"] - pooled["searched_not_offered"],
         "x_zero": pooled["x_zero"], "failed_to_target": pooled["failed_to_target"],
         "closer_overridden": pooled["closer_overrides"],
         "gy_steers_no_use": pooled["gy_steers_no_use"],
         "tutors_drawn": pooled["tutors_drawn"], "pre_main2": pre, "used_same_turn": used,
         "cast_per_drawn": pooled.get("casts_per_drawn")}
    if not measurable.get("tutor_casts"):
        s.update({k: None for k in _CAST_FAMILY})
    if not measurable.get("tutor_spells"):
        s.update({k: None for k in _SPELL_FAMILY})
    s["measurable"] = dict(measurable)
    s["by_pilot"] = buckets
    return s


def decks_block(result: dict, tut_metrics: dict | None) -> dict:
    from qa.context import strip_seat
    decks: dict[str, dict] = {}
    for g in result.get("games") or []:
        for p in (g or {}).get("players") or []:
            d = decks.setdefault(strip_seat(p), {"games": 0, "tutors": None})
            d["games"] += 1
    if isinstance(tut_metrics, dict):
        measurable = (tut_metrics.get("basis") or {}).get("measurable") or {}
        by_seat = tut_metrics.get("by_seat") or {}
        for deck, d in decks.items():
            if measurable.get("tutor_casts") or measurable.get("tutor_spells"):
                d["tutors"] = _tutor_summary(by_seat.get(deck) or {}, measurable)
    return decks


def _ko_summary(m: dict) -> dict:
    return {k: m.get(k) for k in ("knockouts", "by_cause", "basis", "undated", "errors",
                                  "turning_points")}


def _tutor_metrics_summary(m: dict) -> dict:
    pooled = m.get("pooled") or {}
    keep = ("tutor_cast", "unreachable", "unreachable_rate", "unreachable_rate_known",
            "x_zero", "failed_to_target", "tutors_drawn", "tutor_spells_cast",
            "casts_per_drawn", "gy_steers_no_use", "closer_overrides")
    basis = m.get("basis") or {}
    return {"pooled": {k: pooled.get(k) for k in keep},
            "measurable": basis.get("measurable"), "reach_index": basis.get("reach_index"),
            "pilots_unknown": basis.get("pilots_unknown")}


def _inputs(ctx) -> dict:
    b = ctx.basis()
    plans = b.get("plans")
    return {"agent": b.get("agent"), "games": b.get("games"), "zone_games": b.get("zones"),
            "plans_file": Path(plans).name if isinstance(plans, str) else None,
            "plan_version": b.get("planVersion"), "forge_index": b.get("forge_index"),
            "card_cache_entries": b.get("card_cache"), "raw_jsonl_files": b.get("raw_jsonl")}


# ------------------------------------------------------------- analysis --

DEFAULT_DETECTORS = ("knockouts", "tutors")


def _default_detectors():
    """The registry, one module at a time: a module that fails to import
    (a bad deploy, a syntax error) becomes that detector's error in
    qa.json, and the rest still run. Importing them together used to raise
    out of analyze(), so one broken module left a qa.json with no games, no
    knockouts and no board accuracy (measured on the verify branch)."""
    import importlib
    out = []
    for name in DEFAULT_DETECTORS:
        try:
            mod = importlib.import_module(f"qa.{name}")
            out.append((name, mod.detect, getattr(mod, "KIND", None)))
        except Exception as e:  # noqa: BLE001 - recorded by _timed as this detector's error
            def broken(ctx, _e=e, _n=name):
                raise ImportError(f"qa.{_n} did not import: {type(_e).__name__}: {_e}")
            out.append((name, broken, None))
    return out


def analyze(path: str | Path, *, result: dict | None = None, detectors=None,
            budgets: dict | None = None, total_budget: float = GLOBAL_BUDGET,
            facts=None, forge=None, load_forge: bool = True) -> dict:
    """The qa.json document for one run (nothing is written).

    `result` analyses an already-loaded result dict under the name of
    `path` (preflight's synthetic run). `detectors` replaces the registry
    with [(name, detect(ctx) -> (metrics, flags), kind)] (tests inject slow
    and failing ones). Never raises for anything the run's data can cause."""
    budgets = dict(BUDGETS, **(budgets or {}))
    clock = _Clock(total_budget)
    name = run_name(path)
    stem = run_stem(name)
    errors: list[dict] = []
    dets: dict[str, dict] = {}
    doc: dict = {"schema": SCHEMA, "analyzer": ANALYZER, "run": name, "run_stem": stem,
                 "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "status": "partial", "run_state": None, "inputs": None, "basis": None,
                 "board_accuracy": None, "pilot": None, "fidelity": None, "games": [],
                 "decks": {}, "flags": [], "detectors": dets, "review_queue": None,
                 "errors": errors, "notes": []}

    def build_ctx():
        from qa import context as qctx
        f = facts if facts is not None else qctx.CardFacts.load()
        idx = forge
        if idx is None and load_forge:
            try:
                idx = qctx.load_forge_index()
            except Exception as e:  # noqa: BLE001 - the index is optional
                print(f"qa: Forge index not loaded: {type(e).__name__}: {e}",
                      file=sys.stderr, flush=True)
                idx = None
        try:
            if result is not None:
                return qctx.from_result_dict(result, source=name, facts=f, forge=idx)
            return qctx.from_result(Path(path), facts=f, forge=idx)
        except (AttributeError, TypeError) as e:
            # A JSON file that is not a result object (a plans file, a list).
            raise ValueError(f"not a simulation result ({type(e).__name__}: {e})") from e

    info: dict = {}
    ctx = _timed("context", build_ctx, clock.budget("context", budgets), errors, info)
    dets["context"] = info
    if ctx is not None and not isinstance(ctx.result.get("games"), list):
        errors.append({"stage": "context", "error": "not a simulation result (no games list)"})
        ctx = None
    if ctx is None:
        doc["seconds"] = round(time.perf_counter() - clock.t0, 3)
        return doc

    res, meta = ctx.result, ctx.meta
    for label, fn in (("run_state", lambda: run_state(meta, res)),
                      ("inputs", lambda: _inputs(ctx)),
                      ("basis", lambda: _basis_of(res)),
                      ("pilot", lambda: pilot_block(meta, ctx.plans)),
                      ("fidelity", lambda: fidelity_block(meta))):
        try:
            doc[label] = fn()
        except Exception as e:  # noqa: BLE001
            errors.append({"stage": label, "error": f"{type(e).__name__}: {e}"})

    metrics: dict[str, dict | None] = {}
    seen: dict[str, int] = {}
    flags: list[dict] = []
    for dname, detect, kind in (detectors if detectors is not None else _default_detectors()):
        dinfo = {"version": DETECTOR_VERSIONS.get(dname, f"{dname}/1"), "kind": kind}
        out = _timed(dname, lambda d=detect: d(ctx), clock.budget(dname, budgets), errors, dinfo)
        dets[dname] = dinfo
        if out is None:
            metrics[dname] = None
            continue
        try:
            m, f = out
            metrics[dname] = m
            new = normalize_flags(f, dname, kind, res.get("games") or [], stem, errors, seen)
            flags += new
            dinfo["flags"] = len(new)
            if dname == "knockouts":
                dinfo["metrics"] = _ko_summary(m)
            elif dname == "tutors":
                dinfo["metrics"] = _tutor_metrics_summary(m)
        except Exception as e:  # noqa: BLE001 - a malformed detector answer
            metrics[dname] = None
            dinfo["status"] = "error"
            errors.append({"stage": dname, "error": f"bad detector output: {type(e).__name__}: {e}"})

    def board():
        import board as board_mod
        v = board_mod.validate(res, fetch=False)
        return {"basis": _board_basis(v.get("basis")), "exit_match_rate": v.get("exit_match_rate"),
                "assumed_share": v.get("assumed_share"), "exits_total": v.get("exits_total"),
                "entries_total": v.get("entries_total")}

    binfo = {"version": DETECTOR_VERSIONS["board_accuracy"], "kind": "rules"}
    doc["board_accuracy"] = _timed("board_accuracy", board,
                                   clock.budget("board_accuracy", budgets), errors, binfo)
    dets["board_accuracy"] = binfo

    for label, fn in (("games", lambda: games_block(res, metrics.get("knockouts"))),
                      ("decks", lambda: decks_block(res, metrics.get("tutors")))):
        try:
            doc[label] = fn()
        except Exception as e:  # noqa: BLE001
            errors.append({"stage": label, "error": f"{type(e).__name__}: {e}"})
            sys.stderr.write(f"qa: {label} failed:\n{traceback.format_exc()}")
    flags.sort(key=lambda f: (-_SEV_RANK.get(f["severity"], 0), f["anchor"].get("game") or 0,
                              f["anchor"].get("turn") or 0, f["id"]))
    doc["flags"] = flags
    try:
        doc["notes"] = coverage_notes(doc)
    except Exception as e:  # noqa: BLE001
        errors.append({"stage": "notes", "error": f"{type(e).__name__}: {e}"})
    doc["seconds"] = round(time.perf_counter() - clock.t0, 3)
    return doc


def coverage_notes(doc: dict) -> list[dict]:
    """What this analysis could not judge although no stage failed. The
    card cache is read, never fetched (qa/context.CardFacts), so a card it
    does not hold is unknown and its flag is simply not raised: the status
    stays "complete" and only these notes say the run is under-flagged."""
    notes: list[dict] = []
    unknown = 0
    for d in (doc.get("decks") or {}).values():
        for b in (((d or {}).get("tutors") or {}).get("by_pilot") or {}).values():
            if isinstance(b, dict) and isinstance(b.get("gy_steers_unknown"), int):
                unknown += b["gy_steers_unknown"]
    if (doc.get("inputs") or {}).get("card_cache_entries") == 0:
        notes.append({"stage": "inputs", "note": "no card cache: every check that reads "
                      "card facts (graveyard use, target types) is unknown, so the flags "
                      "that depend on them are missing"})
    if unknown:
        s = "" if unknown == 1 else "s"
        notes.append({"stage": "tutors", "note": f"{unknown} graveyard steer{s} not judged: "
                      "the card is not in the card cache, so no tutor.gy_steer_no_use flag "
                      "could be raised for " + ("it" if unknown == 1 else "them")})
    return notes


def finish(doc: dict, ddir: str | Path | None = None, *, queue: bool = True) -> Path:
    """File the review queue, then write qa.json (last). Returns its path."""
    if queue and doc.get("flags"):
        try:
            from qa import review_queue
            doc["review_queue"] = review_queue.enqueue(doc, data_dir(ddir))
        except Exception as e:  # noqa: BLE001
            doc["errors"].append({"stage": "review_queue", "error": f"{type(e).__name__}: {e}"})
            sys.stderr.write(f"qa: review queue write failed:\n{traceback.format_exc()}")
    elif queue:
        doc["review_queue"] = {"eligible": 0, "written": 0}
    doc["status"] = "complete" if not doc["errors"] else "partial"
    out = qa_path(doc["run"], ddir)
    _atomic_write(out, doc)
    return out


def run_one(path: str | Path, ddir: str | Path | None = None, *, queue: bool = True,
            quiet: bool = False, **kw) -> tuple[int, Path | None]:
    """analyze + finish for one result file; (exit status, qa.json path)."""
    name = run_name(path)
    note_attempt(name, ddir)
    try:
        doc = analyze(path, **kw)
    except Exception as e:  # noqa: BLE001 - analyze guards itself; belt and braces
        sys.stderr.write(f"qa: analysis of {name} failed:\n{traceback.format_exc()}")
        doc = {"schema": SCHEMA, "analyzer": ANALYZER, "run": name, "run_stem": run_stem(name),
               "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "status": "partial", "games": [], "decks": {}, "flags": [], "detectors": {},
               "errors": [{"stage": "analyze", "error": f"{type(e).__name__}: {e}"}],
               "notes": []}
    try:
        out = finish(doc, ddir, queue=queue)
    except OSError as e:
        print(f"qa: could not write qa.json for {name}: {e}", file=sys.stderr, flush=True)
        return 2, None
    if not quiet:
        q = doc.get("review_queue") or {}
        print(f"qa: {name}: {len(doc['games'])} games, {len(doc['flags'])} flags, "
              f"{q.get('written', 0)} queued, {len(doc['errors'])} errors, "
              f"{doc.get('seconds', 0):.2f} s -> {out}", flush=True)
        for e in doc["errors"]:
            print(f"qa:   error [{e.get('stage')}] {e.get('error')}", flush=True)
    return (0 if not doc["errors"] else 1), out


# ------------------------------------------------------------ public read --

def public(doc: dict, sw: dict | None = None) -> dict:
    """qa.json as GET /results/{file}/qa serves it.

    The turning point follows the API's own game-story switches (the pages'
    rule: off holds it, the label is the one in force). No human flag note
    can appear: layer A never reads the human queue, and any flag carrying a
    note or a reporter is dropped here all the same."""
    out = json.loads(json.dumps(doc))
    if sw is None:
        import game_story
        sw = game_story.switches()
    for g in out.get("games") or []:
        tp = g.get("turning_point")
        if not isinstance(tp, dict):
            continue
        if sw.get("turning_point") == "off":
            g["turning_point"] = None
        else:
            tp["label"] = sw.get("turning_point_label") or tp.get("label")
    out["flags"] = [f for f in out.get("flags") or []
                    if isinstance(f, dict) and "note" not in f and "reporter" not in f
                    and f.get("source") != "flag_this_play"]
    out.pop("run_stem", None)
    return out


# ----------------------------------------------------------------- --all --

def _stale(name: str, ddir, queue: bool = True) -> bool:
    """Whether --all should (re)write this run's qa.json: none, unreadable,
    another analyzer version, or (when queueing) one written with --no-queue
    whose flags were never filed. The sweeper skips any run that has a
    qa.json, so without the last rule a --no-queue write would keep that
    run's flags out of the review queue for good."""
    try:
        doc = read_qa(name, ddir)
    except (OSError, ValueError):
        return True
    if not isinstance(doc, dict) or doc.get("analyzer") != ANALYZER:
        return True
    return bool(queue and doc.get("flags") and doc.get("review_queue") is None)


def run_all(ddir: str | Path | None = None, *, force: bool = False, queue: bool = True,
            nice: int = 0, timeout: float = 120.0, quiet: bool = False,
            limit: int | None = None) -> dict:
    """Backfill: one child process per run, so a runaway detector on one run
    cannot slow the next, and each gets the hook's 120 s ceiling."""
    rdir = data_dir(ddir) / "sim_results"
    files = sorted(rdir.glob("sim_*.json")) if rdir.is_dir() else []
    counts = {"runs": len(files), "written": 0, "with_errors": 0, "not_written": 0,
              "skipped_current": 0, "seconds": []}
    todo = [f for f in files if force or _stale(f.name, ddir, queue)]
    counts["skipped_current"] = len(files) - len(todo)
    if limit is not None:
        todo = todo[:limit]
    for f in todo:
        cmd = [sys.executable, "-u", str(Path(__file__).resolve()), str(f),
               "--data-dir", str(data_dir(ddir))]
        if nice:
            cmd += ["--nice", str(nice)]
        if not queue:
            cmd.append("--no-queue")
        if quiet:
            cmd.append("--quiet")
        t0 = time.perf_counter()
        try:
            rc = subprocess.run(cmd, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = 3
            print(f"qa: {f.name}: killed after {timeout:.0f} s", file=sys.stderr, flush=True)
        counts["seconds"].append(round(time.perf_counter() - t0, 3))
        if rc == 0:
            counts["written"] += 1
        elif rc == 1:
            counts["written"] += 1
            counts["with_errors"] += 1
        else:
            counts["not_written"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("result", nargs="?", help="a result file path or name")
    ap.add_argument("--all", action="store_true", help="every run in sim_results")
    ap.add_argument("--force", action="store_true", help="with --all: rewrite current ones too")
    ap.add_argument("--limit", type=int, default=None, help="with --all: at most N runs")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--nice", type=int, default=0)
    ap.add_argument("--no-queue", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if a.data_dir:
        # cards.py and forge_index.py read MTG_DATA_DIR when first imported
        # (lazily, inside analyze), so the card cache and the Forge index
        # come from the same data dir as the results and qa.json.
        os.environ["MTG_DATA_DIR"] = str(Path(a.data_dir))
    if a.nice and hasattr(os, "nice"):
        try:
            os.nice(a.nice)
        except OSError:
            pass
    if a.all == bool(a.result):
        ap.print_usage(sys.stderr)
        print("pass one result, or --all", file=sys.stderr)
        return 2
    if a.all:
        c = run_all(a.data_dir, force=a.force, queue=not a.no_queue, nice=a.nice,
                    quiet=a.quiet, limit=a.limit)
        secs = sorted(c.pop("seconds"))
        p95 = secs[min(len(secs) - 1, int(round(0.95 * (len(secs) - 1))))] if secs else None
        print("qa --all: " + json.dumps({**c, "p95_seconds": p95,
                                         "max_seconds": secs[-1] if secs else None}), flush=True)
        return 0 if not (c["with_errors"] or c["not_written"]) else 1
    path = resolve_result(a.result, a.data_dir)
    if path is None:
        print(f"qa: no such result: {a.result}", file=sys.stderr)
        return 2
    rc, _ = run_one(path, a.data_dir, queue=not a.no_queue, quiet=a.quiet)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
