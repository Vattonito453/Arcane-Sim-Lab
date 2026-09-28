#!/usr/bin/env python3
"""run_scenarios.py report parsing: one trial's shim JSONL -> the report row,
rows -> the per-arm summary, and the board check against the writer.

    py studies/scenarios/tests/test_report.py

The JSONL is synthetic but record-for-record in the shape shim 0.17.1
writes (meta, scenario, entry, agent, result), with Forge's own log
phrasing: "Turn N (player)", "devAi(k)-..." for the phase the state set,
"AdditionalAi(k)-..." for an extra combat, "<seat> triggered <card>".
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_scenarios as R  # noqa: E402
import writer as W  # noqa: E402

A, B = "Ai(1)-alpha", "Ai(2)-bravo"


def scenario(tmp: Path) -> dict:
    for name, cmd, main in (("alpha", "Godo, Bandit Warlord", ["Helm of the Host", "Mountain", "Mountain",
                                                                "Sol Ring", "Lightning Bolt"]),
                            ("bravo", "Nadu, Winged Wisdom", ["Island", "Forest", "Counterspell"])):
        (tmp / f"{name}.dck").write_text(
            "[metadata]\nName=%s\n[Commander]\n1 %s\n[Main]\n%s\n" % (name, cmd, "\n".join(f"1 {c}" for c in main)),
            encoding="utf-8")
    sc = {"format": W.FORMAT, "id": "t", "turn": 5, "active": 0, "phase": "MAIN1",
          "seats": [{"deck": str(tmp / "alpha.dck"), "life": 40,
                     "battlefield": [{"card": "Godo, Bandit Warlord", "id": "g"},
                                     {"card": "Helm of the Host", "attached_to": "g"},
                                     {"card": "Mountain", "tapped": True}, {"token": "c_a_treasure_sac"}],
                     "hand": ["Lightning Bolt"]},
                    {"deck": str(tmp / "bravo.dck"), "life": 12, "poison": 2,
                     "battlefield": ["Island"], "hand": ["Counterspell"]}],
          "success": {"type": "win", "seat": 0, "by_turn": 7},
          "line": {"seat": 0, "pieces": ["Godo, Bandit Warlord", "Helm of the Host"]}}
    W.validate(sc)
    return sc


def seats_record(info: dict) -> list:
    """The shim's scenario-record seats for a board loaded exactly as written."""
    ids = iter(range(500, 1000))
    out = []
    for i, s in enumerate(info["seats"]):
        name = (A, B)[i]
        bf, idmap = [], {}
        for sig in s["battlefield"]:
            c = {"id": next(ids), "card": "Treasure Token" if sig["token"] else sig["card"],
                 "tapped": sig["tapped"], "sick": sig["sick"], "sickNow": sig["sick"]}
            if sig["token"]:
                c["token"] = True
            if sig["counters"]:
                c["counters"] = sig["counters"]
            if sig["commander"]:
                c["commander"] = True
            idmap[c["card"]] = c["id"]
            bf.append((c, sig))
        cards = []
        for c, sig in bf:
            if sig["attached_to"]:
                c["attachedTo"] = idmap[sig["attached_to"]]
            cards.append(c)
        z = {"Battlefield": cards}
        for zone in ("hand", "graveyard", "exile", "command", "library"):
            z[zone.capitalize()] = [{"id": next(ids), "card": n} for n in s["zones"][zone]]
        z["Command"].append({"id": next(ids), "card": "Commander Effect"})
        out.append(dict({"name": name, "life": s["life"], "poison": s["poison"], "landsPlayed": 0,
                         "commanderIds": []}, **z))
    return out


def jsonl(info: dict, winner: str | None, turns: int, extra_combats: int = 2) -> list[dict]:
    e = []
    seq = iter(range(10 ** 6))

    def entry(t, m, **kw):
        e.append(dict({"rec": "entry", "game": 0, "seq": next(seq), "type": t, "message": m}, **kw))

    entry("MULLIGAN", f"{A} has kept a hand of 7 cards")
    # A Helm trigger BEFORE the scenario applied (never happens in Forge;
    # here it proves pre-apply entries are ignored).
    entry("STACK_ADD", f"{A} triggered Helm of the Host", card="Helm of the Host", cardId=1)
    entry("TURN", f"Turn 1 ({B})")
    entry("PHASE", f"{B}'s Untap step")
    entry("PHASE", f"dev{A}'s Main phase, precombat")
    entry("PHASE", f"{A}'s Beginning of Combat Step")
    for k in range(extra_combats + 1):
        if k:
            entry("PHASE", f"Additional{A}'s Beginning of Combat Step")
        entry("STACK_ADD", f"{A} triggered Helm of the Host", card="Helm of the Host", cardId=600)
        entry("STACK_RESOLVE", "At the beginning of combat on your turn, create a token", card="Helm of the Host")
        # The first Godo trigger names targets, commas in a card name included.
        tgt = f" targeting [Kiki-Jiki, Mirror Breaker (499), {B}]" if k == 0 else ""
        entry("STACK_ADD", f"{A} triggered Godo, Bandit Warlord{tgt}", card="Godo, Bandit Warlord", cardId=700 + k)
    entry("STACK_ADD", f"{A} cast Lightning Bolt targeting [{B}]", card="Lightning Bolt", cardId=9)
    entry("STACK_ADD", f"{B} activated Godo, Bandit Warlord", card="Godo, Bandit Warlord", cardId=5)  # other seat
    if turns > 5:
        entry("TURN", f"Turn 6 ({B})")
        entry("PHASE", f"{B}'s Beginning of Combat Step")
        entry("TURN", f"Turn 7 ({A})")
        entry("STACK_ADD", f"{A} activated Godo, Bandit Warlord", card="Godo, Bandit Warlord", cardId=700)
    entry("GAME_OUTCOME", f"Turn {turns}")
    recs = [{"rec": "meta", "shim": "0.17.1", "shimCommit": "967cb71a3eef", "players": [A, B],
             "scenario": "trial_0.state", "scenarioSha256": "ab" * 32},
            {"rec": "scenario", "game": 0, "file": "trial_0.state", "sha256": "ab" * 32, "applied": True,
             "before": "1 UNTAP", "turn": 5, "phase": "MAIN1", "active": A, "priority": A,
             "atMs": 700, "applyMs": 300, "lifeRestored": [], "seats": seats_record(info)}]
    recs += e
    recs.append({"rec": "agent", "game": 0, "turn": 5, "player": A, "event": "combo_cast",
                 "detail": "Helm of the Host line=1"})
    recs.append({"rec": "agent", "game": 0, "turn": 5, "player": B, "event": "counter_veto", "detail": "x"})
    recs.append({"rec": "result", "game": 0, "draw": winner is None, "winner": winner, "turns": turns,
                 "timedOut": False, "turnCapped": False,
                 "seats": [{"name": A, "life": 40, "alive": True}, {"name": B, "life": 0, "alive": winner is None}],
                 "ms": 12000})
    return recs


def write_trial(dirp: Path, k: int, recs: list[dict], err: str = "", wall: float = 20.0) -> Path:
    p = dirp / f"trial_{k}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    p.with_suffix(".err").write_text(err, encoding="utf-8")
    p.with_suffix(".cell.json").write_text(json.dumps({"rc": 0, "wall_s": wall}), encoding="utf-8")
    return p


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sc = scenario(tmp)
        _, info = W.build(sc, seed=3)

        # 1. A kill on the scenario turn, board loaded as written.
        p = write_trial(tmp, 0, jsonl(info, A, 5), err="shim: FModel initialized\n")
        t = R.parse_trial(p, sc, info)
        assert t["applied"] and t["board_diffs"] == [] and t["loaded"], t["board_diffs"]
        assert t["winner_seat"] == 0 and t["success"] and t["kill_on_scenario_turn"]
        assert t["turns_to_kill"] == 0
        assert t["piece_counts"] == {"Godo, Bandit Warlord": {"triggered": 3},
                                     "Helm of the Host": {"triggered": 3}}, t["piece_counts"]
        assert t["piece_activity_total"] == 6, "pre-apply and other-seat entries are not counted"
        assert t["piece_targets"] == {"Godo, Bandit Warlord": {"triggered: Kiki-Jiki, Mirror Breaker": 1,
                                                               f"triggered: {B}": 1}}, t["piece_targets"]
        assert t["iterations_scenario_turn"] == 6 and t["iterations_max_turn"] == 6
        assert t["extra_combats_scenario_turn"] == 2 and t["combats_max_turn"] == 3
        assert t["agent_events"] == {"combo_cast": 1, "counter_veto": 1}
        assert t["agent_events_on_pieces"] == 1
        assert t["ms_per_decision"] is None and t["ms_per_turn"] == 12000
        assert t["exceptions"] == 0 and t["wall_s"] == 20.0 and t["shim"] == "0.17.1"
        print("  kill on the scenario turn: loaded, success, pieces, targets, iterations, extra combats: OK")

        # 2. A later kill: counted per turn, turns to kill 2, still inside by_turn.
        p = write_trial(tmp, 1, jsonl(info, A, 7, extra_combats=0),
                        err="java.lang.NullPointerException: boom\n\tat forge.X\n")
        t2 = R.parse_trial(p, sc, info)
        assert t2["success"] and not t2["kill_on_scenario_turn"] and t2["turns_to_kill"] == 2
        assert t2["iterations_scenario_turn"] == 2 and t2["iterations_max_turn"] == 2
        assert t2["piece_counts"]["Godo, Bandit Warlord"] == {"triggered": 1, "activated": 1}
        assert t2["exceptions"] == 1 and "NullPointerException" in t2["exception_samples"][0]
        assert t2["ms_per_turn"] == 4000
        print("  later kill: turns to kill, per-turn iterations, exceptions from stderr: OK")

        # 3. The wrong seat wins, and a draw: neither is a success.
        t3 = R.parse_trial(write_trial(tmp, 2, jsonl(info, B, 6)), sc, info)
        assert t3["winner_seat"] == 1 and not t3["success"] and t3["turns_to_kill"] is None
        t4 = R.parse_trial(write_trial(tmp, 3, jsonl(info, None, 13)), sc, info)
        assert t4["draw"] and not t4["success"] and t4["winner_seat"] is None
        print("  wrong winner and draw are not successes: OK")

        # 4. The board check catches what Forge did not seed as written.
        bad = jsonl(info, A, 5)
        seats = bad[1]["seats"]
        seats[1]["life"] = 10
        seats[0]["Battlefield"][2]["tapped"] = False          # the tapped Mountain
        seats[0]["Library"] = list(reversed(seats[0]["Library"]))
        del seats[0]["Battlefield"][1]["attachedTo"]          # Helm fell off
        seats[0]["Battlefield"] = [c for c in seats[0]["Battlefield"] if not c.get("token")]
        t5 = R.parse_trial(write_trial(tmp, 4, bad), sc, info)
        d = " | ".join(t5["board_diffs"])
        assert not t5["loaded"] and t5["applied"]
        for want in ("seat 1 life 10 != 12", "library order", "battlefield", "tokens 0 != 1"):
            assert want in d, (want, d)
        assert t5["line_loaded"] is False, "Helm fell off Godo: the line itself did not load"
        # A difference off the line (the tapped Mountain untapped) leaves the line loaded.
        off = jsonl(info, A, 5)
        off[1]["seats"][0]["Battlefield"][2]["tapped"] = False
        t5b = R.parse_trial(write_trial(tmp, 4, off), sc, info)
        assert not t5b["loaded"] and t5b["line_loaded"] is True, t5b["board_diffs"]
        assert R.parse_trial(write_trial(tmp, 4, jsonl(info, A, 5)), sc, info)["line_loaded"] is True
        # A line held in hand (S5's Oracle and Consultation) is checked too,
        # not passed because nothing of it is on the battlefield.
        hand_line = dict(sc, line={"seat": 0, "pieces": ["Lightning Bolt"]})
        assert R.parse_trial(write_trial(tmp, 4, jsonl(info, A, 5)), hand_line, info)["line_loaded"] is True
        lost_bolt = jsonl(info, A, 5)
        lost_bolt[1]["seats"][0]["Hand"] = []
        tb = R.parse_trial(write_trial(tmp, 4, lost_bolt), hand_line, info)
        assert tb["line_loaded"] is False and not tb["loaded"], "the line's card left the hand"
        failed = jsonl(info, None, -1)
        failed[1] = {"rec": "scenario", "game": 0, "file": "x", "sha256": "0", "applied": False,
                     "error": "java.lang.RuntimeException: Non-matching number of players"}
        t6 = R.parse_trial(write_trial(tmp, 5, failed), sc, info)
        assert not t6["applied"] and not t6["loaded"] and "Non-matching" in t6["apply_error"]
        print("  board check: life, tapped, library order, attachment, token count, line pieces, failed apply: OK")

        # 5. A missing trial and a truncated one.
        missing = R.parse_trial(tmp / "trial_9.jsonl", sc, info)
        assert missing["ran"] is False
        trunc = tmp / "trial_8.jsonl"
        trunc.write_text(json.dumps(jsonl(info, A, 5)[0]) + "\n{\"rec\":\"sce", encoding="utf-8")
        tt = R.parse_trial(trunc, sc, info)
        assert tt["bad_lines"] == 1 and not tt["has_result"] and not tt["applied"]
        print("  missing and truncated trials: OK")

        # 5b. zone and alive success types (a tutor's pick; not killing yourself).
        def zrec(turn, card, frm, to, owner):
            return {"rec": "zone", "game": 0, "turn": turn, "phase": "MAIN1", "card": card, "cardId": 1,
                    "from": frm, "to": to, "fromPlayer": owner if frm not in ("Stack", "None") else "",
                    "toPlayer": owner, "types": "Artifact", "pt": "", "token": False}
        zsc = dict(sc, success={"type": "zone", "seat": 0, "from": "Library", "to": "Graveyard",
                                "cards": ["Helm of the Host"], "first": True, "by_turn": 6})
        W.validate(zsc)
        base = jsonl(info, None, 13)
        picks = [zrec(1, "Sol Ring", "Library", "Graveyard", A),          # while the state loads
                 zrec(5, "Island", "Library", "Graveyard", B),            # the other seat
                 zrec(5, "Lightning Bolt", "Stack", "Graveyard", A),      # not from the library
                 zrec(5, "Helm of the Host", "Library", "Graveyard", A),  # the pick
                 zrec(6, "Sol Ring", "Library", "Graveyard", A)]
        tz = R.parse_trial(write_trial(tmp, 6, base[:2] + picks + base[2:]), zsc, info)
        assert tz["success"] and tz["zone_first"] == "Helm of the Host", tz.get("zone_moves")
        assert tz["zone_moves"] == ["Helm of the Host", "Sol Ring"], tz["zone_moves"]
        wrong = [zrec(5, "Sol Ring", "Library", "Graveyard", A), zrec(5, "Helm of the Host", "Library", "Graveyard", A)]
        tzw = R.parse_trial(write_trial(tmp, 7, base[:2] + wrong + base[2:]), zsc, info)
        assert not tzw["success"] and tzw["zone_first"] == "Sol Ring"
        anyz = dict(zsc, success=dict(zsc["success"], first=False))
        assert R.parse_trial(write_trial(tmp, 7, base[:2] + wrong + base[2:]), anyz, info)["success"]
        late = [zrec(7, "Helm of the Host", "Library", "Graveyard", A)]
        assert not R.parse_trial(write_trial(tmp, 7, base[:2] + late + base[2:]), zsc, info)["success"]
        typed = dict(zsc, success=dict(zsc["success"], cards=["Nothing"], types_any=["Artifact"]))
        assert R.parse_trial(write_trial(tmp, 6, base[:2] + picks + base[2:]), typed, info)["success"]
        typed2 = dict(zsc, success=dict(zsc["success"], cards=["Nothing"], types_any=["Creature"]))
        assert not R.parse_trial(write_trial(tmp, 6, base[:2] + picks + base[2:]), typed2, info)["success"]
        asc = dict(sc, success={"type": "alive", "seat": 1, "by_turn": 9})
        W.validate(asc)
        assert R.parse_trial(write_trial(tmp, 7, jsonl(info, None, 9)), asc, info)["success"]
        assert not R.parse_trial(write_trial(tmp, 7, jsonl(info, A, 6)), asc, info)["success"]
        # Forge's outcome lines outrank the result's alive flags ...
        lost = jsonl(info, None, 9)
        lost.insert(-1, {"rec": "entry", "game": 0, "seq": 9999, "type": "GAME_OUTCOME",
                         "message": f"{B} has lost trying to draw cards from empty library"})
        assert R.parse_trial(write_trial(tmp, 7, lost), asc, info)["success"] is False
        # ... and without them, a setGameOver that threw leaves the trial unscored.
        threw = R.parse_trial(write_trial(tmp, 8, jsonl(info, None, 9), err=(
            "shim: game 0 setGameOver threw java.lang.NullPointerException: x; recording the game as "
            "ended by the shim\n")), asc, info)
        assert threw["success"] is None and threw["unscored"] and threw["game_over_threw"]
        agg = R.aggregate([threw, R.parse_trial(write_trial(tmp, 7, jsonl(info, None, 9)), asc, info)])
        assert agg["finished"] == 2 and agg["scored"] == 1 and agg["unscored"] == 1 and agg["success"] == 1
        assert agg["success_rate"] == 1.0
        for badsucc in ({"type": "zone", "seat": 0, "by_turn": 6}, {"type": "lose", "seat": 0},
                        {"type": "win", "seat": 5}, dict(zsc["success"], cards=[])):
            try:
                W.validate(dict(sc, success=badsucc))
            except W.ScenarioError:
                continue
            raise AssertionError(f"accepted {badsucc}")
        assert "first Library to Graveyard move by turn 6 is one of: Helm of the Host" in R.success_text(
            zsc["success"]), R.success_text(zsc["success"])
        print("  zone (first pick, any pick, deadline, owner, load-time moves) and alive (outcome lines, unscored) successes: OK")

        # 5c. A cached trial is reused only if it played the state now beside
        # it: after a scenario or deck edit the old game is stale, reported as
        # such and re-run rather than paired with the new board check.
        run_dir = tmp / "run" / "t" / "stock"
        run_dir.mkdir(parents=True)
        state = run_dir.parent / "trial_0.state"
        state.write_text("turn=5\n", encoding="utf-8")
        sha = R.sha256(state)
        recs = jsonl(info, A, 5)
        recs[0]["scenarioSha256"] = recs[1]["sha256"] = sha
        fresh = write_trial(run_dir, 0, recs)
        assert R.recorded_state_sha(fresh) == sha
        assert R.parse_trial(fresh, sc, info)["state_matches"] is True
        saved = R.FORGE_JAR
        R.FORGE_JAR = tmp / "forge.jar"          # run_cell's cwd: any existing directory
        try:
            job = {"label": "t stock 0", "out": fresh, "seed": 0, "force": False, "state": state,
                   "cmd": [sys.executable, "-c", "raise SystemExit(0)"]}
            assert R.run_cell(job).endswith(" cached"), "same state: the finished trial is reused"
            state.write_text("turn=6\n", encoding="utf-8")     # the scenario changed since
            ts = R.parse_trial(fresh, sc, info)
            assert ts["state_matches"] is False and R.aggregate([ts])["stale"] == 1
            md = R.markdown({"run": {"jar_name": "j", "jar_sha256": "0" * 64, "repo_commit": "c", "trials": 1,
                                     "seed": 0, "started": "now"},
                             "scenarios": {"t": {"description": "d", "turn": 5, "success": sc["success"],
                                                 "line": sc["line"],
                                                 "arms": {"stock": {"summary": R.aggregate([ts]),
                                                                    "trials": [ts]}}}}})
            assert "Stale trials (1)" in md, md
            r = R.run_cell(job)
            assert "re-run" in r and not r.endswith(" cached"), r
        finally:
            R.FORGE_JAR = saved
        print("  line pieces in hand; stale cached trials detected, reported and re-run: OK")

        # 5d. run.json keeps every invocation into one --out (a top-up run
        # used to overwrite the first run's provenance).
        rj = tmp / "run_hist.json"
        assert R.previous_invocations(rj) == []
        legacy = {"started": "t0", "finished": "t1", "repo_commit": "abc", "trials": 1, "wall_s": 389.4,
                  "trials_run": 20, "trials_cached": 0, "parallel": 8, "scenarios": {"a": {}, "b": {}}}
        rj.write_text(json.dumps(legacy), encoding="utf-8")
        h = R.previous_invocations(rj)
        assert len(h) == 1 and h[0]["wall_s"] == 389.4 and h[0]["scenarios"] == 2, h
        second = dict(legacy, started="t2", finished="t3", wall_s=82.2, trials_run=3, trials_cached=17)
        second["invocations"] = h + [R.invocation_record(second)]
        rj.write_text(json.dumps(second), encoding="utf-8")
        assert [x["wall_s"] for x in R.previous_invocations(rj)] == [389.4, 82.2]
        crashed = dict(second, started="t4", wall_s=None, invocations=second["invocations"])
        del crashed["finished"]
        rj.write_text(json.dumps(crashed), encoding="utf-8")
        h3 = R.previous_invocations(rj)
        assert len(h3) == 3 and h3[-1]["started"] == "t4" and h3[-1]["finished"] is None, h3
        print("  run.json invocation history (legacy, topped up, interrupted): OK")

        # 6. Aggregate and markdown.
        rows = [t, t2, t3, t4, t5, t6, missing]
        a = R.aggregate(rows)
        assert a["trials"] == 7 and a["finished"] == 6 and a["loaded"] == 4 and a["applied"] == 5
        assert a["success"] == 3 and a["kill_on_scenario_turn"] == 2   # t, t5 (board aside, it won on turn 5)
        assert a["turns_to_kill_median"] == 0 and a["draws"] == 2
        assert a["exceptions"] == 1 and a["success_wilson95"][0] < 0.5 < a["success_wilson95"][1]
        assert R.wilson(0, 0) is None and R.wilson(20, 20)[1] == 1.0 and R.wilson(0, 20)[0] == 0.0
        report = {"run": {"jar_name": "shim.jar", "jar_sha256": "0" * 64, "repo_commit": "abc", "trials": 7,
                          "seed": 10, "started": "now"},
                  "scenarios": {"t": {"description": "d", "turn": 5, "success": sc["success"], "line": sc["line"],
                                      "arms": {"stock": {"summary": a, "trials": rows}}}}}
        md = R.markdown(report)
        assert "| stock | 4 / 4 of 7 | 3/6 |" in md and "Board differences" in md, md
        assert "—" not in md, "no em dash in the report"
        print("  aggregate, Wilson interval and markdown: OK")

    print("report: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
