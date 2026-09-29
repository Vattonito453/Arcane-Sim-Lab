#!/usr/bin/env python3
"""The R1.1 disclosures (repair plan WS11 task 4, WS4, WS6 task 4).

Per deck, two lists: cards Forge could not load, and cards Forge's AI doesn't
cast on its own. Proves the one rule (a flagged spell; never a flagged land or
counterspell), the lists for a flagged card, a flagged commander, an unknown
card, a DFC spelled "Front // Back", a single-slash name Forge refuses, and a
deck with none; the run path (Forge's own load report, the pre-report
fallback, the worker's record surviving a deleted deck); the exclusion from
"cold" and "cut" verdicts in deck_telemetry and coach; and the payload fields
on the run summary, the deck payload and the import response, with a size
guard on the summary.

Offline by construction: the Forge index here is synthetic (invented flags on
names, never Forge's GPL card scripts). Run:
    py engine/tests/test_disclosure.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

_data = Path(tempfile.mkdtemp(prefix="mtgdisc-"))
os.environ["MTG_DATA_DIR"] = str(_data)
os.environ.pop("MTG_LLM_API_KEY", None)
(_data / "decks").mkdir()
(_data / "sim_results").mkdir()
# archetype classification reads the card cache; the committed warm cache
# keeps it deterministic and offline (as test_coach does)
shutil.copy(ENGINE / "card_cache.json", _data / "card_cache.json")

import forge_index  # noqa: E402

CARDS = {
    "Grim Consult": {"mode": None, "types": "Instant"},
    "Null Pact": {"mode": None, "types": "Instant"},
    "Flag Vault": {"mode": None, "types": "Land"},
    "Wintry Schemer": {"mode": None, "types": "Legendary Creature Human Warlock"},
    "Storm Mage": {"mode": "DoubleFaced", "types": "Legendary Creature Human Wizard",
                   "faces": ["Storm Mage", "Storm Prodigy"]},
    "Tide Restoration": {"mode": "Modal", "types": "Sorcery",
                         "faces": ["Tide Restoration", "Tide, Reborn"]},
    "Heat // Chill": {"mode": "Split", "types": "Instant", "faces": ["Heat", "Chill"]},
    "Plain Rock": {"mode": None, "types": "Artifact"},
    "Sol Ring": {"mode": None, "types": "Artifact"},
    "Island": {"mode": None, "types": "Basic Land Island"},
    # a real card of the committed kilo_helm_final deck, flagged here only
    "Unwinding Clock": {"mode": None, "types": "Artifact"},
    "Kilo, Apogee Mind": {"mode": None, "types": "Legendary Artifact Creature"},
}
FLAGS = {
    "Grim Consult": {"remove": "All", "kinds": ["spell"], "land": False},
    # Forge's counterspell pre-pass still casts it: not listed
    "Null Pact": {"remove": "All", "kinds": ["counterspell"], "land": False},
    # a flagged land is still played: not listed
    "Flag Vault": {"remove": "All", "kinds": ["activation"], "land": True},
    "Wintry Schemer": {"remove": "All", "kinds": ["spell", "commander"], "land": False},
    "Storm Mage": {"remove": "All", "kinds": ["spell", "activation"], "land": False},
    "Heat // Chill": {"remove": "All", "kinds": ["spell"], "land": False},
    "Unwinding Clock": {"remove": "All", "kinds": ["spell"], "land": False},
}
IDX = forge_index.ForgeIndex(Path("."), {"forge_version": "test"}, CARDS, FLAGS)
_real_load = forge_index.load_index
forge_index.load_index = lambda version=None: IDX       # every _AUTO path sees IDX

import disclosure  # noqa: E402

FLAGGED = """[metadata]
Name=Schemer Test
Deck Type=Commander
[Commander]
1 Wintry Schemer|SET|1
[Main]
1 Grim Consult
1 Null Pact
1 Flag Vault
1 Storm Mage // Storm Prodigy
1 Heat // Chill
1 Plain Rock
Nothing Like This
1 Tide Restoration / Tide, Reborn
90 Island
"""
CLEAN = """[metadata]
Name=Clean Test
[Commander]
1 Sol Ring
[Main]
1 Plain Rock
1 Tide Restoration // Tide, Reborn
97 Island
"""
WANT_WONT = ["Wintry Schemer", "Grim Consult", "Storm Mage", "Heat // Chill"]
WANT_UNKNOWN = ["Nothing Like This", "Tide Restoration / Tide, Reborn"]
FLAGGED_FILE = "schemer_test_1234abcd.dck"
CLEAN_FILE = "clean_test.dck"
(_data / "decks" / FLAGGED_FILE).write_text(FLAGGED, encoding="utf-8")
(_data / "decks" / CLEAN_FILE).write_text(CLEAN, encoding="utf-8")


def test_rule():
    ai = disclosure.ai_skips
    assert ai({"kinds": ["spell"], "land": False})
    assert ai({"kinds": ["spell", "counterspell"], "land": False})
    assert not ai({"kinds": ["counterspell"], "land": False})     # pre-pass casts it
    assert not ai({"kinds": ["activation"], "land": True})        # a land is played
    assert not ai({"kinds": ["spell"], "land": True})
    assert not ai(None) and not ai({})


def test_deck_lists():
    d = disclosure.of_deck_text(FLAGGED, IDX)
    assert d["index"] == "test", d
    # flagged spell, flagged commander, a DFC by its front face, a split card;
    # never the counterspell or the land
    assert d["ai_wont_play"] == WANT_WONT, d
    assert d["commander_ai_wont_play"] == ["Wintry Schemer"], d
    # a count-less line still loads in Forge, so it is checked; a single-slash
    # name is one Forge refuses (Richard's "Primal Amulet / Primal Wellspring")
    assert d["could_not_load"] == WANT_UNKNOWN and d["load_basis"] == "index", d
    none = disclosure.of_deck_text(CLEAN, IDX)
    assert none["could_not_load"] == [] and none["ai_wont_play"] == [], none
    assert none["commander_ai_wont_play"] == []
    # no index: "cannot say", never "none"
    blind = disclosure.of_deck_text(FLAGGED, None)
    assert blind == {"index": None, "could_not_load": None, "load_basis": None,
                     "ai_wont_play": None, "commander_ai_wont_play": []}, blind


def test_import_and_deck_page_agree():
    """One derivation: the import's lists equal the deck page's for the .dck
    the import writes."""
    from convert_decklist import convert
    pasted = ("1 Wintry Schemer\n1 Grim Consult\n1 Null Pact\n1 Flag Vault\n"
              "1 Storm Mage // Storm Prodigy\n1 Heat // Chill\n1 Plain Rock\n"
              "1 Nothing Like This\n91 Island")
    content, rep = convert(pasted, "Schemer Test", index=IDX)
    imp = rep["disclosures"]
    page = disclosure.of_deck_text(content, IDX)
    for k in ("index", "could_not_load", "ai_wont_play", "commander_ai_wont_play", "load_basis"):
        assert imp[k] == page[k], (k, imp[k], page[k])
    assert imp["ai_wont_play"] == WANT_WONT and imp["could_not_load"] == ["Nothing Like This"]
    # and the warning names the same cards in the owner's wording
    wont = [w for w in rep["warnings"] if w["kind"] == "ai_wont_cast"][0]
    assert wont["cards"] == imp["ai_wont_play"], wont
    assert wont["message"].startswith("Forge's AI doesn't cast these cards on its own"), wont
    _c, clean = convert("1 Sol Ring\n1 Plain Rock\n97 Island", "Clean", index=IDX)
    assert clean["disclosures"]["ai_wont_play"] == [] and clean["disclosures"]["could_not_load"] == []
    _c, blind = convert("1 Sol Ring\n98 Island", "Blind", index=None, card_facts=lambda n: {})
    assert blind["disclosures"]["ai_wont_play"] is None, blind["disclosures"]


def _meta(**kw):
    return {"source": "rotated", "format": "Commander",
            "decks": [f"/data/decks/{FLAGGED_FILE}", f"/app/engine/decks/{CLEAN_FILE}"], **kw}


def test_run_lists():
    # a run with Forge's own load report: its list, even where the index disagrees
    m = _meta(unsupported_cards=["Nothing Like This"],
              unsupported_by_deck={FLAGGED_FILE: ["Nothing Like This"]})
    r = disclosure.for_run(m)
    assert r["index"] == "test" and set(r["decks"]) == {"Schemer Test", "Clean Test"}, r
    s = r["decks"]["Schemer Test"]
    assert s["file"] == FLAGGED_FILE and s["load_basis"] == "run", s
    assert s["could_not_load"] == ["Nothing Like This"], s
    assert s["ai_wont_play"] == WANT_WONT and s["commander_ai_wont_play"] == ["Wintry Schemer"], s
    c = r["decks"]["Clean Test"]
    assert c["could_not_load"] == [] and c["load_basis"] == "run" and c["ai_wont_play"] == [], c

    # a run from before the load report: the index stands in, labelled so
    old = disclosure.for_run(_meta())["decks"]["Schemer Test"]
    assert old["load_basis"] == "index" and old["could_not_load"] == WANT_UNKNOWN, old

    # the worker's record outlives a deleted deck; the seat name comes from
    # the fidelity rows and the commander from the run's own record
    gone = {"source": "rotated", "decks": ["/data/decks/deleted_deck_0000aaaa.dck"],
            "unsupported_cards": [],
            "commander_fidelity": [{"deck": "deleted_deck_0000aaaa.dck",
                                    "player": "Winter Deck", "commanders": ["Wintry Schemer"]}],
            "commanders": {"Winter Deck": ["Wintry Schemer"]},
            "ai_wont_play_by_deck": {"Winter Deck": ["Wintry Schemer", "Grim Consult"]},
            "ai_wont_play_index": "2.0.13"}
    g = disclosure.for_run(gone)
    assert g["index"] == "2.0.13", g
    row = g["decks"]["Winter Deck"]
    assert row["ai_wont_play"] == ["Wintry Schemer", "Grim Consult"], row
    assert row["commander_ai_wont_play"] == ["Wintry Schemer"], row
    assert row["could_not_load"] == [] and row["load_basis"] == "run", row

    # deleted, nothing recorded: cannot say, under a readable name
    lost = disclosure.for_run({"decks": ["/data/decks/lost_deck_0000bbbb.dck"]})
    assert lost["decks"] == {"Lost Deck": {"file": "lost_deck_0000bbbb.dck",
                                           "could_not_load": None, "load_basis": None,
                                           "ai_wont_play": None,
                                           "commander_ai_wont_play": []}}, lost
    # no index at all: the run's own load report still stands
    blind = disclosure.for_run(m, idx=None)
    assert blind["index"] is None
    assert blind["decks"]["Schemer Test"]["could_not_load"] == ["Nothing Like This"]
    assert blind["decks"]["Schemer Test"]["ai_wont_play"] is None
    assert disclosure.for_result_deck(m, f"/data/decks/{FLAGGED_FILE}")["file"] == FLAGGED_FILE
    assert disclosure.for_result_deck(m, "nope.dck") is None


def test_worker_records_at_run_time():
    import run_sim
    paths = [_data / "decks" / FLAGGED_FILE, _data / "decks" / CLEAN_FILE]
    rec = disclosure.record_for_run(paths, IDX)
    assert rec == {"ai_wont_play_by_deck": {"Schemer Test": WANT_WONT, "Clean Test": []},
                   "ai_wont_play_index": "test"}, rec
    assert disclosure.record_for_run(paths, None) == {}
    meta = run_sim.fidelity_meta([], paths, [], "Commander")
    assert meta["ai_wont_play_by_deck"]["Schemer Test"] == WANT_WONT, meta
    assert meta["ai_wont_play_index"] == "test"
    # and a finished run's meta reads back through the run path unchanged
    r = disclosure.for_run({**_meta(), **meta})
    assert r["decks"]["Schemer Test"]["ai_wont_play"] == WANT_WONT, r


def _game(events):
    return {"players": ["Ai(1)-Schemer Test", "Ai(2)-Clean Test"],
            "result": {"winner": "Ai(2)-Clean Test"},
            "turns": [{"turn": 1, "events": events}]}


def test_telemetry_exclusion():
    import deck_telemetry
    # the precon convention "1 Name|SET|1" is not part of the commander's name,
    # and meta.decks holds container paths, which _find_deck refuses whole
    assert deck_telemetry._commander_of(FLAGGED_FILE) == "Wintry Schemer"
    assert deck_telemetry._commander_of(f"/data/decks/{FLAGGED_FILE}") == "Wintry Schemer"
    result = {"meta": _meta(), "games": [_game([
        {"raw": "Ai(1)-Schemer Test cast Plain Rock", "action": "stack_add"},
        {"raw": "Ai(1)-Schemer Test cast Heat // Chill", "action": "stack_add"},
    ])]}
    rep = deck_telemetry.compute(result, "schemer_test",
                                 watch=["Grim Consult", "Sol Ring", "Plain Rock", "Heat // Chill"])
    assert rep["ai_wont_play"] == WANT_WONT, rep["ai_wont_play"]
    st = {w["name"]: (w["status"], w["ai_wont_play"]) for w in rep["watched"]}
    assert st["Grim Consult"] == ("ai_skips", True), st      # flagged, never seen: no verdict
    assert st["Sol Ring"] == ("cold", False), st             # unflagged, never seen: cold
    assert st["Plain Rock"] == ("partial", False), st
    assert st["Heat // Chill"] == ("partial", True), st      # flagged but cast: measured
    cmd = rep["commander"]
    assert cmd["name"] == "Wintry Schemer" and cmd["status"] == "ai_skips", cmd
    assert cmd["ai_wont_play"] is True
    # unknown (no index, no override): nothing is exempted
    blind = deck_telemetry.compute(result, "schemer_test", watch=["Grim Consult"],
                                   ai_wont_play=None)
    assert blind["watched"][0]["status"] == "cold" and blind["ai_wont_play"] is None, blind


FIXTURE = str(ENGINE / "tests" / "fixtures" / "sim_sample.json")
KILO = str(ENGINE / "decks" / "kilo_helm_final.dck")
GOOD = {
    "verdict": {"headline": "The engine runs", "prose": "It fired. Read it as a floor."},
    "support_chain": [{"link": "Commander ignition", "status": "running",
                       "measured": "T17 med", "reading": "on plan"}],
    "matchups": [{"pod": "Wilhelt Zombies B3", "win_rate": 0.5, "note": "pressure"}],
    "changes": [{"action": "cut", "card": "Sol Ring", "reason": "x",
                 "evidence": "theory"}],
    "play_guide": ["Sequence producers first."],
}


class Stub:
    def __init__(self, replies):
        self.replies, self.calls = replies, 0

    def __call__(self, system, user, **kw):
        self.calls += 1
        return self.replies[min(self.calls, len(self.replies)) - 1]


def test_coach_exclusion():
    import coach
    skipped = ["Unwinding Clock"]
    cut_flagged = json.loads(json.dumps(GOOD))
    cut_flagged["changes"][0]["card"] = "Unwinding Clock"
    try:
        coach._validate(cut_flagged, ["Unwinding Clock", "Sol Ring"], skipped)
        raise AssertionError("a cut of a card Forge's AI doesn't cast must be rejected")
    except ValueError as e:
        assert "doesn't cast it on its own" in str(e) or "doesn't cast on its own" in str(e), e
    coach._validate(GOOD, ["Unwinding Clock", "Sol Ring"], skipped)      # unflagged cut: fine
    cold = json.loads(json.dumps(GOOD))
    cold["support_chain"].append({"link": "Unwinding Clock untaps", "status": "cold",
                                  "measured": "0/g", "reading": "never fired"})
    try:
        coach._validate(cold, ["Sol Ring"], skipped)
        raise AssertionError("a cold row on a card Forge's AI doesn't cast must be rejected")
    except ValueError as e:
        assert "cold" in str(e), e
    cold["support_chain"][-1]["status"] = "ai_skips"
    coach._validate(cold, ["Sol Ring"], skipped)                       # no verdict: fine
    cold["support_chain"][-1]["status"] = "partial"
    coach._validate(cold, ["Sol Ring"], skipped)                       # measured: fine

    # the context the model reads carries the list, and the rule is in writing
    result = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    ctx = coach.build_context(result, KILO)
    assert ctx["ai_wont_play"] == ["Unwinding Clock"], ctx["ai_wont_play"]
    assert any("ai_wont_play" in n for n in ctx["calibration_notes"])
    assert "ai_wont_play" in coach.SYSTEM_PROMPT

    # end to end: output cutting it is rejected, retried once, then fails closed
    os.environ["MTG_LLM_API_KEY"] = "stub"
    real = coach.llm.complete
    try:
        stub = Stub([json.dumps(cut_flagged)])
        coach.llm.complete = stub
        r = coach.report(FIXTURE, KILO, refresh=True)
        assert r["ok"] is False and "doesn't cast" in r["reason"], r
        assert stub.calls == 2, stub.calls
        assert coach.cached_report(FIXTURE, KILO) is None
        stub = Stub([json.dumps(GOOD)])
        coach.llm.complete = stub
        r = coach.report(FIXTURE, KILO, refresh=True)
        assert r["ok"] is True and r["ai_wont_play"] == ["Unwinding Clock"], r
    finally:
        coach.llm.complete = real
        os.environ.pop("MTG_LLM_API_KEY", None)

    # a report cached before the rule: the cut and the cold row are withheld
    import validity
    key = f"{coach.deck_hash(Path(KILO))}-{Path(FIXTURE).stem}"
    old = {"ok": True, **json.loads(json.dumps(cold)),
           "meta": {"validity_version": validity.VALIDITY_VERSION, "model": "m"}}
    old["support_chain"][-1]["status"] = "cold"
    old["changes"] = cut_flagged["changes"] + GOOD["changes"]
    (coach._coaching_dir() / f"{key}.json").write_text(json.dumps(old), encoding="utf-8")
    hit = coach.cached_report(FIXTURE, KILO)
    assert hit["cached"] is True
    assert [c["card"] for c in hit["withheld_cuts"]] == ["Unwinding Clock"], hit
    assert [c["card"] for c in hit["changes"]] == ["Sol Ring"], hit["changes"]
    assert hit["support_chain"][-1]["status"] == "ai_skips", hit["support_chain"]
    assert hit["support_chain"][0]["status"] == "running"
    assert hit["ai_wont_play"] == ["Unwinding Clock"]


def test_payload_fields():
    import mtg_engine as me
    fixture = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    run = {**fixture, "meta": {**fixture["meta"], **_meta(
        unsupported_cards=["Nothing Like This"],
        unsupported_by_deck={FLAGGED_FILE: ["Nothing Like This"]})}}
    (_data / "sim_results" / "sim_disclosure_test.json").write_text(json.dumps(run),
                                                                    encoding="utf-8")
    s = me._read_result_summary("sim_disclosure_test.json")
    d = s["disclosures"]
    assert d["index"] == "test" and set(d["decks"]) == {"Schemer Test", "Clean Test"}, d
    assert d["decks"]["Schemer Test"]["could_not_load"] == ["Nothing Like This"]
    assert d["decks"]["Schemer Test"]["ai_wont_play"] == WANT_WONT
    assert set(d["decks"]["Schemer Test"]) == {"could_not_load", "load_basis", "ai_wont_play",
                                               "commander_ai_wont_play"}, d
    # size guard: two decks, eight names, well under a kilobyte of JSON
    size = len(json.dumps(d, ensure_ascii=False).encode("utf-8"))
    assert size < 700, size
    # the game payload does not carry them (the summary is the smallest one that needs them)
    assert "disclosures" not in me._read_result_game("sim_disclosure_test.json", 1)

    deck = me._read_deck_cards(_data / "decks" / FLAGGED_FILE)
    dd = deck["disclosures"]
    assert dd["index"] == "test" and dd["ai_wont_play"] == WANT_WONT, dd
    assert dd["could_not_load"] == WANT_UNKNOWN and dd["load_basis"] == "index", dd
    assert deck["commanders"] == ["Wintry Schemer"], deck
    assert me._read_deck_cards(_data / "decks" / CLEAN_FILE)["disclosures"]["ai_wont_play"] == []

    import convert_decklist
    orig = (convert_decklist._load_index, me._warm_card_cache, me._deck_combos)
    convert_decklist._load_index = lambda: IDX
    me._warm_card_cache = lambda content: 0
    me._deck_combos = lambda content: {"status": "unknown"}
    try:
        res = me._import_deck({"name": "Schemer Test", "save": False,
                               "text": "1 Wintry Schemer\n1 Grim Consult\n1 Nothing Like This\n"
                                       "96 Island"})
        assert res["ok"] and res["disclosures"] == res["report"]["disclosures"], res
        assert res["disclosures"]["ai_wont_play"] == ["Wintry Schemer", "Grim Consult"], res
        assert res["disclosures"]["commander_ai_wont_play"] == ["Wintry Schemer"]
        assert res["disclosures"]["could_not_load"] == ["Nothing Like This"]
    finally:
        convert_decklist._load_index, me._warm_card_cache, me._deck_combos = orig


def test_no_em_dash_in_engine_copy():
    """Nothing the engine writes into these payloads is copy with an em dash."""
    for text in (FLAGGED, CLEAN):
        blob = json.dumps(disclosure.of_deck_text(text, IDX), ensure_ascii=False)
        assert "—" not in blob, blob


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
    finally:
        forge_index.load_index = _real_load
        shutil.rmtree(_data, ignore_errors=True)
    print("ALL ASSERTIONS PASSED")
