"""Per-deck scorecards: what each deck DID in a run, not just whether it won.

The results page could only say who won and how long it took. Everything that
answers a deck owner's real questions -- how did it win, how fast, what killed
it, did it block well, did it keep hands it should have shipped -- was either
computed and never surfaced (analysis.win_method) or dropped in the adapter
(the shim's per-seat rubric records). This module reads one adapted result
file and returns one scorecard per deck.

Every figure here is either a direct read of the result record or an
aggregate of the shim's NEUTRAL observer, which scores each seat from live
game state on identical terms. Nothing is inferred from oracle text, and
nothing here is a model prediction (that is predict.py's job, served
separately).

Confidence, stated per section because the UI must not flatten it:
  outcomes   measured   winner, seats, turns come from the result record
  timing     measured   rounds counted per player (see true_round)
  methods    measured   parsed from Forge's own loss lines
  blocking   measured   neutral observer, live power/toughness at decision time
  attacking  measured   same, with the eligible-attacker denominator
  mulligans  measured   GameEventMulligan, every seat, same terms
A section is absent (None) when the run predates the shim version that
emitted it. Absent is not zero, and the UI must say so rather than draw an
empty chart.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

_AI = re.compile(r"^Ai\(\d+\)-")
_LOST = re.compile(r"^(.+?) has lost ")


def bare(player: str) -> str:
    """"Ai(2)-Kilo Helm Final" -> "Kilo Helm Final"."""
    return _AI.sub("", player or "").strip()


def true_round(game: dict, upto_turn_index: int | None = None) -> int:
    """Table rounds, counted per player: a player's Nth turn is round N.

    Dividing Forge's per-player turn counter by seat count undercounts once
    somebody is eliminated (a round is then 3 turns, not 4). Mirrors
    web/lib/replay.ts and studies/behavior_rubric/rubric.py; plan_feedback
    imports this one so Python keeps a single copy.
    """
    taken: dict[str, int] = {}
    best = 0
    for i, t in enumerate(game.get("turns") or []):
        if upto_turn_index is not None and i > upto_turn_index:
            break
        p = t.get("active_player") or ""
        taken[p] = taken.get(p, 0) + 1
        if taken[p] > best:
            best = taken[p]
    return best


def _death_rounds(game: dict) -> dict[str, int]:
    """Round each seat was eliminated, from Forge's own loss lines."""
    out: dict[str, int] = {}
    for i, t in enumerate(game.get("turns") or []):
        for e in t.get("events") or []:
            if e.get("action") != "game_outcome":
                continue
            m = _LOST.match(e.get("raw") or "")
            if m:
                out.setdefault(bare(m.group(1)), true_round(game, i))
    return out


def _rate(num: float, den: float):
    return (num / den) if den else None


def scorecards(result: dict) -> dict:
    """One scorecard per deck, plus run-level context.

    Deliberately does NOT import analysis.analyse(): that report fetches card
    facts and is the right home for combo assembly/conversion. win_method is
    imported lazily so a missing card cache can never take this endpoint down.
    """
    try:
        from analysis import win_method
    except Exception:  # noqa: BLE001
        win_method = None  # type: ignore[assignment]

    games = result.get("games") or []
    decks: dict[str, dict] = {}

    def slot(name: str) -> dict:
        d = decks.get(name)
        if d is None:
            d = {
                "deck": name,
                "games": 0, "wins": 0, "draws": 0, "censored": 0,
                "survived": 0, "decided": 0,
                "winRounds": [], "deathRounds": [],
                "methods": Counter(),
                "block": defaultdict(float), "blockRecs": 0,
                "atk": defaultdict(float), "atkRecs": 0,
                "mull": defaultdict(float), "mullSeats": 0,
                "kept7": 0,
                "ownTurns": 0, "landDrops": 0,
            }
            decks[name] = d
        return d

    run_censored = 0
    for game in games:
        res = game.get("result") or {}
        players = [bare(p) for p in (game.get("players") or [])]
        censored = bool(res.get("timedOut") or res.get("turnCapped"))
        if censored:
            run_censored += 1
        for name in players:
            d = slot(name)
            d["games"] += 1
            if censored:
                d["censored"] += 1

        # Behaviour records: present from shim >= 0.9.0, and only reachable
        # since the adapter started passing them through.
        for r in game.get("rubric") or []:
            name = bare(r.get("player") or "")
            if not name:
                continue
            d = slot(name)
            kind = r.get("kind")
            if kind == "block":
                d["blockRecs"] += 1
                for k in ("incoming", "blocked", "v3", "v2", "v1", "v0",
                          "freeTaken", "freeMissed", "safeMissed",
                          "legalMissed", "lifeTaken"):
                    d["block"][k] += r.get(k, 0) or 0
            elif kind == "attack":
                d["atkRecs"] += 1
                for k in ("attackers", "attackPower", "defenders", "held",
                          "heldEligible"):
                    d["atk"][k] += r.get(k, 0) or 0
                if (r.get("heldBestTough") or 0) > (r.get("backBiggest") or 0):
                    d["atk"]["keptEnough"] += 1
            elif kind == "mull":
                d["mullSeats"] += 1
                d["mull"]["mulls"] += r.get("mulls", 0) or 0
                d["mull"]["lands"] += r.get("lands", 0) or 0
                if not (r.get("mulls") or 0):
                    d["kept7"] += 1

        if censored:
            continue  # a censored game teaches nothing about winning or dying

        # Who was still standing when it ended: a real paired outcome, and the
        # only signal a draw carries. Never folded into a win rate.
        for s in res.get("seats") or []:
            d = slot(bare(s.get("name") or ""))
            d["decided"] += 1
            if s.get("alive"):
                d["survived"] += 1

        # Land drops per own turn. Unlike the behaviour sections this needs no
        # shim records at all: land_drop is a first-class adapter action on
        # both the shim and stdout paths, so it is the one play-quality figure
        # every archived run can answer. It is also the question a Commander
        # player asks first after a loss ("was I screwed, or is my mana bad").
        for t in game.get("turns") or []:
            active = bare(t.get("active_player") or "")
            if not active or active not in decks:
                continue
            decks[active]["ownTurns"] += 1
            for e in t.get("events") or []:
                if e.get("action") == "land_drop" and bare(
                        (e.get("raw") or "").split(" played ")[0]) == active:
                    decks[active]["landDrops"] += 1

        deaths = _death_rounds(game)
        for name, rnd in deaths.items():
            if name in decks:
                decks[name]["deathRounds"].append(rnd)

        winner = res.get("winner")
        if not winner or res.get("draw"):
            for name in players:
                slot(name)["draws"] += 1
            continue
        w = slot(bare(winner))
        w["wins"] += 1
        w["winRounds"].append(true_round(game))
        if win_method is not None:
            try:
                w["methods"][(win_method(game) or {}).get("method") or "other"] += 1
            except Exception:  # noqa: BLE001
                pass

    def med(xs: list[int]):
        if not xs:
            return None
        s = sorted(xs)
        return s[len(s) // 2]

    out = []
    for name, d in decks.items():
        b, a, m = d["block"], d["atk"], d["mull"]
        declinable = b["blocked"] + b["legalMissed"]
        free_opp = b["freeTaken"] + b["freeMissed"]
        blocks_made = b["v3"] + b["v2"] + b["v1"] + b["v0"]
        committable = a["attackers"] + a["heldEligible"]
        out.append({
            "deck": name,
            "games": d["games"],
            "wins": d["wins"],
            "draws": d["draws"],
            "censored": d["censored"],
            "winRate": _rate(d["wins"], d["games"] - d["censored"]),
            "survivalRate": _rate(d["survived"], d["decided"]),
            "medianWinRound": med(d["winRounds"]),
            "medianDeathRound": med(d["deathRounds"]),
            "methods": dict(d["methods"]),
            # None rather than 0 when the deck never took a turn, so the UI
            # can tell "no data" from "never hit a land drop".
            "landsPerTurn": _rate(d["landDrops"], d["ownTurns"]),
            "ownTurns": d["ownTurns"],
            "blocking": None if not d["blockRecs"] else {
                "combats": d["blockRecs"],
                "faced": int(b["incoming"]),
                "engage": _rate(b["blocked"], b["incoming"]),
                "declined": _rate(b["legalMissed"], declinable),
                # Denominators, so a reader (and the copy) can tell "took all
                # of them" off 12 chances from "took all of them" off 1.
                "freeOpportunities": int(free_opp),
                "blocksMade": int(blocks_made),
                "freeCapture": _rate(b["freeTaken"], free_opp),
                # A survive-the-block chance taken shows up as v3 or v1; the
                # observer counts the ones declined in safeMissed.
                "safeCapture": _rate(b["v3"] + b["v1"],
                                     b["v3"] + b["v1"] + b["safeMissed"]),
                "chumpShare": _rate(b["v0"], blocks_made),
                "damagePerCombat": _rate(b["lifeTaken"], d["blockRecs"]),
            },
            "attacking": None if not d["atkRecs"] else {
                "combats": d["atkRecs"],
                "attackersPerCombat": _rate(a["attackers"], d["atkRecs"]),
                "commitment": _rate(a["attackers"], committable),
                "defendersPerAttack": _rate(a["defenders"], d["atkRecs"]),
                "keptEnough": _rate(a["keptEnough"], d["atkRecs"]),
            },
            "mulligans": None if not d["mullSeats"] else {
                "seatGames": d["mullSeats"],
                "kept7": _rate(d["kept7"], d["mullSeats"]),
                "mullsPerGame": _rate(m["mulls"], d["mullSeats"]),
                "landsKept": _rate(m["lands"], d["mullSeats"]),
            },
        })
    out.sort(key=lambda r: (-(r["winRate"] or 0), r["deck"]))

    decided = len(games) - run_censored
    return {
        "decks": out,
        "run": {
            "games": len(games),
            "decided": decided,
            "censored": run_censored,
            # An even table: the number every win rate must be read against.
            "baseline": (1 / len(out)) if out else None,
            "medianGameRound": med([true_round(g) for g in games
                                    if not ((g.get("result") or {}).get("timedOut")
                                            or (g.get("result") or {}).get("turnCapped"))]),
            "hasBehaviour": any(r["blocking"] or r["mulligans"] for r in out),
        },
    }
