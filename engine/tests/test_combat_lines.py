#!/usr/bin/env python3
"""Multi-line combat entries must not lose lines (both adapters, and readapt).

Forge's GameLogFormatter joins a multi-defender attack declaration, and a
defender's whole block declaration, into ONE entry with embedded newlines.
Printed (stock sim) or serialised (shim JSONL) and rebuilt, that is one
captioned line plus caption-less continuation lines, and parse_forge_log used
to skip every caption-less line as chatter. Reproduced from the 2026-08-31 run
a playtester flagged: "Ur-Dragon B3 assigned Sunscorch Regent (75) to attack
Skrat's Revenge.\\nUr-Dragon B3 assigned Dragonlord Ojutai (24) to attack
Living Energy+." lost its second line, so the replay showed Living Energy's
Thopter blocking an Ojutai that had never attacked ("an illegal blocker for
another deck"). Forge played it legally; the log dropped the line.

Run: python3 engine/tests/test_combat_lines.py   (no network, no JVM)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forge_log_adapter import parse_forge_log  # noqa: E402
from shim_log_adapter import parse_shim_jsonl  # noqa: E402
import readapt  # noqa: E402

A, B, C, D = "Ai(1)-Ur-Dragon B3", "Ai(2)-Power Cosmic", "Ai(3)-Skrat's Revenge", "Ai(4)-Living Energy+"
OJUTAI_ATTACK = f"{A} assigned Dragonlord Ojutai (24) to attack {D}."

# The last block line uses a wording no regex here knows. It still follows a
# combat event, so it is still the next line of that entry: the stdout path
# must not need a grammar to keep it, because the shim path keeps it without one.
STDOUT = f"""
Simulation mode
Game 1 of 1
Turn: Turn 18 ({A})
Phase: {A}'s Main phase, precombat
Add To Stack: {A} cast Austere Command
Resolve Stack: Austere Command (12) - Choose two:
• Destroy all artifacts.
• Destroy all creatures with mana value 4 or greater.
Phase: {A}'s Declare Attackers Step
Combat: {A} assigned Sunscorch Regent (75) to attack {C}.
{OJUTAI_ATTACK}
{A} assigned Kokusho, the Evening Star (120) and Atarka, World Render (169) to attack Elspeth, Sun's Champion (52).
Phase: {A}'s Declare Blockers Step
Combat: {C} didn't block Sunscorch Regent (75).
Combat: {D} assigned Thopter Token (638) to block Dragonlord Ojutai (24).
Combat: {B} didn't block Kokusho, the Evening Star (120).
{B} assigned Sylvan Safekeeper (213) and Squirrel Token (300) to block Atarka, World Render (169).
{B} put Squirrel Token (300) in front of Atarka, World Render (169) as well.
Phase: {A}'s Combat Damage Step
Damage: Dragonlord Ojutai (24) deals 5 damage to Thopter Token (638).
java.lang.NullPointerException: boom
\tat forge.game.phase.PhaseHandler.startFirstTurn(PhaseHandler.java:1036)
\tat java.base/java.util.ArrayList.forEach(ArrayList.java:1511)
Caused by: java.lang.IllegalStateException
\t... 3 more
Game Result: Game 1 ended in 1234 ms. {A} has won!
Game 2 of 1
some trailing chatter that must not attach anywhere
"""


def test_stdout_continuations() -> None:
    r = parse_forge_log(STDOUT, source="unit-test")
    assert len(r["games"]) == 1, r["games"]
    evs = r["games"][0]["turns"][0]["events"]
    combat = [e["raw"] for e in evs if e["action"] == "combat"]
    # 3 attack declarations (one per defender, planeswalker included) and
    # 5 block lines (Power Cosmic's three were one Forge entry).
    assert combat == [
        f"{A} assigned Sunscorch Regent (75) to attack {C}.",
        OJUTAI_ATTACK,
        f"{A} assigned Kokusho, the Evening Star (120) and Atarka, World Render (169) "
        "to attack Elspeth, Sun's Champion (52).",
        f"{C} didn't block Sunscorch Regent (75).",
        f"{D} assigned Thopter Token (638) to block Dragonlord Ojutai (24).",
        f"{B} didn't block Kokusho, the Evening Star (120).",
        f"{B} assigned Sylvan Safekeeper (213) and Squirrel Token (300) to block "
        "Atarka, World Render (169).",
        f"{B} put Squirrel Token (300) in front of Atarka, World Render (169) as well.",
    ], combat
    # Every event has its own seq, strictly increasing, continuation or not.
    seqs = [e["seq"] for e in evs]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), seqs
    # Modal spell text stays on the resolve event it belongs to; it does NOT
    # become a stack_resolve of its own (which would pop the replay's fold).
    resolves = [e for e in evs if e["action"] == "stack_resolve"]
    assert len(resolves) == 1, resolves
    assert resolves[0]["raw"] == "Austere Command (12) - Choose two:"
    assert resolves[0]["more"] == ["• Destroy all artifacts.",
                                   "• Destroy all creatures with mana value 4 or greater."]
    # A crash dump is never data: not an event, not attached to one. That
    # includes JDK frames, whose module prefix carries a slash.
    dmg = [e for e in evs if e["action"] == "damage"]
    assert len(dmg) == 1 and "more" not in dmg[0], dmg
    assert not any("NullPointer" in json.dumps(e) or "ArrayList" in json.dumps(e) for e in evs)
    # The event count itself is what the old parser got wrong.
    assert len(evs) == 15, [(e["action"], e["raw"][:40]) for e in evs]
    print("  stdout: 3 attack + 5 block lines kept where 1 + 3 used to survive")


def _shim_jsonl() -> str:
    """The playtester's turn as the shim writes it: the two attack lines are
    ONE entry joined with a newline, exactly as Forge's formatter emits it."""
    attack = f"{A} assigned Sunscorch Regent (75) to attack {C}.\n{OJUTAI_ATTACK}"
    blocks_c = f"{C} didn't block Sunscorch Regent (75)."
    blocks_d = f"{D} assigned Thopter Token (638) to block Dragonlord Ojutai (24)."
    modal = "Austere Command (12) - Choose two:\n• Destroy all artifacts."
    recs = [
        {"rec": "meta", "shim": "0.13.0", "format": "Commander", "games": 1,
         "players": [A, B, C, D], "humanized": True},
        {"rec": "entry", "game": 0, "seq": 0, "type": "TURN", "message": f"Turn 18 ({A})"},
        {"rec": "entry", "game": 0, "seq": 1, "type": "PHASE",
         "message": f"{A}'s Main phase, precombat"},
        {"rec": "entry", "game": 0, "seq": 2, "type": "STACK_RESOLVE", "message": modal},
        {"rec": "entry", "game": 0, "seq": 3, "type": "PHASE",
         "message": f"{A}'s Declare Attackers Step"},
        {"rec": "entry", "game": 0, "seq": 4, "type": "COMBAT", "message": attack},
        {"rec": "entry", "game": 0, "seq": 5, "type": "PHASE",
         "message": f"{A}'s Declare Blockers Step"},
        {"rec": "entry", "game": 0, "seq": 6, "type": "COMBAT", "message": blocks_c},
        {"rec": "entry", "game": 0, "seq": 7, "type": "COMBAT", "message": blocks_d},
        {"rec": "entry", "game": 0, "seq": 8, "type": "DAMAGE",
         "message": "Dragonlord Ojutai (24) deals 5 damage to Thopter Token (638)."},
        # types is Forge's comma-joined core type list, as the shim emits it.
        {"rec": "zone", "game": 0, "turn": 18, "phase": "COMBAT_DAMAGE", "card": "Thopter Token",
         "cardId": 638, "from": "Battlefield", "to": "Graveyard", "fromPlayer": D,
         "toPlayer": D, "types": "Creature,Artifact", "pt": "1/1", "token": True},
        {"rec": "result", "game": 0, "draw": False, "winner": A, "turns": 18,
         "timedOut": False, "turnCapped": False, "ms": 4321},
    ]
    return "\n".join(json.dumps(r) for r in recs) + "\n"


def test_shim_continuations() -> None:
    r = parse_shim_jsonl(_shim_jsonl(), source="unit-test")
    g = r["games"][0]
    evs = g["turns"][0]["events"]
    combat = [e["raw"] for e in evs if e["action"] == "combat"]
    assert combat == [
        f"{A} assigned Sunscorch Regent (75) to attack {C}.",
        OJUTAI_ATTACK,
        f"{C} didn't block Sunscorch Regent (75).",
        f"{D} assigned Thopter Token (638) to block Dragonlord Ojutai (24).",
    ], combat
    resolves = [e for e in evs if e["action"] == "stack_resolve"]
    assert len(resolves) == 1 and resolves[0]["more"] == ["• Destroy all artifacts."], resolves
    # The rest of the shim payload is untouched by the split.
    assert g["zones"] and g["zones"][0]["cardId"] == 638
    assert g["result"]["winner"] == A and r["summary"]["wins"][A] == 1
    print("  shim: the second defender's attack line survives the JSONL rebuild")


def test_readapt_recovers_dropped_combat_lines() -> None:
    """A result adapted before the fix, re-adapted from the same raw log.
    The old adapter is simulated by deleting the continuation event and the
    attached modal text from a fresh parse."""
    raw = _shim_jsonl()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "shim_raw_run77_rot0.jsonl").write_text(raw, encoding="utf-8")
        full = parse_shim_jsonl(raw, source="fixture")
        for g in full["games"]:
            for t in g["turns"]:
                t["events"] = [e for e in t["events"] if e["raw"] != OJUTAI_ATTACK]
                for e in t["events"]:
                    e.pop("more", None)
        full["meta"]["decks"] = ["a.dck", "b.dck", "c.dck", "d.dck"]
        p = tmp / "sim_20260831_162913_run77_rotated.json"
        p.write_text(json.dumps(full), encoding="utf-8")
        # The results index sorts by mtime and shows it as the run's date.
        then = 1_756_000_000
        os.utime(p, (then, then))

        rep = readapt.readapt(p, write=False)
        assert rep["ok"], rep
        assert rep["gained"]["events"] == 1, rep["gained"]
        assert all(rep["gained"][k] == 0 for k in readapt.ENRICHING_KEYS), rep["gained"]

        rep = readapt.readapt(p, write=True)
        assert rep["written"], rep
        after = json.loads(p.read_text(encoding="utf-8"))
        combat = [e["raw"] for t in after["games"][0]["turns"] for e in t["events"]
                  if e["action"] == "combat"]
        assert OJUTAI_ATTACK in combat, combat
        # Meta survives the rewrite; the fingerprint (players, winner, draw,
        # turns) was identical, which is what made the rewrite safe.
        assert after["meta"]["decks"] == ["a.dck", "b.dck", "c.dck", "d.dck"]
        assert after["meta"]["readapted"] is True
        # A re-adapt is not a new run: the file keeps its date.
        assert int(p.stat().st_mtime) == then, p.stat().st_mtime
        assert (tmp / "sim_20260831_162913_run77_rotated.json.bak").is_file()
    print("  readapt: recovers the dropped attack as +1 events, fingerprint and mtime intact")


def main() -> None:
    test_stdout_continuations()
    test_shim_continuations()
    test_readapt_recovers_dropped_combat_lines()
    print("test_combat_lines: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
