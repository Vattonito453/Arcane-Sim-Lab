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

# ══ DFC normalisation and the import pre-check (repair plan WS4 tasks 2-3) ══
# A synthetic Forge index: names and layouts only, written here, never read
# from Forge's own card scripts (those are GPL and never committed).
import convert_decklist  # noqa: E402
import forge_index  # noqa: E402
from convert_decklist import convert  # noqa: E402

CARDS = {
    "Ral, Monsoon Mage": {"mode": "DoubleFaced", "types": "Legendary Creature Human Wizard",
                          "faces": ["Ral, Monsoon Mage", "Ral, Leyline Prodigy"]},
    "Birgi, God of Storytelling": {"mode": "Modal", "types": "Legendary Creature God",
                                   "faces": ["Birgi, God of Storytelling",
                                             "Harnfel, Horn of Bounty"]},
    "Sea Gate Restoration": {"mode": "Modal", "types": "Sorcery",
                             "faces": ["Sea Gate Restoration", "Sea Gate, Reborn"]},
    "Fire // Ice": {"mode": "Split", "types": "Instant", "faces": ["Fire", "Ice"]},
    "Winter, Cynical Opportunist": {"mode": None, "types": "Legendary Creature Human Warlock"},
    "Pact of Negation": {"mode": None, "types": "Instant"},
    "Glimmer Test Vault": {"mode": None, "types": "Land"},
    "Sol Ring": {"mode": None, "types": "Artifact"},
    "Island": {"mode": None, "types": "Basic Land Island"},
}
FLAGS = {
    "Winter, Cynical Opportunist": {"remove": "All", "kinds": ["spell", "commander"],
                                    "land": False},
    # Forge's counterspell pre-pass still casts a flagged counterspell...
    "Pact of Negation": {"remove": "All", "kinds": ["counterspell"], "land": False},
    # ...and a flagged land is still played; neither is "won't cast".
    "Glimmer Test Vault": {"remove": "All", "kinds": ["activation"], "land": True},
}
IDX = forge_index.ForgeIndex(Path("."), {"forge_version": "test"}, CARDS, FLAGS)
KINDS = {"unknown_card", "ai_wont_cast", "index_missing"}


def dck_names(content):
    sec, out = "", {"commander": [], "main": []}
    for line in content.splitlines():
        if line.startswith("["):
            sec = line.strip("[]").lower()
        elif sec in out and line[:1].isdigit():
            out[sec].append(line.split(" ", 1)[1])
    return out


def check_shape(warnings):
    for w in warnings:
        assert set(w) == {"kind", "cards", "message"}, w
        assert w["kind"] in KINDS, w
        assert isinstance(w["cards"], list) and isinstance(w["message"], str), w
        assert "—" not in w["message"], w   # no em dash in copy (CLAUDE.md)


RAL_LIST = """1 Ral, Monsoon Mage // Ral, Leyline Prodigy
1 Birgi, God of Storytelling // Harnfel, Horn of Bounty
1 Sea Gate Restoration // Sea Gate, Reborn
1 Fire // Ice
1 Sol Ring
1 _____ Goblin
1 Pact of Negation
1 Glimmer Test Vault
93 Island"""

# transform, modal and modal-land cards go to the front face; split stays "A // B"
content, rep = convert(RAL_LIST, "Ral Test", index=IDX)
got = dck_names(content)
assert got["commander"] == ["Ral, Monsoon Mage"], got
assert "Birgi, God of Storytelling" in got["main"], got
assert "Sea Gate Restoration" in got["main"], got
assert "Fire // Ice" in got["main"], got                 # split keeps " // "
assert [n for n in got["commander"] + got["main"] if " // " in n] == ["Fire // Ice"], got
assert rep["commander"] == "Ral, Monsoon Mage" and rep["forge_index"] == "test", rep
assert {r["from"]: r["to"] for r in rep["renamed"]} == {
    "Ral, Monsoon Mage // Ral, Leyline Prodigy": "Ral, Monsoon Mage",
    "Birgi, God of Storytelling // Harnfel, Horn of Bounty": "Birgi, God of Storytelling",
    "Sea Gate Restoration // Sea Gate, Reborn": "Sea Gate Restoration",
}, rep["renamed"]
check_shape(rep["warnings"])
kinds = [w["kind"] for w in rep["warnings"]]
assert kinds == ["unknown_card"], rep["warnings"]         # Pact and the land are not "won't cast"
unk = rep["warnings"][0]
assert unk["cards"] == ["_____ Goblin"], unk
assert unk["message"].startswith("Forge doesn't know these cards: _____ Goblin."), unk
assert "_____ Goblin" in got["main"]                     # left in, never silently dropped

# a commander named by --commander matches whichever spelling the list used
content, rep = convert(RAL_LIST, "Ral Test", commander="Ral, Monsoon Mage", index=IDX)
assert dck_names(content)["commander"] == ["Ral, Monsoon Mage"]
content, rep = convert(RAL_LIST.replace("Ral, Monsoon Mage // Ral, Leyline Prodigy",
                                        "Ral, Monsoon Mage"),
                       "Ral Test", commander="Ral, Monsoon Mage // Ral, Leyline Prodigy",
                       index=IDX)
assert dck_names(content)["commander"] == ["Ral, Monsoon Mage"]

# a flagged commander: Forge's AI won't cast it, and the warning says so
content, rep = convert("1 Winter, Cynical Opportunist\n1 Pact of Negation\n1 Sol Ring\n96 Island",
                       "Winter Test", index=IDX)
check_shape(rep["warnings"])
wont = [w for w in rep["warnings"] if w["kind"] == "ai_wont_cast"]
assert len(wont) == 1, rep["warnings"]
assert wont[0]["cards"] == ["Winter, Cynical Opportunist"], wont
assert wont[0]["message"].startswith(
    "Forge's AI won't cast these cards: Winter, Cynical Opportunist."), wont
assert "This includes your commander." in wont[0]["message"], wont

# an unknown COMMANDER rejects the deck with the same message
try:
    convert("1 Nobody Such, Commander\n98 Island", "Bad", index=IDX)
    raise AssertionError("an unknown commander must reject the deck")
except SystemExit as e:
    msg = str(e)
    assert msg.startswith("Forge doesn't know these cards: Nobody Such, Commander."), msg
    assert "—" not in msg, msg

# ── no index: Scryfall layout from the card cache, then leave it and say so ──
# cards.py now stores the card's layout on fetch (full-name and face entries),
# which is what this fallback reads.
import cards  # noqa: E402
_dfc = {"name": "Ral, Monsoon Mage // Ral, Leyline Prodigy", "layout": "transform",
        "card_faces": [{"name": "Ral, Monsoon Mage", "type_line": "Legendary Creature"},
                       {"name": "Ral, Leyline Prodigy", "type_line": "Legendary Planeswalker"}]}
assert cards._slim(_dfc)["layout"] == "transform"
assert all(s["layout"] == "transform" for s in cards._face_slims(_dfc).values())

FACTS = {
    "Ral, Monsoon Mage // Ral, Leyline Prodigy": {"layout": "transform"},
    "Birgi, God of Storytelling // Harnfel, Horn of Bounty": {"layout": "modal_dfc"},
    "Fire // Ice": {"layout": "split"},
    # Sea Gate is not cached, or was cached before `layout` existed
    "Sea Gate Restoration // Sea Gate, Reborn": {"type_line": "Sorcery // Land"},
}
asked = []


def facts(names):
    asked.append(list(names))
    return {n: FACTS[n] for n in names if n in FACTS}


content, rep = convert(RAL_LIST, "Ral Test", index=None, card_facts=facts)
got = dck_names(content)
assert len(asked) == 1, asked                            # one batched cache read
assert got["commander"] == ["Ral, Monsoon Mage"], got
assert "Birgi, God of Storytelling" in got["main"] and "Fire // Ice" in got["main"], got
assert "Sea Gate Restoration // Sea Gate, Reborn" in got["main"], got   # unchanged
assert "_____ Goblin" in got["main"]                     # no index: no unknown check
check_shape(rep["warnings"])
assert [w["kind"] for w in rep["warnings"]] == ["index_missing"], rep["warnings"]
im = rep["warnings"][0]
assert im["cards"] == ["Sea Gate Restoration // Sea Gate, Reborn"], im
assert "skipped" in im["message"] and "Sea Gate Restoration // Sea Gate, Reborn" in im["message"], im
assert rep["forge_index"] is None

# no index and nothing cached: every " // " name stays as pasted, and is named
content, rep = convert(RAL_LIST, "Ral Test", index=None, card_facts=lambda n: {})
got = dck_names(content)
assert got["commander"] == ["Ral, Monsoon Mage // Ral, Leyline Prodigy"], got
assert rep["warnings"][0]["kind"] == "index_missing"
assert "Fire // Ice" in rep["warnings"][0]["cards"], rep["warnings"]

# a plain list without an index still converts exactly as before
content, rep = convert("1 Sol Ring\n1 Arcane Signet\n97 Island", "Plain", index=None,
                       card_facts=lambda n: {})
assert dck_names(content) == {"commander": ["Sol Ring"], "main": ["Arcane Signet", "Island"]}
assert rep["warnings"] == [{"kind": "index_missing", "cards": [], "message": rep["warnings"][0]["message"]}]

# ── POST /decks carries the warnings, top level, in the same shape ──────────
import mtg_engine  # noqa: E402

orig = (convert_decklist._load_index, mtg_engine._warm_card_cache, mtg_engine._deck_combos)
convert_decklist._load_index = lambda: IDX
mtg_engine._warm_card_cache = lambda content: 0         # no network in a unit test
mtg_engine._deck_combos = lambda content: {"status": "unknown"}
try:
    res = mtg_engine._import_deck({"name": "Winter Test", "save": False,
                                   "text": "1 Winter, Cynical Opportunist\n1 Sol Ring\n97 Island"})
    assert res["ok"] is True, res
    assert res["warnings"] == res["report"]["warnings"], res
    assert [w["kind"] for w in res["warnings"]] == ["ai_wont_cast"], res["warnings"]
    bad = mtg_engine._import_deck({"name": "Bad", "save": False,
                                   "text": "1 Nobody Such, Commander\n98 Island"})
    assert bad["ok"] is False and bad["warnings"] == [], bad
    assert bad["error"].startswith("Forge doesn't know these cards:"), bad
finally:
    convert_decklist._load_index, mtg_engine._warm_card_cache, mtg_engine._deck_combos = orig

print("ALL ASSERTIONS PASSED")
