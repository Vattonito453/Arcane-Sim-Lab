#!/usr/bin/env python3
"""The public story of each game: who went out, when and how, and the turn
the board turned. What the results page's one-sentence game rows and the
replay's out seats and "Watch the turning point" control read.

Repair plan WS11 task 1 (tasks/25-repair-plan.md), UX review problem 1 and
sections 4.6 and 5.4 (tasks/26-ux-review.md). The facts come from
qa.knockouts (rules-determined: Forge's loss line gives the cause, the
lethal event gives the moment); this module only picks the public subset
and applies the two display switches below.

## Payload, per game

    knockouts      [{player, turn, round, cause, by, card, basis}], in the
                   order players went out. `turn` is Forge's turn counter,
                   `round` the table turn a player counts ("turn 9"); show
                   `round`. `basis` says where `by` came from: "zones" (the
                   shim's zone stream, a read) or "log" (Forge's event log).
    out            [{player, turn, round, seq}]: the seats that went out and
                   the event Forge dates it by (`seq` of the lethal event;
                   null when only Forge's turn order bounds it, in which case
                   the seat is out from the end of that turn).
    turning_point  {turn, round, card, by, combat, basis, label, seq,
                   share_before, share_after} or null. The turn with the
                   largest shift in board power toward the winner. `basis`
                   is "zones" (read from the zone stream on shim runs) or
                   "inferred" (reconstructed from the stdout log, which never
                   records a creature entering play). `card` is what moved
                   the most power that turn, null when it was combat
                   (`combat` true) or nothing could be named. `label` is the
                   words the UI shows (see MTG_TURNING_POINT). Null for a
                   draw (a game the clock cut off included, whatever winner
                   it records), when no turn moved the board toward the
                   winner, or when the switch is off.

## Display switches (server-side; set in the API's environment)

The knockout and turning-point readings ship to users only after the week-3
hand audit (repair plan WS1 acceptance: at least 95% agreement on 40
knockouts; at least 16 of 20 turning points agreeing with a human reading).
Both are switches, so the lead can apply the audit result without a code
change, and the summary and game payloads carry the decision, so the pages
that read them cannot show more than the server allows.

Scope: the switches govern the game story only (the results page's game
rows and the replay's lede, out seats and primary). Two run-level surfaces
read the same analyzer and are NOT switched: "How games ended" (the final
knockout's cause per game, from /analysis/{file}, disk-cached) and the
scorecards' "how it won" (/results/{file}/scorecards, served immutable).
/analysis also still serves every game's full knockouts and raw turning point
unswitched; no page renders those. If the knockout audit fails, hiding the
per-game cause here does not hide those aggregates.

    MTG_TURNING_POINT    swing (default)  label "Biggest swing": the week-3
                                          audit failed the turning point (8 of
                                          20 against the 16 required;
                                          studies/knockout_audit/RESULTS.md),
                                          so this stays until a re-audit on a
                                          fresh draw passes
                         audited          label "Turning point"
                         off              no turning point at all (held)
    MTG_KNOCKOUT_DETAIL  on (default)     cause and killer shown; the week-3
                                          audit passed knockouts (39 of 40
                                          against the 38 required)
                         off              cause, by and card are null; who
                                          went out, and when, still ship

An unrecognised value falls back to the default and is reported by
switches() so /health and preflight can show it.

Stdlib only.
"""
from __future__ import annotations

import os

TURNING_POINT_ENV = "MTG_TURNING_POINT"
KNOCKOUT_DETAIL_ENV = "MTG_KNOCKOUT_DETAIL"

TURNING_POINT_MODES = ("swing", "audited", "off")
LABELS = {"swing": "Biggest swing", "audited": "Turning point"}

# qa.knockouts names a hint it could not attribute this way; it names no card.
_NO_CARD = {"a resolving ability"}


def switches(env: dict | None = None) -> dict:
    """{"turning_point": mode, "turning_point_label": str | None,
        "knockout_detail": bool, "invalid": [env names with bad values]}"""
    env = os.environ if env is None else env
    invalid: list[str] = []
    tp = (env.get(TURNING_POINT_ENV) or "").strip().lower() or "swing"
    if tp not in TURNING_POINT_MODES:
        invalid.append(TURNING_POINT_ENV)
        tp = "swing"
    kd_raw = (env.get(KNOCKOUT_DETAIL_ENV) or "").strip().lower() or "on"
    if kd_raw not in ("on", "off", "1", "0", "true", "false", "yes", "no"):
        invalid.append(KNOCKOUT_DETAIL_ENV)
        kd_raw = "on"
    return {"turning_point": tp, "turning_point_label": LABELS.get(tp),
            "knockout_detail": kd_raw in ("on", "1", "true", "yes"),
            "invalid": invalid}


def _public_knockout(k: dict, detail: bool) -> dict:
    return {
        "player": k.get("player"),
        "turn": k.get("turn"),
        "round": k.get("round"),
        "cause": k.get("cause") if detail else None,
        "by": k.get("by") if detail else None,
        "card": k.get("card") if detail else None,
        "basis": k.get("basis"),
    }


def _public_turning_point(tp: dict | None, mode: str) -> dict | None:
    if not tp or mode == "off":
        return None
    hint = tp.get("event_hint")
    combat = hint == "combat"
    card = None if (combat or not hint or hint in _NO_CARD) else hint
    return {
        "turn": tp.get("turn"),
        "round": tp.get("round"),
        "card": card,
        "by": tp.get("event_by"),
        "combat": combat,
        "basis": "zones" if tp.get("basis") == "zones" else "inferred",
        "label": LABELS.get(mode, LABELS["swing"]),
        "seq": tp.get("event_seq"),
        "share_before": tp.get("share_before"),
        "share_after": tp.get("share_after"),
    }


def empty() -> dict:
    return {"knockouts": [], "out": [], "turning_point": None}


def of_game(game: dict, sw: dict | None = None) -> dict:
    """{"knockouts", "out", "turning_point"} for one game (module docstring).
    A game the analyzer cannot read gets an empty story, never an error: the
    page then shows who won and when, as before."""
    sw = sw or switches()
    try:
        from qa import knockouts as K  # noqa: PLC0415
        raw = K.analyse_game(game)
    except Exception:  # noqa: BLE001 - one unreadable game must not fail a run
        return empty()
    kos = raw.get("knockouts") or []
    tp = raw.get("turning_point")
    if (game.get("result") or {}).get("timedOut"):
        # The clock cut this game off: any winner it records is an artifact
        # of the timeout (audit A16; validity.clock_cut_wins), so there is no
        # turn the game turned toward it.
        tp = None
    return {
        "knockouts": [_public_knockout(k, sw["knockout_detail"]) for k in kos],
        "out": [{"player": k.get("player"), "turn": k.get("turn"),
                 "round": k.get("round"), "seq": k.get("seq")} for k in kos],
        "turning_point": _public_turning_point(tp, sw["turning_point"]),
    }


def of_run(result: dict, sw: dict | None = None) -> list[dict]:
    """One story per game of a loaded result, in game order."""
    sw = sw or switches()
    return [of_game(g or {}, sw) for g in (result.get("games") or [])]
