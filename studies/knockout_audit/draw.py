#!/usr/bin/env python3
"""The knockout and turning-point audit draw (studies/knockout_audit/PREREG.md).

Committed with the pre-registration, before the draw is run. It reads ONLY
Forge's own records in each result file: the players list, result.winner,
result.draw, result.timedOut and the "has lost" / "has won" lines of Forge's
end-of-game outcome block. It imports no analyzer (engine/qa, analysis.py)
and calls no API.

Usage:
    py studies/knockout_audit/draw.py <runs_dir> [--out sample.json]

<runs_dir> holds the three audited files named in PREREG.md; their md5s are
checked first and the draw refuses to run on anything else.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

SEED = 20261012

# label -> (file name, md5 of the audited copy). Order matters: it is the
# tie-break order of every allocation below.
RUNS = (
    ("R", "sim_20260925_003803_d0eb966b8d33_rotated.json", "396ef82b5d818f67298682af924df3a2"),
    ("S", "sim_20260801_193328.json", "df282cd5cb44527001e9f229c447d6bd"),
    ("T", "sim_20260723_101044.json", "340c7b65b953ff3f7497be7bf275345c"),
)
# Runs whose decided games all become turning-point games; the last run
# supplies the rest of the 20.
CENSUS_RUNS = ("R", "S")
SAMPLED_RUN = "T"
N_TP = 20
N_KO = 40
MAX_NONLIFE = 20

_LOST = re.compile(r"^(?P<p>.+?) has lost (?P<why>.*)$")
_WON = re.compile(r"^(?P<p>.+?) has won\b")


def reason_class(why: str) -> str:
    """Forge's loss reason, coarsely. Used for stratification only."""
    w = why.lower()
    if "life total reached 0" in w:
        return "life"
    if "poison" in w:
        return "poison"
    if "damage from generals" in w or "commander" in w:
        return "commander"
    if "won by spell" in w:
        return "spell"
    if "empty library" in w:
        return "deckout"
    if "conced" in w:
        return "concession"
    return "other"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def outcome_lines(game: dict) -> list[str]:
    return [e.get("raw", "") for t in game.get("turns", []) for e in t.get("events", [])
            if e.get("action") == "game_outcome"]


def game_records(label: str, data: dict) -> list[dict]:
    out = []
    for n, g in enumerate(data.get("games", []), 1):
        lines = outcome_lines(g)
        lost = []
        won = []
        for raw in lines:
            m = _LOST.match(raw)
            if m:
                lost.append({"player": m.group("p"), "forge_line": raw,
                             "reason_class": reason_class(m.group("why"))})
                continue
            m = _WON.match(raw)
            if m:
                won.append(m.group("p"))
        res = g.get("result") or {}
        players = list(g.get("players") or [])
        losers = {k["player"] for k in lost}
        decided = (bool(res.get("winner")) and not res.get("draw")
                   and not res.get("timedOut") and len(won) == 1
                   and won[0] == res.get("winner")
                   and losers == set(players) - {won[0]})
        key = f"{label}-g{n:02d}"
        out.append({"key": key, "run": label, "n": n, "players": players,
                    "winner": res.get("winner"), "decided": decided,
                    "won_lines": won,
                    "knockouts": [dict(k, id=f"{key}:{k['player']}") for k in lost]})
    return out


def largest_remainder(total: int, weights: list[int]) -> list[int]:
    s = sum(weights)
    if s == 0:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    base = [math.floor(x) for x in raw]
    left = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:left]:
        base[i] += 1
    return base


def draw(runs_dir: Path) -> dict:
    rng = random.Random(SEED)
    games: dict[str, list[dict]] = {}
    files = {}
    for label, name, want in RUNS:
        p = runs_dir / name
        got = md5(p)
        if got != want:
            sys.exit(f"{name}: md5 {got} is not the pre-registered {want}")
        files[label] = {"file": name, "md5": got}
        games[label] = game_records(label, json.loads(p.read_text(encoding="utf-8")))

    # 1. Turning-point games: every decided game of the census runs, the rest
    #    from the sampled run, split between its games with a non-life loss
    #    ("mixed") and its all-life games, mixed first and rounded up.
    tp = [g["key"] for lab in CENSUS_RUNS for g in games[lab] if g["decided"]]
    need = N_TP - len(tp)
    t_dec = [g for g in games[SAMPLED_RUN] if g["decided"]]
    t_mixed = sorted(g["key"] for g in t_dec
                     if any(k["reason_class"] != "life" for k in g["knockouts"]))
    t_life = sorted(g["key"] for g in t_dec
                    if all(k["reason_class"] == "life" for k in g["knockouts"]))
    k_mixed = min(len(t_mixed), math.ceil(need / 2))
    k_life = need - k_mixed
    if k_life > len(t_life):
        sys.exit("not enough decided games in the sampled run")
    tp += sorted(rng.sample(t_mixed, k_mixed)) + sorted(rng.sample(t_life, k_life))

    # 2. Reading set: the turning-point games plus every undecided game (any
    #    run) that has at least one knockout.
    by_key = {g["key"]: g for lab in games for g in games[lab]}
    extra = [g["key"] for lab, _, _ in RUNS for g in games[lab]
             if not g["decided"] and g["knockouts"]]
    reading = sorted(set(tp) | set(extra))

    # 3. Knockout frame: every knockout in the reading set.
    frame = [k for key in reading for k in by_key[key]["knockouts"]]
    if len(frame) < N_KO:
        sys.exit(f"frame has {len(frame)} knockouts, fewer than {N_KO}")

    # 4a. Every non-life knockout (census), capped at MAX_NONLIFE.
    nonlife = [k for k in frame if k["reason_class"] != "life"]
    if len(nonlife) > MAX_NONLIFE:
        classes = sorted({k["reason_class"] for k in nonlife})
        alloc = largest_remainder(MAX_NONLIFE, [sum(1 for k in nonlife if k["reason_class"] == c)
                                                for c in classes])
        keep = []
        for c, n in zip(classes, alloc):
            ids = sorted(k["id"] for k in nonlife if k["reason_class"] == c)
            keep += rng.sample(ids, n)
        chosen = set(keep)
    else:
        chosen = {k["id"] for k in nonlife}

    # 4b. Life knockouts fill the rest, allocated to runs in proportion to
    #     their life knockouts in the frame, drawn at random within each run.
    life_by_run = {lab: sorted(k["id"] for k in frame
                               if k["reason_class"] == "life" and k["id"].startswith(lab + "-"))
                   for lab, _, _ in RUNS}
    labels = [lab for lab, _, _ in RUNS]
    alloc = largest_remainder(N_KO - len(chosen), [len(life_by_run[lab]) for lab in labels])
    for lab, n in zip(labels, alloc):
        chosen |= set(rng.sample(life_by_run[lab], n))

    frame_by_id = {k["id"]: k for k in frame}
    ko_items = [frame_by_id[i] for i in sorted(chosen)]
    return {
        "seed": SEED,
        "files": files,
        "tp_games": sorted(tp),
        "reading_set": reading,
        "games": {key: {"run": by_key[key]["run"], "n": by_key[key]["n"],
                        "players": by_key[key]["players"],
                        "decided": by_key[key]["decided"],
                        "turning_point_requested": key in tp,
                        "knockouts_in_game": len(by_key[key]["knockouts"])}
                  for key in reading},
        "frame_size": len(frame),
        "knockouts": [{"id": k["id"], "game": k["id"].split(":", 1)[0],
                       "eliminated_player": k["player"],
                       "forge_line": k["forge_line"],
                       "reason_class": k["reason_class"]} for k in ko_items],
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_dir")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    out = draw(Path(a.runs_dir))
    text = json.dumps(out, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
