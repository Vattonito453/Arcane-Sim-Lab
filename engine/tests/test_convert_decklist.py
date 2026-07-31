#!/usr/bin/env python3
"""Unit test for convert_decklist.parse — both accepted formats and the traps.

The client-side checks (parseList in web/app/import/page.tsx) accept plain
"1 Card Name" lines, so the server parser must too, or the Checks panel says a
list is fine and the engine then rejects it on save. Keep the two in lockstep.
Run: python3 tests/test_convert_decklist.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convert_decklist import parse  # noqa: E402

def entries(text):
    return parse(text)[0]

# ── plain MTGO-style lines, no set codes ──────────────────────────────────
main = entries("1 Kilo, Apogee Mind\n1 Sol Ring\n40 Island")
assert main == [(1, "Kilo, Apogee Mind"), (1, "Sol Ring"), (40, "Island")], main
# a comma'd card name is ONE card, never split
assert main[0][1] == "Kilo, Apogee Mind"

# "3x Island" count syntax
assert entries("3x Island") == [(3, "Island")]

# foil marker and bare set-code tails are stripped, matching the client
assert entries("1 Lightning Bolt *F*") == [(1, "Lightning Bolt")]
assert entries("1 Lightning Bolt (2XM) 336 *F*") == [(1, "Lightning Bolt")]
assert entries("1 Lightning Bolt (2XM)") == [(1, "Lightning Bolt")]

# ── set-coded Moxfield/Arena lines still parse exactly as before ──────────
assert entries("1 Inspirit, Flagship Vessel (EOC) 2 F") == [(1, "Inspirit, Flagship Vessel")]
assert entries("1 Flux Channeler (PLST) WAR-52") == [(1, "Flux Channeler")]
assert entries("1 Tekuthal, Inquiry Dominus (PONE) 71p") == [(1, "Tekuthal, Inquiry Dominus")]

# multi-entry single-line export splits on each (SET) num anchor
one_line = entries("1 Sol Ring (EOC) 53 1 Arcane Signet (EOC) 54 3 Island (EOE) 269")
assert one_line == [(1, "Sol Ring"), (1, "Arcane Signet"), (3, "Island")], one_line

# mixed plain and set-coded lines in one list
mixed = entries("1 Sol Ring (EOC) 53\n1 Krenko, Mob Boss\n2 Mountain")
assert mixed == [(1, "Sol Ring"), (1, "Krenko, Mob Boss"), (2, "Mountain")], mixed

# ── lines that must NOT parse ─────────────────────────────────────────────
# comments would otherwise read as "85 more cards…"
assert entries("# 85 more cards in the full Kilo list") == []
assert entries("// a comment") == []
# headers and blanks
assert entries("Deck\n\nCommander") == []
# a bare number is not an entry
assert entries("42") == []

# ── sideboard split unchanged ─────────────────────────────────────────────
m, side = parse("1 Sol Ring\nSIDEBOARD:\n1 Pithing Needle")
assert m == [(1, "Sol Ring")] and side == [(1, "Pithing Needle")], (m, side)

print("ALL ASSERTIONS PASSED")
