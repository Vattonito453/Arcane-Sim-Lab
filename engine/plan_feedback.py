"""Outcome feedback for deck plans: the sims teach the plans.

Every finished run records, per deck: games, wins, HOW the wins happened
(analysis.win_method), and the true round each win landed on. deck_plan
consults the store when it builds a plan and lets observed reality nudge the
plan toward how the deck actually wins.

THE COLD-START INVARIANT, stated once and enforced here:

    A deck with no history plays exactly the shipped defaults, which are the
    validated configuration every study this month measured. Feedback only
    ever NUDGES, inside hard bounds, and only once there is enough data:
    per-deck effects need >= MIN_DECK_GAMES games of that list; below that,
    the deck inherits its ARCHETYPE's aggregate (>= MIN_TAG_GAMES games
    across all decks sharing its primary tag); below that, nothing happens.

    No deck ever sims "dumb" waiting for data, and opponents never need
    history to know a deck's threats: the threat index is built from the
    decklist itself at import time.

Store: MTG_DATA_DIR/plan_feedback.json, written atomically (tmp + replace).
One worker per box today; if that changes this needs the jobqueue's SQLite,
not fancier JSON.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

MIN_DECK_GAMES = 8
MIN_TAG_GAMES = 24
# Combat/spell share above which the observed win method counts as the
# deck's real plan.
METHOD_MAJORITY = 0.7
# Feedback may move a search-target value by at most this much, and never
# below 1 or above 9. The static plan always survives underneath.
MAX_NUDGE = 2

_AI = re.compile(r"^Ai\(\d+\)-")


def _store_path() -> Path:
    base = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent)))
    return base / "plan_feedback.json"


def load_store() -> dict:
    p = _store_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_store(store: dict) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=1)
        os.replace(tmp, p)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _true_round(game: dict) -> int:
    """Rounds the way a table counts them (a player's Nth turn is round N).

    One Python copy, in scorecard; web/lib/replay.ts carries the TypeScript
    mirror. Imported lazily so this module keeps working if scorecard grows a
    heavier dependency later.
    """
    from scorecard import true_round
    return true_round(game)


def record_run(result: dict) -> dict:
    """Fold one adapted result file's outcomes into the store.

    Idempotent per run: the run's raw source line is remembered so a re-adapt
    or a retry does not double-count.
    """
    from analysis import win_method  # local import: analysis pulls cards.py

    run_id = (result.get("meta") or {}).get("source_hash") or \
        str((result.get("meta") or {}).get("started") or "") + \
        str(len(result.get("games") or []))
    store = load_store()
    seen = store.setdefault("_runs", [])
    if run_id in seen:
        return store
    decks = store.setdefault("decks", {})
    for game in result.get("games") or []:
        res = game.get("result") or {}
        if res.get("timedOut") or res.get("turnCapped"):
            continue  # censored games teach nothing about winning
        winner = res.get("winner")
        players = game.get("players") or []
        for raw in players:
            name = _AI.sub("", raw).strip()
            d = decks.setdefault(name, {"games": 0, "wins": 0,
                                        "methods": {}, "win_rounds": []})
            d["games"] += 1
        if not winner or res.get("draw"):
            continue
        wname = _AI.sub("", winner).strip()
        d = decks.setdefault(wname, {"games": 0, "wins": 0,
                                     "methods": {}, "win_rounds": []})
        d["wins"] += 1
        method = (win_method(game) or {}).get("method") or "other"
        d["methods"][method] = d["methods"].get(method, 0) + 1
        rounds = _true_round(game)
        if rounds:
            d["win_rounds"] = (d["win_rounds"] + [rounds])[-50:]
    seen.append(run_id)
    store["_runs"] = seen[-500:]
    _save_store(store)
    return store


def note_tags(deck_name: str, tags: list[str]) -> None:
    """deck_plan records the deck's archetype at plan-build time, so the
    archetype aggregate can be computed without re-tagging every deck."""
    store = load_store()
    d = store.setdefault("decks", {}).setdefault(
        deck_name, {"games": 0, "wins": 0, "methods": {}, "win_rounds": []})
    if d.get("tags") != tags:
        d["tags"] = tags
        _save_store(store)


def observed_for(deck_name: str, tags: list[str], store: dict | None = None) -> dict | None:
    """The observation a plan may use: per-deck first, archetype fallback.

    Returns {"basis": "deck"|"archetype", "games", "wins", "methods"} or None
    (the cold-start case: use shipped defaults, nudge nothing).
    """
    store = store if store is not None else load_store()
    decks = store.get("decks") or {}
    d = decks.get(deck_name)
    if d and d.get("games", 0) >= MIN_DECK_GAMES:
        return {"basis": "deck", "games": d["games"], "wins": d["wins"],
                "methods": dict(d.get("methods") or {})}
    tag = tags[0] if tags else None
    if tag:
        games = wins = 0
        methods: dict[str, int] = {}
        for other in decks.values():
            if (other.get("tags") or [None])[0] != tag:
                continue
            games += other.get("games", 0)
            wins += other.get("wins", 0)
            for m, n in (other.get("methods") or {}).items():
                methods[m] = methods.get(m, 0) + n
        if games >= MIN_TAG_GAMES:
            return {"basis": "archetype", "games": games, "wins": wins,
                    "methods": methods}
    return None


def apply_to_plan(plan: dict, deck_name: str, tags: list[str]) -> dict:
    """Nudge the plan toward how the deck is OBSERVED to win. Bounded.

    v1 touches exactly one lever: search-target values (what tutors fetch),
    +/- MAX_NUDGE, clamped to [1, 9]. Combat-majority decks tilt toward
    finisher-hinted targets; spell-majority decks tilt toward combo pieces.
    Everything else in the plan is untouched, and the raw observation rides
    along under "observed" for the UI and for coaching.
    """
    obs = observed_for(deck_name, tags)
    if not obs:
        return plan
    plan["observed"] = obs  # additive: the shim ignores unknown keys
    total = sum(obs["methods"].values())
    if not total:
        return plan
    # Labels come from analysis._METHODS verbatim; "combat" alone matches
    # nothing there (found by running the committed fixture through this).
    combat = (obs["methods"].get("combat damage / life loss", 0)
              + obs["methods"].get("commander damage", 0))
    spell = obs["methods"].get("spell", 0)
    targets = (plan.get("search") or {}).get("targets") or {}
    context = (plan.get("search") or {}).get("context") or {}
    line_pieces = {c for ln in plan.get("lines") or [] for c in ln.get("cards", [])}

    def nudge(name: str, up: bool) -> None:
        v = targets.get(name)
        if v is None:
            return
        moved = min(9, v + MAX_NUDGE) if up else max(1, v - MAX_NUDGE)
        targets[name] = moved

    if combat / total >= METHOD_MAJORITY:
        for name in targets:
            if (context.get(name) or {}).get("hint") == "finisher":
                nudge(name, up=True)
    elif spell / total >= METHOD_MAJORITY:
        for name in targets:
            if name in line_pieces:
                nudge(name, up=True)
    return plan
