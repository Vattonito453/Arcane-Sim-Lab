#!/usr/bin/env python3
"""The R1 game story end to end on the engine side (repair plan WS11 tasks 1,
6 and 10): game_story's public subset and display switches, commander names
from each deck's [Commander] section, the pilot disclosure, the readapt
commander backfill, run_sim's new meta, and the summary / game / index
payloads that carry them. Synthetic fixtures only: no Forge, no network, no
user data.

Run: py engine/tests/test_game_story.py   ->  ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(HERE))

# Keep every cache and data read away from the tracked files; set before the
# engine modules read MTG_DATA_DIR at import.
_DATA = tempfile.mkdtemp(prefix="game_story_")
os.environ["MTG_DATA_DIR"] = _DATA

import commanders  # noqa: E402
import game_story  # noqa: E402
import mtg_engine  # noqa: E402
import readapt  # noqa: E402
import run_sim  # noqa: E402
import validity  # noqa: E402
from test_qa_knockouts import A, B, C, D, game_one  # noqa: E402

EM_DASH = "—"


# --- switches -----------------------------------------------------------------

def test_switch_defaults_are_not_audited_and_detail_on():
    sw = game_story.switches({})
    assert sw == {"turning_point": "swing", "turning_point_label": "Biggest swing",
                  "knockout_detail": True, "invalid": []}, sw


def test_switch_values():
    sw = game_story.switches({"MTG_TURNING_POINT": "audited", "MTG_KNOCKOUT_DETAIL": "off"})
    assert sw["turning_point_label"] == "Turning point" and sw["knockout_detail"] is False, sw
    sw = game_story.switches({"MTG_TURNING_POINT": " OFF "})
    assert sw["turning_point"] == "off" and sw["turning_point_label"] is None, sw
    sw = game_story.switches({"MTG_TURNING_POINT": "yes please", "MTG_KNOCKOUT_DETAIL": "maybe"})
    assert sw["turning_point"] == "swing" and sw["knockout_detail"] is True, sw
    assert sw["invalid"] == ["MTG_TURNING_POINT", "MTG_KNOCKOUT_DETAIL"], sw


# --- the story ------------------------------------------------------------------

def test_game_one_story_public_subset():
    st = game_story.of_game(game_one(), game_story.switches({}))
    assert set(st) == {"knockouts", "out", "turning_point"}, st
    assert [k["player"] for k in st["knockouts"]] == [D, C, A], st["knockouts"]
    for k in st["knockouts"]:
        assert set(k) == {"player", "turn", "round", "cause", "by", "card", "basis"}, k
        assert k["by"] == B and k["basis"] == "zones", k
    assert [k["cause"] for k in st["knockouts"]] == ["poison", "poison", "combat_damage"]
    assert [k["round"] for k in st["knockouts"]] == [2, 2, 3]
    # Out seats carry the event Forge dates the loss by, for the replay.
    assert [o["player"] for o in st["out"]] == [D, C, A], st["out"]
    for o in st["out"]:
        assert set(o) == {"player", "turn", "round", "seq"} and isinstance(o["seq"], int), o
    tp = st["turning_point"]
    assert tp is not None and tp["label"] == "Biggest swing", tp
    assert tp["basis"] == "zones" and tp["round"] == 1, tp
    assert set(tp) == {"turn", "round", "card", "by", "combat", "basis", "label", "seq",
                       "share_before", "share_after"}, tp
    json.dumps(st)


def test_knockout_detail_off_hides_cause_and_killer_only():
    st = game_story.of_game(game_one(), game_story.switches({"MTG_KNOCKOUT_DETAIL": "off"}))
    for k in st["knockouts"]:
        assert k["cause"] is None and k["by"] is None and k["card"] is None, k
        assert k["player"] and k["round"], k     # who went out, and when, still ship
    assert len(st["out"]) == 3


def test_turning_point_label_follows_the_switch():
    st = game_story.of_game(game_one(), game_story.switches({"MTG_TURNING_POINT": "audited"}))
    assert st["turning_point"]["label"] == "Turning point", st["turning_point"]
    st = game_story.of_game(game_one(), game_story.switches({"MTG_TURNING_POINT": "off"}))
    assert st["turning_point"] is None


def test_stdout_turning_point_is_labelled_inferred():
    st = game_story.of_game(game_one(with_zones=False), game_story.switches({}))
    tp = st["turning_point"]
    assert tp is None or tp["basis"] == "inferred", tp
    for k in st["knockouts"]:
        assert k["basis"] == "log", k


def test_draw_has_no_turning_point_and_bad_game_is_empty():
    g = game_one()
    g["result"] = {"winner": None, "draw": True}
    assert game_story.of_game(g)["turning_point"] is None
    # A clock-cut game is a draw whatever winner it records (audit A16).
    g = game_one()
    g["result"] = {"winner": B, "draw": False, "timedOut": True}
    st = game_story.of_game(g)
    assert st["turning_point"] is None and len(st["out"]) == 3, st
    assert game_story.of_game({"turns": "not a list"}) == game_story.empty()


# --- commanders ---------------------------------------------------------------

def _facts(layout_by_name):
    return lambda names: {n: {"layout": layout_by_name[n]} for n in names
                          if n in layout_by_name}


def test_commander_names_from_the_dck():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tymna.dck"
        p.write_text("﻿[metadata]\nName=Tymna Thrasios\n[Commander]\n"
                     "1 Tymna the Weaver|C16|1\n# a comment\nThrasios, Triton Hero\n"
                     "[Main]\n1 Sol Ring\n", encoding="utf-8")
        info = commanders.dck_identity(p, index=None, card_facts=_facts({}))
    assert info == {"name": "Tymna Thrasios",
                    "commanders": ["Tymna the Weaver", "Thrasios, Triton Hero"]}, info


def test_dfc_names_are_normalised_like_an_import():
    joined = "Ral, Monsoon Mage // Ral, Leyline Prodigy"
    split = "Fire // Ice"
    facts = _facts({joined: "transform", split: "split"})
    assert commanders.display_name(joined, index=None, card_facts=facts) == "Ral, Monsoon Mage"
    assert commanders.display_name(split, index=None, card_facts=facts) == split
    # Neither the index nor the cache knows it: the front face, since no
    # split card can be a commander.
    assert commanders.display_name("Front Face // Back Face", index=None,
                                   card_facts=_facts({})) == "Front Face"

    class Index:
        def resolve(self, name):
            return "Ral, Monsoon Mage" if name == joined else None
    assert commanders.display_name(joined, index=Index(), card_facts=_facts({})) \
        == "Ral, Monsoon Mage"


def test_lookup_goes_through_find_and_reports_missing():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "kess_reanimator_305b76d7.dck").write_text(
            "[metadata]\nName=Kess, Reanimator\n[Commander]\n1 Kess, Dissident Mage\n",
            encoding="utf-8")
        find = lambda f: (tmp / f) if (tmp / f).is_file() else None  # noqa: E731
        found, missing = commanders.lookup(
            ["/data/decks/kess_reanimator_305b76d7.dck", "/data/decks/gone_12345678.dck"],
            find=find)
    assert found == {"Kess, Reanimator": ["Kess, Dissident Mage"]}, found
    assert missing == ["gone_12345678.dck"], missing


def test_of_run_prefers_what_the_run_recorded():
    meta = {"decks": ["x.dck"], "commanders": {"Deck X": ["Recorded Commander"]}}
    assert commanders.of_run(meta, find=lambda f: None) == {"Deck X": ["Recorded Commander"]}
    assert commanders.of_run({"decks": ["x.dck"]}, find=lambda f: None) == {}
    assert commanders.of_run({}, find=lambda f: None) == {}


def test_run_sim_writes_commanders_and_plan_meta():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "krenko.dck"
        p.write_text("[metadata]\nName=Krenko Goblins\n[Commander]\n1 Krenko, Mob Boss\n"
                     "[Main]\n1 Sol Ring\n", encoding="utf-8")
        meta = run_sim.fidelity_meta([], [p], [], "Commander")
    assert meta["commanders"] == {"Krenko Goblins": ["Krenko, Mob Boss"]}, meta
    plans = {"decks": {"a": {"planVersion": 2, "fix": {"tutorReach": True,
                                                      "graveyardDest": False}},
                       "b": {"planVersion": 2, "fix": {"tutorReach": True,
                                                      "graveyardDest": False}}}}
    assert run_sim._plan_meta(plans) == {"plan_version": 2, "plan_fix": ["tutorReach"]}
    assert run_sim._plan_meta({"decks": {"a": {}}}) == {"plan_version": 1}
    assert run_sim._plan_meta({}) == {}


# --- readapt backfill -----------------------------------------------------------

def _result_file(tmp: Path, meta: dict) -> Path:
    p = tmp / "sim_20260925_003803_d0eb966b8d33_rotated.json"
    p.write_text(json.dumps({"meta": meta, "games": [], "summary": {}}), encoding="utf-8")
    os.utime(p, (1_700_000_000, 1_700_000_000))
    return p


def test_backfill_adds_commanders_and_keeps_mtime():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "krenko_goblins.dck").write_text(
            "[metadata]\nName=Krenko Goblins\n[Commander]\n1 Krenko, Mob Boss\n",
            encoding="utf-8")
        find = lambda f: (tmp / f) if (tmp / f).is_file() else None  # noqa: E731
        p = _result_file(tmp, {"decks": ["/app/engine/decks/krenko_goblins.dck",
                                         "/data/decks/deleted_0badf00d.dck"]})
        dry = readapt.backfill_commanders(p, write=False, find=find)
        assert dry["ok"] and not dry["written"], dry
        assert dry["added"] == {"Krenko Goblins": ["Krenko, Mob Boss"]}, dry
        assert dry["missing"] == ["deleted_0badf00d.dck"], dry
        r = readapt.backfill_commanders(p, write=True, find=find)
        assert r["written"], r
        meta = json.loads(p.read_text(encoding="utf-8"))["meta"]
        assert meta["commanders"] == {"Krenko Goblins": ["Krenko, Mob Boss"]}, meta
        assert int(p.stat().st_mtime) == 1_700_000_000, "the run's date must not move"
        again = readapt.backfill_commanders(p, write=True, find=find)
        assert not again["written"] and "already" in again["reason"], again


def test_backfill_never_overwrites_what_the_run_recorded_or_an_old_backup():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "a.dck").write_text("[metadata]\nName=A\n[Commander]\n1 Today's Commander\n",
                                   encoding="utf-8")
        (tmp / "b.dck").write_text("[metadata]\nName=B\n[Commander]\n1 Bee\n",
                                   encoding="utf-8")
        find = lambda f: (tmp / f) if (tmp / f).is_file() else None  # noqa: E731
        p = _result_file(tmp, {"decks": ["a.dck", "b.dck"],
                               "commanders": {"A": ["Run-time Commander"]}})
        bak = p.with_suffix(p.suffix + ".bak")
        bak.write_text("original", encoding="utf-8")
        r = readapt.backfill_commanders(p, write=True, find=find)
        assert r["added"] == {"B": ["Bee"]}, r
        meta = json.loads(p.read_text(encoding="utf-8"))["meta"]
        assert meta["commanders"] == {"A": ["Run-time Commander"], "B": ["Bee"]}, meta
        assert bak.read_text(encoding="utf-8") == "original"


def test_backfill_skips_gracefully_when_no_deck_is_found():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _result_file(tmp, {"decks": ["/data/decks/gone_12345678.dck"]})
        before = p.read_bytes()
        r = readapt.backfill_commanders(p, write=True, find=lambda f: None)
        assert not r["ok"] and not r["written"] and "no deck file found" in r["reason"], r
        assert p.read_bytes() == before
        r = readapt.backfill_commanders(_result_file(tmp, {}), write=True,
                                        find=lambda f: None)
        assert not r["written"] and "no decks" in r["reason"], r


# --- pilot disclosure -----------------------------------------------------------

def _rot(agents):
    decks = [f"d{i}.dck" for i in range(len(agents))]
    return [{"seats": decks[i:] + decks[:i], "agents": agents[i:] + agents[:i]}
            for i in range(len(agents))]


def test_pilot_plan_stock_mixed_unknown():
    plan = validity.pilot({"agent": "simlab-forge-shim/0.15.0", "humanized": True,
                           "rotations_detail": _rot(["plan"] * 4)})
    assert plan["kind"] == "plan" and plan["shim"] == "0.15.0" and plan["random"], plan
    assert plan["label"] == "Piloted by Sim Lab's plan agent on Forge's AI (shim 0.15.0).", plan
    assert plan["note"] == "Some choices are random on purpose.", plan
    stock = validity.pilot({"agent": "simlab-forge-shim/0.15.0", "humanized": False,
                            "humanized_by_rotation": [False] * 4,
                            "rotations_detail": _rot(["stock"] * 4)})
    assert stock["kind"] == "stock" and not stock["random"] and stock["note"] is None, stock
    assert stock["label"] == "Piloted by Forge's own AI (shim 0.15.0).", stock
    stdout = validity.pilot({"humanized": False})
    assert stdout["kind"] == "stock" and stdout["shim"] is None, stdout
    assert stdout["label"] == "Piloted by Forge's own AI.", stdout
    mixed = validity.pilot({"agent": "simlab-forge-shim/0.16.0",
                            "rotations_detail": _rot(["plan", "stock", "stock", "stock"])})
    assert mixed["kind"] == "mixed" and mixed["plan_decks"] == 1, mixed
    assert mixed["stock_decks"] == 3, mixed
    assert validity.pilot({})["kind"] == "unknown"
    v2 = validity.pilot({"agent": "simlab-forge-shim/0.17.0", "humanized": True,
                         "plan_version": 2,
                         "plan_fix": ["commanderTutorZone", "graveyardDest",
                                      "noForcedChoices", "tutorReach"]})
    assert "plan version 2, tutoring fixes on, shim 0.17.0" in v2["label"], v2
    off = validity.pilot({"humanized": True, "random_dials": False})
    assert off["random"] is False and off["note"] is None, off
    # run_sim records the plan whenever plans were built, including a run whose
    # seats all fell back to stock: the label must not name a plan no seat ran.
    fell_back = validity.pilot({"agent": "simlab-forge-shim/0.17.0", "humanized": False,
                                "humanized_by_rotation": [False] * 4,
                                "rotations_detail": _rot(["stock"] * 4),
                                "plan_version": 2, "plan_fix": ["tutorReach"]})
    assert fell_back["kind"] == "stock", fell_back
    assert fell_back["label"] == "Piloted by Forge's own AI (shim 0.17.0).", fell_back
    part = validity.pilot({"agent": "simlab-forge-shim/0.17.0",
                           "rotations_detail": _rot(["plan", "stock", "stock", "stock"]),
                           "plan_version": 2, "plan_fix": []})
    assert "plan version 2, tutoring fixes off" in part["label"], part
    # One rotation of four fell back to stock for every seat: every deck ran
    # the plan in three rotations, so no deck is "on" either pilot alone and
    # the label must count rotations, not claim "0 decks on the plan agent".
    decks = [f"d{i}.dck" for i in range(4)]
    one_down = validity.pilot({
        "agent": "simlab-forge-shim/0.16.0", "humanized": False,
        "humanized_by_rotation": [True, False, True, True],
        "rotations_detail": [{"seats": decks[i:] + decks[:i], "agents": [a] * 4}
                             for i, a in enumerate(["plan", "stock", "plan", "plan"])]})
    assert one_down["kind"] == "mixed", one_down
    assert one_down["label"] == ("Mixed pilots: 3 of 4 seat rotations ran Sim Lab's plan "
                                 "agent, the rest Forge's own AI (shim 0.16.0)."), one_down
    assert "0 decks" not in one_down["label"], one_down
    assert mixed["label"].startswith("Mixed pilots: 1 deck on Sim Lab's plan agent"), mixed
    for p in (plan, stock, stdout, mixed, v2, fell_back, part, one_down):
        assert EM_DASH not in p["label"] and "umaniz" not in p["label"], p


def test_an_all_stock_run_is_not_a_mixed_pod():
    games = [{"result": {"winner": A, "draw": False, "duration_ms": 1000}}]
    base = {"source": "rotated", "clock": 900, "humanized": False}
    v = validity.assess({"meta": {**base, "humanized_by_rotation": [False] * 4},
                         "games": games})
    assert "mixed_pilot" not in v["flags"] and "unknown_pilot" not in v["flags"], v
    assert not any("Mixed pod" in r for r in v["reasons"]), v
    v = validity.assess({"meta": {**base, "humanized_by_rotation": [True, False, True, True]},
                         "games": games})
    assert "mixed_pilot" in v["flags"], v


# --- payloads -----------------------------------------------------------------

def test_summary_game_and_index_carry_story_commanders_and_pilot():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        decks = tmp / "decks"
        decks.mkdir()
        (decks / "skrat.dck").write_text(
            "[metadata]\nName=Skrat's Revenge\n[Commander]\n1 The Unbeatable Squirrel Girl\n",
            encoding="utf-8")
        res = tmp / "sim_results"
        res.mkdir()
        name = "sim_20260925_003803_abcdef012345_rotated.json"
        meta = {"source": "rotated", "agent": "simlab-forge-shim/0.15.0", "humanized": True,
                "decks": ["/data/decks/skrat.dck"], "clock": 900,
                "rotations_detail": _rot(["plan"] * 4)}
        (res / name).write_text(json.dumps({"meta": meta, "games": [game_one()],
                                            "summary": {"games": 1, "draws": 0,
                                                        "wins": {B: 1}, "win_rates": {B: 1.0}}}),
                                encoding="utf-8")
        orig_dirs, orig_res = mtg_engine._deck_dirs, mtg_engine.RESULTS_DIR
        mtg_engine._deck_dirs = lambda: [decks]
        mtg_engine.RESULTS_DIR = res
        saved = {k: os.environ.pop(k, None) for k in ("MTG_TURNING_POINT",
                                                      "MTG_KNOCKOUT_DETAIL")}
        try:
            s = mtg_engine._read_result_summary(name)
            g = mtg_engine._read_result_game(name, 1)
            idx = mtg_engine._list_results()
            os.environ["MTG_TURNING_POINT"] = "audited"
            s2 = mtg_engine._read_result_summary(name)
        finally:
            mtg_engine._deck_dirs, mtg_engine.RESULTS_DIR = orig_dirs, orig_res
            os.environ.pop("MTG_TURNING_POINT", None)
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
    assert s["commanders"] == {"Skrat's Revenge": ["The Unbeatable Squirrel Girl"]}, s
    assert s["pilot"]["kind"] == "plan" and s["pilot"]["shim"] == "0.15.0", s["pilot"]
    assert s["story"] == {"turning_point_label": "Biggest swing", "knockout_detail": True,
                          "basis": "zones"}, s["story"]
    g1 = s["games"][0]
    assert [k["cause"] for k in g1["knockouts"]] == ["poison", "poison", "combat_damage"]
    assert len(g1["out"]) == 3 and g1["turning_point"]["label"] == "Biggest swing", g1
    # The game payload carries the same story for that game.
    for key in ("knockouts", "out", "turning_point"):
        assert g[key] == g1[key], key
    assert g["commanders"] == s["commanders"] and g["pilot"] == s["pilot"]
    assert idx[0]["commanders"] == s["commanders"] and idx[0]["pilot"]["kind"] == "plan", idx
    assert s2["games"][0]["turning_point"]["label"] == "Turning point"
    assert s2["story"]["turning_point_label"] == "Turning point"
    json.dumps(s)
    json.dumps(g)


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
