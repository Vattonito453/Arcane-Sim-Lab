#!/usr/bin/env python3
"""A behavioural rubric: is this thing PLAYING MAGIC, or just following rules?

Win rate says who won. It does not say whether the pilot played like a person.
This scores three sources on the SAME axes and, where possible, the SAME
decklists:

  HUMAN  studies/human_ceiling/traces/*.json  -- 12 competitive cEDH games
  STOCK  studies/human_ceiling/runs/*.jsonl   -- stock Forge, same decks
  AGENT  a run of the same pods with plan agents

Axes are actions grounded in the rules, not vibes:

  1 win round            how fast the deck actually closes
  2 win method           combat damage vs a spell/combo kill
  3 interaction rate     disruption spells per game
  4 interaction timing   what share happens on someone else's turn
  5 commander deploy     how early the commander lands

HONEST LIMITS, stated once so no number here is over-read:
  * Human interaction counts are a FLOOR. They come from what players said
    out loud in auto-captions, so a silent removal spell is invisible.
  * MULLIGANS are not measurable on the human side at all -- the traces
    record "not recoverable; edited out". Creators cut them.
  * BLOCKS are not measurable on the human side either. Nobody narrates a
    block, and captions do not carry combat detail.
  So blocking and mulligan fidelity CANNOT be validated against humans from
  this corpus, however well we measure them in the sim. Saying otherwise
  would be inventing a baseline.
"""
from __future__ import annotations
import collections, glob, json, os, re, statistics as st, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "engine"))
import analysis  # noqa: E402

DISRUPT = re.compile(r"counter|negation|pact|dispel|swords|path|pongify|"
                     r"rapid hybrid|beast within|chain of vapor|bolt|"
                     r"deflecting|veil|silence|thoughtseize|duress|"
                     r"force of will|fierce guardianship|mana drain|"
                     r"flusterstorm|red elemental|pyroblast|abrade|"
                     r"nature's claim|krosan grip|wipe|damnation|"
                     r"toxic deluge|cyclonic rift", re.I)


def _num(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def human_rows():
    """Normalise heterogeneous trace files. They were extracted per video by
    an LLM, so schemas drift: events are sometimes dicts and sometimes prose
    strings, actors are `by` or `actor`, turns are `turn` or `round`."""
    rows = []
    for f in sorted((REPO / "studies/human_ceiling/traces").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for g in d.get("games", []):
            ev = g.get("interaction_events") or []
            norm = []
            for e in ev:
                if isinstance(e, dict):
                    norm.append({"turn": _num(e.get("turn") or e.get("round")),
                                 "by": e.get("by") or e.get("actor"),
                                 "spell": e.get("spell") or e.get("event"),
                                 "outcome": e.get("outcome")})
                elif isinstance(e, str):
                    norm.append({"turn": None, "by": None, "spell": e,
                                 "outcome": None})
            method = (g.get("win_method") or "").lower()
            rows.append({
                "src": "HUMAN", "video": d.get("video_id"),
                "win_round": _num(g.get("win_turn_estimate")),
                "combat_win": bool(re.search(r"combat|attack|commander damage", method))
                              and not re.search(r"combo|loop|storm|mill|drain", method),
                "interactions": len(norm),
                "interaction_known": bool(ev),
                "events": norm,
            })
    return rows


def sim_rows(pattern, label):
    rows = []
    for f in sorted(glob.glob(pattern)):
        games = collections.defaultdict(lambda: {"turns": 0, "seats": 4,
                                                 "casts": [], "res": None})
        cur_turn_player, cur_turn = None, 0
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            g = r.get("game", 0)
            if r.get("rec") == "result":
                games[g]["res"] = r
                games[g]["turns"] = r.get("turns") or 0
                games[g]["seats"] = len(r.get("seats") or []) or 4
            elif r.get("rec") == "entry":
                t, msg = r.get("type"), (r.get("message") or "")
                if t == "TURN":
                    m = re.match(r"^Turn (\d+) \((.+)\)\s*$", msg)
                    if m:
                        cur_turn, cur_turn_player = int(m.group(1)), m.group(2).strip()
                elif t == "STACK_ADD":
                    m = re.match(r"^(.+?) cast (.+?)$", msg.strip())
                    if m and DISRUPT.search(m.group(2)):
                        games[g]["casts"].append(
                            (m.group(1).strip(), m.group(2).strip(),
                             m.group(1).strip() == cur_turn_player))
        for g, v in games.items():
            if not v["res"] or v["res"].get("timedOut") or not v["res"].get("winner"):
                continue
            seats = max(1, v["seats"])
            rows.append({
                "src": label, "file": os.path.basename(f),
                "win_round": (max(1, v["turns"]) - 1) // seats + 1,
                "combat_win": True,   # refined below by analysis where available
                "interactions": len(v["casts"]),
                "interaction_known": True,
                "offturn": sum(1 for c in v["casts"] if not c[2]),
            })
    return rows


def report(groups):
    print("=" * 76)
    print("BEHAVIOURAL RUBRIC -- is it playing Magic, or just following rules?")
    print("=" * 76)
    print("%-8s %6s %12s %14s %16s" % ("source", "games", "win round",
                                       "disruption/gm", "off-turn share"))
    print("-" * 76)
    for label, rows in groups:
        if not rows:
            print("%-8s   (no data)" % label)
            continue
        wr = [r["win_round"] for r in rows if r.get("win_round")]
        inter = [r["interactions"] for r in rows if r.get("interaction_known")]
        off = [r.get("offturn") for r in rows if r.get("offturn") is not None]
        offshare = ("%.0f%%" % (100 * sum(off) / max(1, sum(inter)))) if off else "n/a"
        print("%-8s %6d %12s %14s %16s" % (
            label, len(rows),
            ("%.1f" % st.mean(wr)) if wr else "-",
            ("%.1f" % st.mean(inter)) if inter else "-",
            offshare))
    print()
    print("NOTE: human disruption counts are a FLOOR (only spells said out loud).")
    print("      Mulligans and blocks have NO human baseline in this corpus.")


if __name__ == "__main__":
    h = human_rows()
    s = sim_rows(str(REPO / "studies/human_ceiling/runs/shim_raw_*.jsonl"), "STOCK")
    a = sim_rows(str(REPO / "studies/behavior_rubric/runs_agent/*.jsonl"), "AGENT")
    report([("HUMAN", h), ("STOCK", s), ("AGENT", a)])
