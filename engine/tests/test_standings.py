#!/usr/bin/env python3
"""The published win rates (engine/standings.py; repair plan WS11 task 9).

Decided games are the one denominator, the engine publishes the rate, whole
percents below 30 decided games, and the run leader is "leader", "tie" or
"none" (no clear leader at or below an even share). These checks pin:

  * how each kind of game ending counts (won, clock, turn cap, draw, crash);
  * the playtester's pod shape: Kess 4 of 7 decided (57%), not 4 of 8 (50%),
    with the winless deck still listed and the average at 25%;
  * tie, no clear leader, and the 30-game precision switch;
  * an unrotated run's "Ai(n)-" keys fold to deck names;
  * from_summary (a job's status) agrees with the games;
  * every consumer reads the same figures: the summary, game and index
    payloads, the scorecards (winRate, decidedGames, digits, order), the
    prediction rows (no "deck file not found" on an unrotated run, the
    decided rate as "Simulated"), the telemetry and the coach's opponents;
  * the scorecard median is the true median (15.5 for wins on 9, 14, 17, 19).

Run: py engine/tests/test_standings.py   -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="simlab_standings_")
os.environ["MTG_DATA_DIR"] = _TMP
os.environ["MTG_EMBEDDED_WORKER"] = "0"

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import standings as S  # noqa: E402

K, SK, ST, KR = "Kess, Reanimator", "Skrat's Revenge", "Stella Lee, Wild Card", "Krenko Goblins"
POD = [K, SK, ST, KR]


def _game(order, winner=None, **marks):
    """One game in seat order; winner is a deck name or None."""
    players = [f"Ai({i + 1})-{d}" for i, d in enumerate(order)]
    res = {"winner": None, "draw": False, "duration_ms": 1000, "raw": ""}
    if winner:
        res["winner"] = players[order.index(winner)]
    res.update(marks)
    return {"players": players, "result": res, "turns": []}


def _richard_like():
    """8 games, one clock-cut (with a stale winner on the record, audit A16):
    Kess 4, Stella 2, Skrat's 1, Krenko 0 of 7 decided."""
    rot = [POD, POD[1:] + POD[:1], POD[2:] + POD[:2], POD[3:] + POD[:3]]
    wins = [SK, K, ST, K, ST, None, K, K]
    games = []
    for i, w in enumerate(wins):
        order = rot[i // 2]
        if w is None:
            games.append(_game(order, winner=K, timedOut=True, draw=True))
        else:
            games.append(_game(order, winner=w))
    return {"meta": {"source": "rotated", "decks": []}, "games": games}


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_outcomes():
    check(S.outcome(_game(POD, K)) == "won", "a winner is decided")
    check(S.outcome(_game(POD, K, timedOut=True)) == "clock",
          "a clock-cut game is not decided, whatever winner it carries")
    check(S.outcome(_game(POD, turnCapped=True, draw=True)) == "turn_cap", "turn cap")
    check(S.outcome(_game(POD, draw=True)) == "draw", "a declared draw")
    check(S.outcome(_game(POD, error="boom")) == "no_result", "a crash")
    check(S.outcome(_game(POD, missingResult=True)) == "no_result", "a lost record")
    check(S.outcome(_game(POD)) == "no_result", "no winner and no mark")
    old = _game(POD)
    old["result"]["raw"] = "Game 3 ended. Ai(2)-Skrat's Revenge has won because all opponents have lost"
    check(S.outcome(old) == "won" and S.winner_of(old) == SK,
          "a null winner with a 'has won' line reads the line (the games table does)")
    check(S.winner_of(_game(POD, K, timedOut=True)) is None, "no winner for a clock cut")
    print("  outcomes: won, clock, turn cap, draw, no result: OK")


def test_playtester_pod():
    t = S.standings(_richard_like())
    check(t["games"] == 8 and t["decided"] == 7, t)
    check(t["undecided"] == {"clock": 1, "turn_cap": 0, "draw": 0, "no_result": 0}, t)
    check(t["pod"] == 4 and t["average"] == 0.25, t)
    check(t["digits"] == 0, "whole percents below 30 decided games")
    names = [d["deck"] for d in t["decks"]]
    check(names == [K, ST, SK, KR], names)
    kess = t["decks"][0]
    check(kess["wins"] == 4 and kess["decided"] == 7 and kess["games"] == 8, kess)
    check(abs(kess["rate"] - 4 / 7) < 1e-4, "4 of 7 decided, not 4 of 8")
    check(t["decks"][-1]["wins"] == 0 and t["decks"][-1]["rate"] == 0.0,
          "the winless deck is listed with a real 0")
    check(t["leader"] == {"kind": "leader", "decks": [K], "rate": kess["rate"]}, t["leader"])
    print("  the playtester's pod: Kess 4 of 7 decided (57%), leader, average 25%: OK")


def test_tie_none_and_precision():
    tie = S.standings({"games": [_game(POD, K), _game(POD, SK), _game(POD, K), _game(POD, SK)]})
    check(tie["leader"]["kind"] == "tie" and tie["leader"]["decks"] == [K, SK], tie["leader"])
    even = S.standings({"games": [_game(POD, d) for d in POD]})
    check(even["leader"] == {"kind": "none", "decks": [], "rate": None},
          "every deck at exactly 1/N: no clear leader")
    nothing = S.standings({"games": [_game(POD, timedOut=True)]})
    check(nothing["decided"] == 0 and nothing["leader"]["kind"] == "none", nothing)
    check(all(d["rate"] is None for d in nothing["decks"]),
          "no decided games: no rate, never a 0 that reads as a loss")
    big = S.standings({"games": [_game(POD, POD[i % 4]) for i in range(30)]})
    check(big["decided"] == 30 and big["digits"] == 1, "one decimal from 30 decided games")
    check(S.standings({"games": [_game(POD, K)] * 29})["digits"] == 0, "29 decided: whole")
    print("  tie, no clear leader, nothing decided, the 30-game precision switch: OK")


def test_unrotated_keys_and_summary():
    run = {"games": [_game(POD, K), _game(POD, ST), _game(POD, K, timedOut=True)]}
    t = S.standings(run)
    check([d["deck"] for d in t["decks"]][:2] == [K, ST], "Ai(n)- prefixes fold away")
    import run_sim
    summary = run_sim._summarize_by_deck(_richard_like()["games"])
    a, b = S.standings(_richard_like()), S.from_summary(summary)
    for k in ("games", "decided", "pod", "average", "digits", "leader"):
        check(a[k] == b[k], (k, a[k], b[k]))
    check([(d["deck"], d["wins"], d["rate"]) for d in a["decks"]]
          == [(d["deck"], d["wins"], d["rate"]) for d in b["decks"]],
          "a job's status publishes the same rates as its result file")
    check(b["undecided"]["clock"] == 1, b["undecided"])
    print("  unrotated keys fold; a job status (from_summary) agrees with the games: OK")


def test_consumers_read_the_same_figures():
    import mtg_engine
    import scorecard
    tmp = Path(_TMP)
    decks_dir = tmp / "decks"
    decks_dir.mkdir(parents=True, exist_ok=True)
    cmdr = {K: "Kess, Dissident Mage", SK: "The Unbeatable Squirrel Girl",
            ST: "Stella Lee, Wild Card", KR: "Krenko, Mob Boss"}
    files = []
    for d in POD:
        f = decks_dir / (d.lower().replace(",", "").replace("'", "_").replace(" ", "_") + "_1a2b3c4d.dck")
        f.write_text(f"[metadata]\nName={d}\n[Commander]\n1 {cmdr[d]}\n[Main]\n1 Sol Ring\n",
                     encoding="utf-8")
        files.append(f"/data/decks/{f.name}")   # container paths, as production records them
    run = _richard_like()
    run["meta"]["decks"] = files
    for g in run["games"]:
        g["result"]["seats"] = [{"name": p, "alive": True} for p in g["players"]]
    name = "sim_20260925_000000_standings_rotated.json"
    (mtg_engine.RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    (mtg_engine.RESULTS_DIR / name).write_text(json.dumps(run), encoding="utf-8")
    want = S.standings(run)

    summ = mtg_engine._read_result_summary(name)
    check(summ["standings"] == want, "summary payload")
    game = mtg_engine._read_result_game(name, 1)
    check(game["standings"] == want, "game payload: the replay's run order")
    idx = [e for e in mtg_engine._list_results() if e["file"] == name][0]
    check(idx["standings"] == want, "results index")

    sc = scorecard.scorecards(run)
    check([d["deck"] for d in sc["decks"]] == [d["deck"] for d in want["decks"]],
          "scorecards in the published order")
    for card, pub in zip(sc["decks"], want["decks"]):
        check(card["winRate"] == pub["rate"] and card["decidedGames"] == pub["decided"],
              (card["deck"], card["winRate"], pub["rate"]))
    check(sc["run"]["decided"] == 7 and sc["run"]["digits"] == 0, sc["run"])

    pred = mtg_engine._read_result_prediction(name)
    if pred.get("available"):
        rows = {r["deck"]: r for r in pred["decks"]}
        check(set(rows) == set(POD), rows.keys())
        check(rows[K]["sim_win_rate"] == 57.1, rows[K])
        check(all(r.get("reason_code") != "deck_file_missing" for r in rows.values()), rows)
        check(pred["digits"] == 0 and pred["decided"] == 7, pred)
    else:
        check(pred.get("reason_code") in ("no_model", "suppressed", "unavailable"), pred)

    # Unrotated: summary.win_rates keyed "Ai(n)-Deck" made every row "deck
    # file not found" (week-3 review, sim_20260723_101044).
    unrot = dict(run, meta=dict(run["meta"], source="live"),
                 summary={"win_rates": {f"Ai({i + 1})-{d}": 0.1 for i, d in enumerate(POD)}})
    uname = "sim_20260925_000001_standings.json"
    (mtg_engine.RESULTS_DIR / uname).write_text(json.dumps(unrot), encoding="utf-8")
    upred = mtg_engine._read_result_prediction(uname)
    if upred.get("available"):
        check(all(r.get("reason_code") != "deck_file_missing" for r in upred["decks"]),
              [r.get("reason") for r in upred["decks"]])
        check({r["deck"] for r in upred["decks"]} == set(POD), upred["decks"])

    tel = mtg_engine._read_result_telemetry(name, "kess")
    check(tel["decided"] == 7 and tel["wins"] == 4, tel)
    check(abs(tel["win_rate"] - round(4 / 7, 3)) < 1e-9, tel["win_rate"])

    import coach
    ctx = coach.build_context(run, str(decks_dir / Path(files[0]).name))
    opp = {o["name"]: o for o in ctx["opponents"]}
    check(K not in opp and opp[ST]["wins"] == 2 and opp[ST]["decided"] == 7, opp)
    check(abs(opp[ST]["win_rate"] - round(2 / 7, 3)) < 1e-9, opp[ST])
    print("  summary, game, index, scorecards, prediction, telemetry, coach: one figure: OK")


def test_true_median():
    import scorecard
    order = [K, SK]
    games = []
    for rounds, winner in ((9, K), (14, K), (17, K), (19, K), (10, SK), (12, SK)):
        g = _game(order, winner)
        g["turns"] = [{"turn": i + 1, "active_player": g["players"][i % 2], "events": []}
                      for i in range(rounds * 2)]
        games.append(g)
    by = {d["deck"]: d for d in scorecard.scorecards({"games": games})["decks"]}
    check(by[K]["medianWinRound"] == 15.5, ("the median of 9, 14, 17, 19", by[K]["medianWinRound"]))
    check(by[SK]["medianWinRound"] == 11, ("the median of 10 and 12", by[SK]["medianWinRound"]))
    check(isinstance(by[SK]["medianWinRound"], int), "a whole median stays an int")
    run = scorecard.scorecards({"games": games[:3]})["run"]
    check(run["medianGameRound"] == 14, run)
    print("  the scorecard median is the true median (15.5, not the upper 17): OK")


def main():
    test_outcomes()
    test_playtester_pod()
    test_tie_none_and_precision()
    test_unrotated_keys_and_summary()
    test_consumers_read_the_same_figures()
    test_true_median()
    print("test_standings: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
