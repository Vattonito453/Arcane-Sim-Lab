#!/usr/bin/env python3
"""Convert Forge headless-sim stdout into the training game_log JSON schema.

Forge log lines are `<Caption>: <message>` where Caption comes from
forge.game.GameLogEntryType (verified against Forge 2.0.13 source):
  Turn, Phase, Mulligan, Ante, Draft, Zone Change, Player Control, Damage,
  Life, Land, Discard, Combat, Information, Resolve Stack, Add To Stack,
  Replacement Effect, Mana, Game Outcome, Match Result

Every event keeps the raw message, so nothing is lost if a regex misses.
Zero dependencies (stdlib only).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date

CAPTION_TO_ACTION = {
    "Turn": "turn_begin",
    "Phase": "phase",
    "Mulligan": "mulligan",
    "Ante": "ante",
    "Draft": "draft",
    "Zone Change": "zone_change",
    "Player Control": "player_control",
    "Damage": "damage",
    "Life": "life_change",
    "Land": "land_drop",
    "Discard": "discard",
    "Combat": "combat",
    "Information": "information",
    "Resolve Stack": "stack_resolve",
    "Add To Stack": "stack_add",
    "Replacement Effect": "replacement_effect",
    "Mana": "mana",
    "Game Outcome": "game_outcome",
    "Match Result": "match_result",
}

# Longest captions first so "Resolve Stack" wins over any prefix collision.
_CAPTION_RE = re.compile(
    r"^(%s):\s?(.*)$" % "|".join(sorted((re.escape(c) for c in CAPTION_TO_ACTION), key=len, reverse=True))
)

# "Turn 4 (Ai(2)-Drana Vampires)" — greedy to the LAST ')' since AI names
# contain parentheses (verified against real Forge 2.0.13 output)
_TURN_RE = re.compile(r"[Tt]urn\s+(\d+)\s*\((.+)\)\s*$")
# "Game Result: Game 1 ended in 4321 ms. Alice has won!" — printed by SimulateMatch
_RESULT_RE = re.compile(r"Game Result: Game (\d+) ended in (?:a Draw|(\d+) ms\.\s*(.+?) has won)", re.I)
_DRAW_RE = re.compile(r"Game Result: Game (\d+) ended in a Draw", re.I)


def parse_forge_log(text: str, source: str = "forge-sim") -> dict:
    """Parse one sim invocation's stdout (may contain several games)."""
    games: list[dict] = []
    cur: dict | None = None
    cur_turn: dict | None = None
    seq = 0

    def new_game() -> dict:
        return {"players": [], "turns": [], "result": None, "events_pregame": []}

    def close_game() -> None:
        nonlocal cur, cur_turn
        if cur is not None and (cur["turns"] or cur["events_pregame"] or cur["result"]):
            games.append(cur)
        cur, cur_turn = None, None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        draw = _DRAW_RE.search(line)
        res = _RESULT_RE.search(line)
        if draw or res:
            if cur is None:
                cur = new_game()
            if draw:
                cur["result"] = {"winner": None, "draw": True, "raw": line}
            else:
                cur["result"] = {"winner": res.group(3), "draw": False,
                                 "duration_ms": int(res.group(2)) if res.group(2) else None,
                                 "raw": line}
            close_game()
            continue

        m = _CAPTION_RE.match(line)
        if not m:
            continue  # sim chatter (deck loading, timers) — intentionally skipped
        caption, msg = m.group(1), m.group(2)
        action = CAPTION_TO_ACTION[caption]

        if cur is None:
            cur = new_game()
            seq = 0

        seq += 1
        event = {"seq": seq, "action": action, "raw": msg}

        if action == "turn_begin":
            tm = _TURN_RE.search(msg)
            cur_turn = {
                "turn": int(tm.group(1)) if tm else len(cur["turns"]) + 1,
                "active_player": tm.group(2) if tm else None,
                "events": [],
            }
            cur["turns"].append(cur_turn)
            if cur_turn["active_player"] and cur_turn["active_player"] not in cur["players"]:
                cur["players"].append(cur_turn["active_player"])
            continue

        if action == "life_change":
            lm = re.search(r"(.+?) has (\d+) life", msg)
            if lm:
                event["player"], event["life"] = lm.group(1), int(lm.group(2))
        elif action == "damage":
            dm = re.search(r"(.+?) deals (\d+) .*?damage to (.+?)\.?$", msg)
            if dm:
                event["source"], event["amount"], event["target"] = dm.group(1), int(dm.group(2)), dm.group(3)
        elif action in ("stack_add", "stack_resolve"):
            cm = re.search(r"(?:cast|casts|plays|activated|triggered)\s+(.+?)(?:\s+targeting|\.|$)", msg, re.I)
            if cm:
                event["object"] = cm.group(1)
        elif action == "game_outcome":
            event["detail"] = msg

        target = cur_turn["events"] if cur_turn is not None else cur["events_pregame"]
        target.append(event)

    close_game()

    return {
        "meta": {
            "source": source,
            "generator": "forge_log_adapter.py",
            "schema": "training/game_00X game_log schema (events carry raw Forge messages)",
            "extracted": date.today().isoformat(),
        },
        "games": games,
        "summary": summarize(games),
    }


def summarize(games: list[dict]) -> dict:
    # Seed every seat that took a turn at zero wins. A deck that never wins is
    # still in the pod, and consumers derive the pod size from these keys — omit
    # it and a 4-deck run reports as a 1-deck run with a 100% even-seats
    # baseline. Winner keys come from the same `Ai(n)-Name` namespace as the
    # Turn lines, so they land on the seeded key rather than creating a new one.
    wins: dict[str, int] = {}
    draws = 0
    # Shim-only: a game the clock cut off, forced to a draw rather than let
    # Forge's outcome object decide (simlab-forge-shim SimShim.java). Stock
    # Forge games never carry this key, so it stays 0 for those runs — this
    # is the number that would have surfaced the timeout-declares-a-winner
    # bug and the too-short clock immediately instead of needing a manual
    # raw-log audit to notice 71% of games were hitting it.
    timeouts = 0
    for g in games:
        for p in g.get("players") or []:
            wins.setdefault(p, 0)
    for g in games:
        r = g.get("result") or {}
        if r.get("timedOut"):
            timeouts += 1
            # A game the clock cut off is a draw, whatever winner the record
            # carries. This used to fall through to the elif and CREDIT that
            # winner, so re-parsing a polluted file re-minted the fake win it
            # was being re-parsed to remove (audit A16).
            draws += 1
            continue
        if r.get("draw"):
            draws += 1
        elif r.get("winner"):
            wins[r["winner"]] = wins.get(r["winner"], 0) + 1
    total = len(games)
    return {
        "games": total,
        "draws": draws,
        "timeouts": timeouts,
        "wins": wins,
        "win_rates": {p: round(w / total, 3) for p, w in wins.items()} if total else {},
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: forge_log_adapter.py <forge_sim_stdout.log> [out.json]", file=sys.stderr)
        sys.exit(1)
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    result = parse_forge_log(text, source=sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None
    payload = json.dumps(result, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {out}: {result['summary']}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
