#!/usr/bin/env python3
"""Phase lines must be read against the game's own player keys.

Forge names the active player in every phase line by possessive: "<name>'s
Untap step", or "<name>' Upkeep step" when the name ends in s. Commander deck
names carry possessives of their own, and the replay's parse cut at the FIRST
"'s " (web/lib/replay.ts, a lazy regex): the playtester's "Skrat's Revenge's
Main phase, precombat" read as player "Skrat" in phase "Revenge's main phase,
precombat". The header showed that label, the combat test failed on "Revenge's
declare blockers step" so the attack lanes vanished at declare blockers, and
the zone read, not recognising the label, jumped to end-of-turn state.

The fix matches the known player keys, longest first. The adapters never parse
the player out of a phase line (they keep the raw text), so they needed no
change; what this test pins on the Python side:

  1. the rule itself (`phase_owner`, the Python statement of replay.ts
     parsePhase), against the shared cases in fixtures/possessive_names_cases.json,
     which web/scripts/replay_phase.test.mjs runs against the TypeScript;
  2. that the synthetic fixture really exercises the bug: the old lazy regex
     misreads exactly the two possessive seats;
  3. that the shim adapter keeps these names intact end to end (players, turn
     owners, every phase line under the turn of the player it names, the
     multi-defender attack split into one event per defender, blocks), and
     reproduces the committed adapted fixture the TypeScript test reads;
  4. that board.py reads the fixture on both paths without losing a seat.

Regenerate the adapted fixture after changing the JSONL:
    py engine/tests/test_possessive_phase.py --write

Run: py engine/tests/test_possessive_phase.py   (no network, no JVM)
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from shim_log_adapter import parse_shim_jsonl  # noqa: E402
import board  # noqa: E402

FIX = HERE / "fixtures"
JSONL = FIX / "possessive_names_shim.jsonl"
ADAPTED = FIX / "possessive_names.json"
CASES = FIX / "possessive_names_cases.json"

SKRAT = "Ai(1)-Skrat's Revenge"
YURIKO = "Ai(2)-Yuriko's Ninjas"
ATRAXA = "Ai(3)-Atraxa, Praetors' Voice"
GOBLINS = "Ai(4)-Goblins"
PLAYERS = [SKRAT, YURIKO, ATRAXA, GOBLINS]

# Forge's PhaseType labels as the log prints them.
FORGE_PHASES = [
    "Untap step", "Upkeep step", "Draw step", "Main phase, precombat",
    "Beginning of Combat Step", "Declare Attackers Step", "Declare Blockers Step",
    "First Strike Damage Step", "Combat Damage Step", "End of Combat Step",
    "Main phase, postcombat", "End step", "Cleanup step",
]

_AI = re.compile(r"^Ai\(\d+\)-")
_OLD = (re.compile(r"^(.+?)'s (.+)$"), re.compile(r"^(.+?)' (.+)$"))
# Mirrors RE_BLOCK in web/lib/replay.ts (board.py has no block pattern).
_BLOCK = re.compile(r"^(.+?) assigned (.+?) to block (.+?)\.?\s*$")


def _old_parse(raw: str) -> tuple[str, str] | None:
    """The lazy regex replay.ts used before the fix, kept as the fallback."""
    m = _OLD[0].match(raw) or _OLD[1].match(raw)
    return (m.group(1), m.group(2)) if m else None


def possessives(players: list[str]) -> list[tuple[str, str]]:
    """(lead, key) for every way a phase line can open, longest lead first.
    Mirrors phasePossessives() in web/lib/replay.ts."""
    out: list[tuple[str, str]] = []
    for key in players:
        for name in dict.fromkeys([key, _AI.sub("", key)]):
            if not name:
                continue
            out.append((f"{name}'s ", key))
            if name.lower().endswith("s"):
                out.append((f"{name}' ", key))
    return sorted(out, key=lambda lk: -len(lk[0]))


def phase_owner(raw: str, players: list[str]) -> tuple[str, str] | None:
    """(player key, phase label) for a phase line. Mirrors parsePhase()."""
    known = possessives(players)
    no_ai = _AI.sub("", raw)
    for line in ([raw] if no_ai == raw else [raw, no_ai]):
        for lead, key in known:
            if len(line) > len(lead) and line.startswith(lead):
                return key, line[len(lead):]
    return _old_parse(raw)


def _adapt() -> dict:
    result = parse_shim_jsonl(JSONL.read_text(encoding="utf-8"), source=JSONL.name)
    # The adapter stamps today's date; the committed copy must not churn daily.
    result["meta"]["extracted"] = "fixture"
    return result


def test_shared_cases() -> None:
    spec = json.loads(CASES.read_text(encoding="utf-8"))
    assert spec["players"] == PLAYERS, spec["players"]
    n_fallback = 0
    for c in spec["cases"]:
        players = c.get("players", spec["players"])
        got = phase_owner(c["raw"], players)
        assert got == (c["p"], c["label"]), (c["why"], c["raw"], got)
        n_fallback += bool(c.get("fallback"))
    assert n_fallback == 1, n_fallback
    print(f"  {len(spec['cases'])} shared phase-line cases (incl. mirror, prefix collision, fallback)")


def test_fixture_exercises_the_bug(result: dict) -> None:
    game = result["games"][0]
    wrong: dict[str, int] = {}
    total = 0
    for t in game["turns"]:
        for e in t["events"]:
            if e["action"] != "phase":
                continue
            total += 1
            old = _old_parse(e["raw"])
            if old is None or old[0] != t["active_player"]:
                wrong[t["active_player"]] = wrong.get(t["active_player"], 0) + 1
    assert total == 13 * len(game["turns"]), total
    # Skrat took two turns, Yuriko one: 3 turns x 13 lines misread before the
    # fix. Atraxa (comma, inner apostrophe) and Goblins (plain s) read right.
    assert wrong == {SKRAT: 26, YURIKO: 13}, wrong
    print(f"  the old lazy regex misreads {sum(wrong.values())} of {total} phase lines "
          f"(Skrat's Revenge, Yuriko's Ninjas); the fix reads all of them")


def test_adapter_keeps_names(result: dict) -> None:
    assert result["meta"]["agent"] == "simlab-forge-shim/0.15.0", result["meta"]
    game = result["games"][0]
    assert game["players"] == PLAYERS, game["players"]
    assert [t["active_player"] for t in game["turns"]] == [SKRAT, YURIKO, ATRAXA, GOBLINS, SKRAT]
    assert [e["raw"] for e in game["events_pregame"]] == [
        f"{p} has kept a hand of 7 cards" for p in PLAYERS]

    for t in game["turns"]:
        labels = []
        for e in t["events"]:
            if e["action"] == "phase":
                owner = phase_owner(e["raw"], game["players"])
                assert owner is not None and owner[0] == t["active_player"], (t["turn"], e["raw"], owner)
                labels.append(owner[1])
        assert labels == FORGE_PHASES, (t["turn"], labels)

    # Turn 5: one Forge entry attacking two defenders became two combat events.
    t5 = game["turns"][4]
    combat = [e["raw"] for e in t5["events"] if e["action"] == "combat"]
    attacks = [board._ATTACK.match(r) for r in combat]
    lanes = [(m.group(1), [n for n, _ in board._refs(m.group(2))], m.group(3))
             for m in attacks if m]
    assert lanes == [(SKRAT, ["Goblin Instigator"], ATRAXA),
                     (SKRAT, ["Goblin Token"], YURIKO)], lanes
    blocks = [(m.group(1), [n for n, _ in board._refs(m.group(2))], m.group(3))
              for m in map(_BLOCK.match, combat) if m]
    assert blocks == [(ATRAXA, ["Thraben Inspector"], "Goblin Instigator (110)"),
                      (YURIKO, ["Ninja of the Deep Hours"], "Goblin Token (111)")], blocks
    # Turn 4: the control seat's attack and the defender's no-block.
    t4 = [e["raw"] for e in game["turns"][3]["events"] if e["action"] == "combat"]
    m = board._ATTACK.match(t4[0])
    assert (m.group(1), m.group(3)) == (GOBLINS, YURIKO), t4
    m = board._NOBLOCK.match(t4[1])
    assert m.group(1) == YURIKO and board._refs(m.group(2)) == [("Goblin Guide", "410")], t4

    # A turn-capped draw, every seat seeded in the summary under its full key.
    assert game["result"]["draw"] is True and game["result"]["turnCapped"] is True
    assert result["summary"]["wins"] == {p: 0 for p in PLAYERS}, result["summary"]
    assert len(game["zones"]) == 19, len(game["zones"])
    print("  adapter: names intact, every phase line under its owner's turn, "
          "split attack is two lanes, blocks keep the blocking seat")


def test_committed_adapted_fixture(result: dict) -> None:
    committed = json.loads(ADAPTED.read_text(encoding="utf-8"))
    assert committed == result, (
        "fixtures/possessive_names.json is stale: regenerate it with "
        "py engine/tests/test_possessive_phase.py --write")
    print("  fixtures/possessive_names.json matches a fresh adapt of the JSONL")


def test_board_reads_both_paths(result: dict) -> None:
    # Shim path: the zone stream is a read.
    shim = board.validate(result, fetch=False)
    assert shim["basis"] == "zone_stream", shim
    assert shim["exits_total"] == 2 and shim["exit_match_rate"] == 1.0, shim
    final, _ = board.build(result["games"][0], fetch=False)
    snap = final.snapshot()
    names = {p: sorted(c["name"] for c in seat) for p, seat in snap.items()}
    assert names[SKRAT] == ["Goblin Token", "Goblin Token", "Mountain"], names[SKRAT]
    assert names[YURIKO] == ["Island", "Ninja of the Deep Hours"], names[YURIKO]
    assert names[ATRAXA] == ["Plains", "Thraben Inspector"], names[ATRAXA]
    assert names[GOBLINS] == ["Goblin Guide", "Mountain"], names[GOBLINS]

    # Stdout path: the same game without zones is inferred from the text, and
    # the possessive names must still route every card to the right seat.
    stdout = copy.deepcopy(result)
    for g in stdout["games"]:
        g.pop("zones", None)
    inferred = board.validate(stdout, fetch=False)
    assert inferred["basis"] == "inferred", inferred
    assert inferred["exits_total"] == 2 and inferred["exit_match_rate"] == 1.0, inferred
    final, _ = board.build(stdout["games"][0], fetch=False)
    snap = final.snapshot()
    seat_of = {c["name"]: p for p, seat in snap.items() for c in seat}
    assert seat_of["Ninja of the Deep Hours"] == YURIKO, seat_of
    assert seat_of["Thraben Inspector"] == ATRAXA, seat_of
    assert seat_of["Goblin Guide"] == GOBLINS, seat_of
    assert seat_of["Mountain"] in (SKRAT, GOBLINS) and seat_of["Island"] == YURIKO, seat_of
    # Seat routing only: which copies the inference keeps is board.py's own
    # measured limitation (exit_match_rate), not this test's subject.
    assert all(p in PLAYERS for p in seat_of.values()), seat_of
    print(f"  board.py: zone read exit_match_rate {shim['exit_match_rate']}, "
          f"stdout inference {inferred['exit_match_rate']}, every card on its own seat")


def main() -> None:
    result = _adapt()
    if "--write" in sys.argv:
        with open(ADAPTED, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {ADAPTED}")
        return
    test_shared_cases()
    test_fixture_exercises_the_bug(result)
    test_adapter_keeps_names(result)
    test_committed_adapted_fixture(result)
    test_board_reads_both_paths(result)
    print("test_possessive_phase: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
