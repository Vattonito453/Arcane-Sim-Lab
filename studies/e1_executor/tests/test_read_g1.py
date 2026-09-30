#!/usr/bin/env python3
"""The G1 reader (studies/e1_executor/read_g1.py): the strict "stated state
followed by the outlet", the trial success rule, the unhandled-exception
definition and the verdict's precedence, on synthetic records in the shape
shim 0.18.0-proto writes.

    py studies/e1_executor/tests/test_read_g1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import read_g1 as R  # noqa: E402

A = "Ai(1)-alpha"


def agent(event, step, detail, turn=9):
    return {"rec": "agent", "turn": turn, "player": A, "event": event,
            "detail": f"line=l1 step={step} act=0 it=0 ms=0.5 at=10 {detail}".rstrip()}


def entry(seq, typ, msg, card=None):
    e = {"rec": "entry", "seq": seq, "type": typ, "message": msg}
    if card:
        e["card"] = card
    return e


ACT = {"state_step": 0, "outlet_step": 2, "outlet_op": "activate"}
PASS = {"state_step": 0, "outlet_step": 1, "outlet_op": "pass"}


def so(recs, meta, pieces=frozenset({"Kiki"})):
    return R.strict_state_outlet(recs, R.exec_stream(recs), meta, 9, A, set(pieces))


def test_activation_outlet():
    good = [agent("exec_stop", 0, "why=mana_at_least"), agent("exec_step", 2, "op=activate api=DealDamage card=B")]
    assert so(good, ACT) == (True, True)
    # the outlet before the state, on another turn, or the state stopped on max: no
    assert so(list(reversed(good)), ACT) == (True, False)
    assert so([good[0], agent("exec_step", 2, "op=activate", turn=11)], ACT) == (True, False)
    assert so([agent("exec_stop", 0, "why=max"), good[1]], ACT) == (False, False)
    assert so([agent("exec_stop", 0, "why=exhausted canPlay X"), good[1]], ACT) == (False, False)
    assert so([agent("exec_stop", 0, "why=mana_at_least", turn=11), good[1]], ACT) == (False, False)
    # a confirm answer that stopped a loop trigger is not the loop's own stop
    assert so([agent("exec_stop", 0, "op=confirm answer=false why=count card=C"), good[1]], ACT) == (False, False)
    # a data decline is an exec_step, and a bind is not the outlet
    assert so([good[0], agent("exec_step", 2, "op=bind card=B target=X")], ACT) == (True, False)
    assert so([], None) == (False, False)


def test_pass_outlet():
    turn = entry(1, "TURN", "Turn 1 (Ai(4)-delta)")
    line = entry(5, "STACK_ADD", "Ai(1)-alpha activated Kiki (1) targeting [Zealous (2)]", card="Kiki")
    attack = entry(9, "COMBAT", "Ai(1)-alpha assigned Zealous (3), Zealous (4) to attack Ai(2)-beta.")
    late = entry(20, "STACK_ADD", "Ai(1)-alpha triggered Kiki (1)", card="Kiki")   # end-step delayed trigger
    st, ho = agent("exec_stop", 0, "why=power_vs_life"), agent("exec_stop", 1, "why=handoff")
    assert so([turn, line, attack, late, st, ho], PASS) == (True, True)
    # no hand-off, the hand-off before the state, or no attack: no
    assert so([turn, line, attack, st], PASS) == (True, False)
    assert so([turn, line, attack, ho, st], PASS) == (True, False)
    assert so([turn, line, st, ho], PASS) == (True, False)
    # an attack that came before the line's first action (the line ran in main 2): no
    early = entry(3, "COMBAT", "Ai(1)-alpha assigned Goblin (7) to attack Ai(2)-beta.")
    assert so([turn, early, line, st, ho], PASS) == (True, False)
    # a block declaration is not an attack; another seat's attack does not count
    block = entry(9, "COMBAT", "Ai(1)-alpha assigned Wall (8) to block Bear (9).")
    other = entry(9, "COMBAT", "Ai(2)-beta assigned Bear (9) to attack Ai(1)-alpha.")
    assert so([turn, line, block, other, st, ho], PASS) == (True, False)
    # an attack on the next turn does not count
    nxt = entry(15, "TURN", "Turn 10 (Ai(2)-beta)")
    assert so([turn, line, nxt, attack, st, ho], PASS) == (True, False)


def row(**kw):
    r = {"finished": True, "line_loaded": True, "timed_out": False, "kill": False, "so_strict": False,
         "so_harness": False}
    r.update(kw)
    return r


def test_success_rule():
    assert R.success_of(row(kill=True), "stock", "primary")
    assert not R.success_of(row(so_strict=True), "stock", "primary")        # stock: kills only
    assert R.success_of(row(so_strict=True), "exec", "primary")
    assert not R.success_of(row(so_strict=True), "exec", "kills")
    assert R.success_of(row(so_harness=True), "exec", "harness")
    assert not R.success_of(row(so_harness=True), "exec", "primary")
    # not finished, line not loaded, or timed out: a failure whatever else
    for bad in ({"finished": False}, {"line_loaded": False}, {"timed_out": True}):
        assert not R.success_of(row(kill=True, so_strict=True, **bad), "exec", "primary")


def test_unhandled():
    t = {"rc": 0, "ran": True, "has_result": True}
    assert R.unhandled_reasons(t, "") == []
    assert R.unhandled_reasons(t, "java.util.concurrent.CompletionException: java.util.ConcurrentModificationException\n"
                                  "shim: game 0 setGameOver threw java.lang.NullPointerException") == []
    assert R.unhandled_reasons(dict(t, rc=1), "") == ["exit 1"]
    assert R.unhandled_reasons(dict(t, has_result=False), "") == ["no result record"]
    assert R.unhandled_reasons(dict(t, error="IllegalStateException"), "") == ["result error IllegalStateException"]
    assert R.unhandled_reasons(t, "shim: fatal boom") == ["shim: fatal"]
    assert R.unhandled_reasons(t, 'Exception in thread "Game" java.lang.NullPointerException') == ["Exception in thread"]


def synthetic(ex_success: dict, stock_kills: dict | None = None, sub=0, over=0, unhandled_exec=False,
              c1_stock=10, c1_exec=10, agree=18, median=0.4, java_ok=True):
    """Phases shaped as read_phase returns them, for verdict()."""
    stock_kills = stock_kills or {}
    base = dict(finished=True, line_loaded=True, timed_out=False, so_strict=False, so_harness=False,
                sub_chooser=False, budget_stop=False, unhandled=[], decision_ms=[median], kill=False,
                kill_on_scenario_turn=False, turns=9, exec_records=0, printed_exceptions=0, trial=0,
                game_s=40.0, affinity="3", jvm_args=[R.G.ACTIVE_CPUS])
    rows = {}
    for sid in R.G.SCENARIOS:
        k, ks = ex_success.get(sid, 0), stock_kills.get(sid, 0)
        ex = [dict(base, so_strict=i < k, sub_chooser=i < sub, budget_stop=i < over,
                   unhandled=["exit 1"] if (unhandled_exec and i == 0) else []) for i in range(20)]
        st = [dict(base, kill=i < ks) for i in range(20)]
        rows[sid] = {"stock": st, "exec": ex}
    outcome = {"rows": rows}
    timing = {"rows": {sid: {"exec": [dict(base)]} for sid in R.G.SCENARIOS}}
    import json
    src = json.loads((R.G.SUITE / "c1" / "sources.json").read_text(encoding="utf-8"))["chosen"]
    c1rows = {}
    for i, c in enumerate(src):
        won = c["won_within_horizon"]
        # stock agrees with the game on the first `agree` boards
        s_kill = won if i < agree else not won
        c1rows[c["id"]] = {"stock": [dict(base, kill=s_kill)], "exec": [dict(base, kill=s_kill)]}
    # set exact success counts for stock and exec
    ids = list(c1rows)
    for arm, want in (("stock", c1_stock), ("exec", c1_exec)):
        have = sum(c1rows[i][arm][0]["kill"] for i in ids)
        for i in ids:
            if have == want:
                break
            r = c1rows[i][arm][0]
            if have < want and not r["kill"]:
                r["kill"], have = True, have + 1
            elif have > want and r["kill"]:
                r["kill"], have = False, have - 1
    c1 = {"rows": c1rows}
    java = {"passes": java_ok}
    return outcome, c1, timing, java


S1, S2, S3, S4, S6 = R.G.SCENARIOS


def test_verdicts():
    v = lambda *a, **k: R.verdict(*synthetic(*a, **k), "primary")
    assert v({S1: 20, S3: 20, S4: 20, S6: 20})["verdict"] == "GO"
    assert v({S1: 16, S3: 16, S6: 16})["verdict"] == "GO"                   # 3 incl. S1, at the edge
    assert v({S3: 20, S4: 20, S6: 20})["verdict"] == "PARTIAL"              # no trigger scenario
    assert v({S1: 15, S3: 20, S4: 20, S6: 20})["verdict"] == "PARTIAL"
    # stock above 2/20 on a scenario takes it out of the count
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, {S1: 3})["verdict"] == "PARTIAL"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, {S1: 2})["verdict"] == "GO"
    # C1 broken: exec more than 3 below stock, or the control itself off
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, c1_stock=10, c1_exec=6)["verdict"] == "UNDECIDED"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, c1_stock=10, c1_exec=7)["verdict"] == "GO"
    # NO-GO conditions win over GO
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, sub=5)["verdict"] == "NO-GO"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, sub=4)["verdict"] == "GO"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, over=5)["verdict"] == "NO-GO"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, unhandled_exec=True)["verdict"] == "NO-GO"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, median=2000.1)["verdict"] == "NO-GO"
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, median=2000.0)["verdict"] == "GO"
    assert v({S3: 6, S4: 6, S6: 20})["verdict"] == "NO-GO"                  # most at <= 6/20
    assert v({S3: 20, S4: 10, S6: 20})["verdict"] == "UNDECIDED"            # neither branch
    assert v({S1: 20, S3: 20, S4: 20, S6: 20}, java_ok=False)["verdict"] == "UNDECIDED"


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
