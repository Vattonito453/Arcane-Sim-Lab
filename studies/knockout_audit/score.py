"""Score the analyzer against the frozen readings, exactly as PREREG.md says.

    py studies/knockout_audit/score.py <analyzer_output.json> [--out items.json]
        [--self-mode literal|seat|null]

Inputs:
  - sample.json (this folder): the 40 sampled knockouts and 20 turning-point games.
  - readings/{A1,A2,B1,B2,C}.json (this folder): the frozen readings. A1/A2 are
    pass A, B1/B2 pass B, C is the third reading (pass C) of every game where A
    and B differed on a scored item.
  - analyzer_output.json: {"blob": ..., "games": {"R-g01": {"knockouts": [...],
    "turning_point": {...} | null}, ...}} as written by run_analyzer.py.

Rules implemented (PREREG "Reading passes and how they combine", "Agreement rules"):

  Knockout. A reading agrees with the analyzer's knockout for the same player in
  the same game when turn, cause class and killer seat all match. Killer: the
  analyzer's `by`; both absent counts as the same; seats compared as printed, or
  with the "Ai(n)-" prefix removed from both if one side omits it. The card is
  scored separately (case-insensitive, instance numbers removed) and is not part
  of the pass rule. No analyzer knockout for the player = disagree.

  Turning point. A reading agrees when the analyzer's turn equals the reading's
  turn, or differs by exactly one Forge turn and the analyzer's card
  (`event_hint`) names the reading's card ("combat" matches "combat"). No
  analyzer turning point for a decided game = disagree.

  Combining. An item's readings are pass A, pass B and, when the game was read
  in pass C, pass C. The item agrees if a strict majority of its readings agree.
  (Where A and B are identical they give one verdict; where they differ pass C
  exists, so this is the PREREG's "majority of three".) A missing or malformed
  reading of an item counts as a reading that disagrees.

  Human consensus per field: the value at least two readings share, else
  "no consensus".

One value the PREREG schema does not define, decided before the analyzer was
run on these files: both deck-out readings of S-g06 give the killer as "self".
READER.md asks for a seat as printed, or null for a deck-out, so "self" is not a
well-formed killer. `--self-mode literal` (the default and the verdict) applies
the PREREG's malformed-reading rule to that field: the reading disagrees.
`seat` reads it as the eliminated player's own seat, `null` as no killer; both
are reported as sensitivity only.

Turns: passes A and B returned turns as digit strings (the reader harness's
output shape); a string of digits is read as that integer. Anything else is
malformed.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PASS_OF = {"A1": "A", "A2": "A", "B1": "B", "B2": "B", "C": "C"}
KO_THRESHOLD = 38   # of 40
TP_THRESHOLD = 16   # of 20
PATH_OF_RUN = {"R": "shim", "S": "shim", "T": "stdout"}

_AI = re.compile(r"^Ai\(\d+\)-")
_INST = re.compile(r"\s*\(\d+\)")


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

class Malformed(Exception):
    pass


def as_turn(v):
    if isinstance(v, bool):
        raise Malformed(f"turn {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    raise Malformed(f"turn {v!r}")


def norm_card(v):
    if v is None:
        return None
    s = _INST.sub("", str(v)).strip().lower()
    return s or None


def seats_equal(a, b) -> bool:
    """PREREG killer comparison. None == None."""
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    # Prefix removed from both only when one side omits it.
    if bool(_AI.match(a)) != bool(_AI.match(b)):
        return _AI.sub("", a) == _AI.sub("", b)
    return False


def reading_killer(e: dict, player: str, self_mode: str):
    """The reading's killer as a seat string or None; Malformed if not well formed."""
    k = e.get("killer")
    if k is None:
        return None
    if not isinstance(k, str):
        raise Malformed(f"killer {k!r}")
    if k.strip().lower() in ("self", "none", "null", ""):
        if k.strip().lower() == "self":
            if self_mode == "seat":
                return player
            if self_mode == "null":
                return None
        raise Malformed(f"killer {k!r}")
    return k


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_readings() -> dict[str, dict[str, dict]]:
    """{game: {pass: game_reading}}; a pass may cover a game at most once."""
    by_game: dict[str, dict[str, dict]] = defaultdict(dict)
    for rid, pas in PASS_OF.items():
        p = HERE / "readings" / f"{rid}.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        for g in doc["games"]:
            if pas in by_game[g["game"]]:
                raise SystemExit(f"pass {pas} reads {g['game']} twice")
            by_game[g["game"]][pas] = dict(g, _reader=rid)
    return by_game


def load_items() -> list[dict]:
    s = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
    items = [{"id": k["id"], "game": k["game"], "kind": "knockout",
              "player": k["eliminated_player"], "reason_class": k["reason_class"]}
             for k in s["knockouts"]]
    items += [{"id": f"{g}:turning_point", "game": g, "kind": "turning_point"}
              for g in s["tp_games"]]
    assert len([i for i in items if i["kind"] == "knockout"]) == 40
    assert len([i for i in items if i["kind"] == "turning_point"]) == 20
    return items


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def consensus(values: list):
    """The value at least two readings share (compared as given), else the marker."""
    c = Counter(json.dumps(v, sort_keys=True) for v in values)
    top = [json.loads(k) for k, n in c.items() if n >= 2]
    return top[0] if len(top) == 1 else "no consensus"


def majority(flags: list[bool]) -> bool:
    return sum(flags) * 2 > len(flags)


def score_knockout(item, readings, ana_game, self_mode):
    player = item["player"]
    ko = next((k for k in (ana_game or {}).get("knockouts") or []
               if k.get("player") == player), None)
    per = []
    for pas in sorted(readings):
        g = readings[pas]
        es = [e for e in g.get("eliminations") or [] if e.get("player") == player]
        row = {"pass": pas, "reader": g["_reader"]}
        if len(es) != 1:
            row.update(missing=True, agree=False, card_agree=False)
            per.append(row)
            continue
        e = es[0]
        row.update(turn=e.get("turn"), cause=e.get("cause"), killer=e.get("killer"),
                   card=e.get("card"))
        problems = []
        try:
            t = as_turn(e.get("turn"))
        except Malformed as exc:
            t, _ = None, problems.append(str(exc))
        try:
            killer = reading_killer(e, player, self_mode)
        except Malformed as exc:
            killer, _ = None, problems.append(str(exc))
        if problems:
            row["malformed"] = problems
        if ko is None:
            agree = False
            fields = {}
        else:
            fields = {
                "turn": t is not None and t == ko.get("turn"),
                "cause": e.get("cause") == ko.get("cause"),
                "killer": ("killer" not in " ".join(problems))
                          and seats_equal(killer, ko.get("by")),
            }
            agree = all(fields.values())
        row["fields"] = fields
        row["agree"] = agree
        row["card_agree"] = ko is not None and norm_card(e.get("card")) == norm_card(ko.get("card"))
        per.append(row)
    human = {f: consensus([r.get(f) if f != "turn" else _turn_or_raw(r.get("turn"))
                           for r in per if not r.get("missing")])
             for f in ("turn", "cause", "killer", "card")}
    return {
        **item,
        "human": human,
        "analyzer": None if ko is None else {k: ko.get(k) for k in
                                              ("turn", "cause", "by", "card", "basis",
                                               "dated_by", "round")},
        "readings": per,
        "agree": majority([r["agree"] for r in per]),
        "card_agree": majority([r["card_agree"] for r in per]),
    }


def _turn_or_raw(v):
    try:
        return as_turn(v)
    except Malformed:
        return v


def score_tp(item, readings, ana_game):
    tp = (ana_game or {}).get("turning_point")
    per = []
    for pas in sorted(readings):
        g = readings[pas]
        r = g.get("turning_point")
        row = {"pass": pas, "reader": g["_reader"]}
        if not r:
            row.update(missing=True, agree=False)
            per.append(row)
            continue
        row.update(turn=r.get("turn"), card=r.get("card"))
        try:
            t = as_turn(r.get("turn"))
        except Malformed as exc:
            row.update(malformed=[str(exc)], agree=False)
            per.append(row)
            continue
        if tp is None:
            agree, how = False, "no analyzer turning point"
        else:
            d = abs(tp.get("turn") - t)
            same_card = norm_card(tp.get("event_hint") or tp.get("card")) == norm_card(r.get("card"))
            if d == 0:
                agree, how = True, "same turn"
            elif d == 1 and same_card:
                agree, how = True, "one turn apart, same card"
            else:
                agree, how = False, (f"{d} turns apart" + (", same card" if same_card else ""))
        row.update(agree=agree, how=how)
        per.append(row)
    human = {"turn": consensus([_turn_or_raw(r.get("turn")) for r in per if not r.get("missing")]),
             "card": consensus([r.get("card") for r in per if not r.get("missing")])}
    return {
        **item,
        "human": human,
        "analyzer": None if tp is None else {k: tp.get(k) for k in
                                              ("turn", "round", "seat", "event_hint",
                                               "event_by", "shift", "share_before",
                                               "share_after", "basis", "inferred")},
        "readings": per,
        "agree": majority([r["agree"] for r in per]),
    }


def score(analyzer: dict, self_mode: str = "literal") -> dict:
    items = load_items()
    readings = load_readings()
    games = analyzer["games"]
    scored = []
    for it in items:
        rd = {p: g for p, g in readings[it["game"]].items() if p in ("A", "B", "C")}
        if it["kind"] == "knockout":
            scored.append(score_knockout(it, rd, games.get(it["game"]), self_mode))
        else:
            scored.append(score_tp(it, rd, games.get(it["game"])))
    for s in scored:
        s["run"] = s["game"].split("-")[0]
        s["path"] = PATH_OF_RUN[s["run"]]
        s["pass_c"] = "C" in readings[s["game"]]
    ko = [s for s in scored if s["kind"] == "knockout"]
    tp = [s for s in scored if s["kind"] == "turning_point"]

    def tally(rows, key="agree"):
        return {"agree": sum(1 for r in rows if r[key]), "of": len(rows)}

    summary = {
        "self_mode": self_mode,
        "knockouts": tally(ko),
        "knockout_pass": sum(1 for r in ko if r["agree"]) >= KO_THRESHOLD,
        "knockout_card": tally(ko, "card_agree"),
        "turning_points": tally(tp),
        "turning_point_pass": sum(1 for r in tp if r["agree"]) >= TP_THRESHOLD,
        "knockouts_by_run": {r: tally([s for s in ko if s["run"] == r]) for r in "RST"},
        "knockouts_by_path": {p: tally([s for s in ko if s["path"] == p])
                              for p in ("shim", "stdout")},
        "knockout_card_by_path": {p: tally([s for s in ko if s["path"] == p], "card_agree")
                                  for p in ("shim", "stdout")},
        "turning_points_by_run": {r: tally([s for s in tp if s["run"] == r]) for r in "RST"},
        "turning_points_by_path": {p: tally([s for s in tp if s["path"] == p])
                                   for p in ("shim", "stdout")},
        "knockouts_by_game": {g: tally([s for s in ko if s["game"] == g])
                              for g in sorted({s["game"] for s in ko})},
        "no_consensus": [s["id"] + ":" + f for s in scored for f, v in s["human"].items()
                         if v == "no consensus"],
        "pass_c_games": sorted({s["game"] for s in scored if s["pass_c"]}),
    }
    return {"summary": summary, "items": scored}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if not args:
        print(__doc__)
        return 1
    analyzer = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    mode = opts.get("self-mode", "literal")
    out = score(analyzer, mode)
    out["analyzer_blob"] = analyzer.get("blob")
    out["analyzer_context_blob"] = analyzer.get("context_blob")
    s = out["summary"]
    print(f"self-mode {mode}")
    print(f"knockouts: {s['knockouts']['agree']}/40 (pass needs {KO_THRESHOLD}) "
          f"-> {'PASS' if s['knockout_pass'] else 'FAIL'}")
    print(f"  by run {s['knockouts_by_run']}  by path {s['knockouts_by_path']}")
    print(f"  card: {s['knockout_card']['agree']}/40  by path {s['knockout_card_by_path']}")
    print(f"turning points: {s['turning_points']['agree']}/20 (pass needs {TP_THRESHOLD}) "
          f"-> {'PASS' if s['turning_point_pass'] else 'FAIL'}")
    print(f"  by run {s['turning_points_by_run']}  by path {s['turning_points_by_path']}")
    print(f"no consensus: {s['no_consensus']}")
    for it in out["items"]:
        if not it["agree"] or (it["kind"] == "knockout" and not it["card_agree"]):
            print(f"  {'DISAGREE' if not it['agree'] else 'card only'}: {it['id']}"
                  f"  human={it['human']}  analyzer={it['analyzer']}")
    if "out" in opts:
        Path(opts["out"]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
        print(f"wrote {opts['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
