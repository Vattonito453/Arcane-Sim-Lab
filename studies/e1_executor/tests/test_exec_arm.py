#!/usr/bin/env python3
"""The E1 exec arm in studies/scenarios/run_scenarios.py: step-file
validation, the plans merge (the channel the shim reads), StepRunner record
parsing and the per-trial and per-arm executor figures.

    py studies/e1_executor/tests/test_exec_arm.py

The agent records are synthetic but in the exact shape shim 0.18.0-proto's
StepRunner writes: detail "line=<id> step=<s> act=<a> it=<n> ms=<x> at=<y>
<fields>".
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
E1 = HERE.parent
REPO = E1.parent.parent
sys.path.insert(0, str(REPO / "studies" / "scenarios"))
import run_scenarios as R  # noqa: E402

A = "Ai(1)-alpha"


def rec(event, step, detail, act=0, it=0, ms=0.5, at=10, turn=9):
    return {"rec": "agent", "game": 0, "turn": turn, "player": A, "event": event,
            "detail": f"line=l1 step={step} act={act} it={it} ms={ms} at={at} {detail}".rstrip()}


def valid_steps() -> dict:
    return {"format": R.STEPS_FORMAT, "deck": "alpha", "state_step": 0, "outlet_step": 1,
            "lines": [{"id": "l1", "pieces": {"Card A": "Battlefield"},
                       "triggers": [{"card": "Card B", "target": {"card": "Card A"}},
                                    {"card": "Card C", "confirm": False}],
                       "steps": [{"loop": [{"op": "activate", "card": "Card A", "api": "Mana"},
                                           {"op": "activate", "card": "Card A", "api": "Untap"}],
                                  "until": {"mana_at_least": 10}, "max": 50},
                                 {"op": "activate", "card": "Card D",
                                  "target": {"player": "opponent", "policy": "lowest_life"},
                                  "until": {"opponents_out": True}}]}]}


def test_committed_step_files_validate():
    files = sorted((E1 / "steps").glob("*.json")) + sorted((E1 / "steps_binary").glob("*.json"))
    assert len(files) >= 6, files
    ids = set()
    for p in files:
        s = json.loads(p.read_text(encoding="utf-8"))
        assert R.validate_steps(s) == [], (p.name, R.validate_steps(s))
        assert s["scenario"] == p.stem, p
        ids.add(p.stem)
        # each names a real suite scenario, and its deck is one of that scenario's seats
        sc = json.loads((REPO / "studies/scenarios/suite" / f"{p.stem}.json").read_text(encoding="utf-8"))
        decks = [Path(seat["deck"]).stem for seat in sc["seats"]]
        assert s["deck"] == decks[sc["line"]["seat"]], (p.name, s["deck"], decks)
    for sid in ("s1_kiki_conscripts", "s2_derevi_emiel_cradle", "s3_druid_reconfiguration",
                "s4_magda_clock_torque", "s6_scepter_reversal"):
        assert sid in ids, sid


def test_validate_rejects():
    assert R.validate_steps(valid_steps()) == []
    cases = [
        (lambda s: s.update(format="x"), "format"),
        (lambda s: s.pop("deck"), "deck"),
        (lambda s: s.update(lines=[]), "lines"),
        (lambda s: s["lines"][0]["steps"][1].update(op="play"), "op"),
        (lambda s: s["lines"][0]["steps"][1].pop("card"), "card is required"),
        (lambda s: s["lines"][0]["steps"][1].update(target={"card": "X", "player": "self"}), "exactly one"),
        (lambda s: s["lines"][0]["steps"][1].update(target={"player": "everyone"}), "self or opponent"),
        (lambda s: s["lines"][0]["steps"][0].update(until={"lethal": 1}), "unknown stop predicate"),
        (lambda s: s["lines"][0]["steps"][0].update(until={"no_progress": {"of": "cards"}}), "no_progress.of"),
        (lambda s: s["lines"][0]["steps"][1].update(zone="Deck"), "zone"),
        (lambda s: s["lines"][0].update(pieces={"Card A": "Board"}), "pieces"),
        (lambda s: s.update(outlet_step=5), "outlet_step"),
        (lambda s: s["lines"][0]["triggers"][0].update(target={"player": "all"}), "self or opponent"),
        (lambda s: s["lines"][0]["steps"][0].update(loop=[]), "loop must be"),
    ]
    for mutate, needle in cases:
        s = copy.deepcopy(valid_steps())
        mutate(s)
        errs = R.validate_steps(s)
        assert errs and any(needle in e for e in errs), (needle, errs)
    # a pass step needs no card
    s = valid_steps()
    s["lines"][0]["steps"][1] = {"op": "pass"}
    assert R.validate_steps(s) == []


def test_load_and_merge():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        assert R.load_steps(td, "nope") is None
        (td / "sx.json").write_text(json.dumps(dict(valid_steps(), scenario="sx",
                                                    plan_patch={"search": {"targets": {"Card E": 9}}})),
                                    encoding="utf-8")
        p, steps = R.load_steps(td, "sx")
        assert p.name == "sx.json" and steps["deck"] == "alpha"
        plans = {"decks": {"alpha": {"planVersion": 2, "search": {"targets": {"Card A": 5}, "context": {}},
                                     "lines": [{"cards": ["Card A"]}]},
                           "bravo": {"planVersion": 2}}}
        pp = td / "plans.json"
        pp.write_text(json.dumps(plans), encoding="utf-8")
        out = R.merge_steps(pp, steps, td, "sx")
        merged = json.loads(out.read_text(encoding="utf-8"))
        a = merged["decks"]["alpha"]
        assert a["steps"] == {"lines": steps["lines"]}                  # only lines cross
        assert a["search"]["targets"] == {"Card A": 5, "Card E": 9}      # deep merge keeps siblings
        assert a["search"]["context"] == {} and a["lines"] == [{"cards": ["Card A"]}]
        assert merged["decks"]["bravo"] == {"planVersion": 2}            # other seats untouched
        assert json.loads(pp.read_text(encoding="utf-8")) == plans       # source not modified
        assert R.merge_steps(pp, steps, td, "sx") == out                 # content-addressed
        # a deck the plans do not hold is refused
        bad = dict(steps, deck="charlie")
        try:
            R.merge_steps(pp, bad, td, "sx")
            raise AssertionError("merge accepted a missing deck")
        except SystemExit:
            pass
        # malformed step files are refused at load
        (td / "sy.json").write_text(json.dumps({"format": R.STEPS_FORMAT}), encoding="utf-8")
        try:
            R.load_steps(td, "sy")
            raise AssertionError("load accepted a malformed file")
        except SystemExit:
            pass


def test_exec_records():
    recs = [rec("exec_arm", 0, "", ms=1.2, at=3),
            rec("exec_step", 0, "op=activate api=CopyPermanent card=Kiki-Jiki, Mirror Breaker target=Zealous Conscripts (500)"),
            rec("exec_step", 0, "op=bind card=Zealous Conscripts target=Kiki-Jiki, Mirror Breaker (499)", it=1),
            rec("exec_stop", 0, "op=confirm answer=false why=count card=Grinding Station"),
            rec("exec_abort", 1, "why=precondition canPlay Clock of Omens"),
            {"rec": "agent", "game": 0, "turn": 9, "player": A, "event": "combo_cast", "detail": "x"},
            {"rec": "agent", "game": 0, "turn": 9, "player": A, "event": "exec_step", "detail": "garbled"}]
    ex = R.exec_records(recs)
    assert [e["event"] for e in ex] == ["exec_arm", "exec_step", "exec_step", "exec_stop", "exec_abort"]
    assert ex[0]["ms"] == 1.2 and ex[0]["at"] == 3 and ex[0]["op"] is None
    assert ex[1]["op"] == "activate" and ex[1]["line"] == "l1"
    assert "card=Kiki-Jiki, Mirror Breaker target=Zealous Conscripts (500)" in ex[1]["detail"]
    assert ex[2]["op"] == "bind" and ex[2]["it"] == 1
    assert ex[3]["why"] == "count" and ex[3]["op"] == "confirm"
    assert ex[4]["why"] == "precondition" and ex[4]["step"] == 1


def combat(msg, seq=50):
    return {"rec": "entry", "game": 0, "seq": seq, "type": "COMBAT", "message": msg}


def turn(n, seq):
    return {"rec": "entry", "game": 0, "seq": seq, "type": "TURN", "message": f"Turn {n} ({A})"}


def test_exec_summary_activate_outlet():
    recs = [rec("exec_arm", 0, ""),
            rec("exec_step", 0, "op=activate api=Mana card=Devoted Druid", ms=2.0),
            rec("exec_step", 0, "op=activate api=Untap card=Devoted Druid", act=1, ms=0.4),
            rec("exec_stop", 0, "why=mana_at_least", it=476, ms=0.3),
            rec("exec_stop", 1, "why=exhausted canPayCost Walking Ballista", ms=3.0),
            rec("exec_step", 2, "op=activate api=DealDamage card=Walking Ballista target=Ai(2)-b", ms=0.1)]
    s = R.exec_summary(recs, A, 9, {"state_step": 0, "outlet_step": 2, "outlet_op": "activate"})
    assert s["armed"] == 1 and s["actions"] == 3 and s["binds"] == 0
    assert s["state"] and s["outlet"] and s["state_then_outlet"]
    assert s["stops"] == {"mana_at_least": 1, "exhausted": 1}
    assert s["decisions"] == 6 and sorted(s["decision_ms"])[-1] == 3.0
    # the state loop ending on exhaustion, max or the budget is not the stated state
    for why in ("exhausted canPlay Gaea's Cradle", "max", "budget"):
        r2 = [r if "why=mana_at_least" not in r["detail"] else rec("exec_stop", 0, f"why={why}") for r in recs]
        s2 = R.exec_summary(r2, A, 9, {"state_step": 0, "outlet_step": 2, "outlet_op": "activate"})
        assert not s2["state"] and s2["outlet"] and not s2["state_then_outlet"], why
    # an outlet that never fired
    s3 = R.exec_summary(recs[:5], A, 9, {"state_step": 0, "outlet_step": 2, "outlet_op": "activate"})
    assert s3["state"] and not s3["outlet"]
    # a confirm stop on the state step is a trigger decision, not the loop's stop
    s4 = R.exec_summary([rec("exec_stop", 0, "op=confirm answer=false why=count card=X")], A, 9,
                        {"state_step": 0, "outlet_step": 1, "outlet_op": "activate"})
    assert not s4["state"] and s4["stops"] == {}
    # no step-file facts: counts only
    s5 = R.exec_summary(recs, A, 9, None)
    assert not s5["state"] and not s5["outlet"] and s5["actions"] == 3


def test_exec_summary_pass_outlet():
    base = [{"rec": "entry", "game": 0, "seq": 1, "type": "MULLIGAN", "message": "kept"}, turn(1, 2),
            rec("exec_arm", 0, ""), rec("exec_stop", 0, "why=power_vs_life", it=44),
            rec("exec_stop", 1, "why=handoff")]
    meta = {"state_step": 0, "outlet_step": 1, "outlet_op": "pass"}
    atk = combat(f"{A} assigned Zealous Conscripts (840), Zealous Conscripts (860) to attack Ai(2)-b.")
    s = R.exec_summary(base + [atk], A, 9, meta)
    assert s["state"] and s["outlet"] and s["state_then_outlet"]
    # the attack must be the line seat's, on the scenario turn
    other = combat("Ai(2)-b assigned Goblin Token (899) to attack " + A + ".")
    assert not R.exec_summary(base + [other], A, 9, meta)["outlet"]
    late = [turn(10, 60), atk]
    assert not R.exec_summary(base + late, A, 9, meta)["outlet"]
    # no hand-off record, no outlet
    assert not R.exec_summary(base[:4] + [atk], A, 9, meta)["outlet"]


def test_parse_trial_and_aggregate():
    sc = {"id": "t", "turn": 9, "success": {"type": "win", "seat": 0, "by_turn": 9},
          "line": {"seat": 0, "pieces": ["Walking Ballista"]}}
    meta = {"state_step": 0, "outlet_step": 2, "outlet_op": "activate"}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        rows = []
        for k, (won, ms) in enumerate(((True, [0.2, 0.4, 9.0]), (False, [1.0]))):
            recs = [{"rec": "meta", "shim": "0.18.0-proto", "players": [A, "Ai(2)-b"], "plansSha256": "ab"},
                    turn(1, 1)]
            recs += [rec("exec_arm", 0, "", ms=ms[0])]
            if won:
                recs += [rec("exec_stop", 0, "why=mana_at_least", ms=ms[1]),
                         rec("exec_step", 2, "op=activate api=DealDamage card=Walking Ballista target=Ai(2)-b",
                             ms=ms[2])]
            else:
                recs += []
            recs.append({"rec": "result", "game": 0, "winner": A if won else None, "draw": not won,
                         "turns": 9 if won else 13, "ms": 1000, "turnCapped": not won, "seats": []})
            p = td / "exec" / f"trial_{k}.jsonl"
            p.parent.mkdir(exist_ok=True)
            p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
            p.with_suffix(".err").write_text("" if won else "shim: fatal: boom\n", encoding="utf-8")
            p.with_suffix(".cell.json").write_text(json.dumps({"rc": 0 if won else 1, "wall_s": 5}), encoding="utf-8")
            assert R.recorded_plans_sha(p) == "ab"
            rows.append(R.parse_trial(p, sc, None, meta))
        t0, t1 = rows
        assert t0["success"] and t0["exec"]["state_then_outlet"] and t0["ms_per_decision"] == 0.4
        assert not t0["unhandled"] and t1["unhandled"]
        assert not t1["exec"]["state"] and t1["ms_per_decision"] == 1.0
        agg = R.aggregate(rows)
        e = agg["exec"]
        assert e["trials"] == 2 and e["armed"] == 2 and e["state_then_outlet"] == 1
        assert e["decisions"] == 4 and e["decision_ms_median"] == 0.7 and e["decision_ms_max"] == 9.0
        assert agg["ms_per_decision"] == 0.7 and agg["unhandled"] == 1
        # a stock trial (no exec records, no step facts) carries no exec block
        plain = R.parse_trial(td / "exec" / "trial_1.jsonl", sc, None, None)
        assert "exec" in plain  # it has an exec_arm record
        p = td / "exec" / "trial_2.jsonl"
        p.write_text(json.dumps({"rec": "meta", "players": [A]}) + "\n" +
                     json.dumps({"rec": "result", "game": 0, "winner": None, "turns": 13, "seats": []}),
                     encoding="utf-8")
        stock = R.parse_trial(p, sc, None, None)
        assert "exec" not in stock and stock["ms_per_decision"] is None
        assert "exec" not in R.aggregate([stock])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("ALL ASSERTIONS PASSED")
