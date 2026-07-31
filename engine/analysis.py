#!/usr/bin/env python3
"""Win-condition analysis for a sim result: what each deck is trying to do, how
often the pieces actually assembled, and whether the AI ever converted them.

Why: Forge's AI cannot pilot most multi-card combos, so a combo deck's win rate
is a floor, not a verdict (engine/SIM_CALIBRATION.md). The number that separates
"bad deck" from "bad pilot" is the gap between ASSEMBLED (all pieces of a known
combo on the battlefield at once) and CONVERTED (that seat then won). A deck
that assembles turn 7 in 60% of games and converts none is healthy with an
incapable pilot; a deck that never assembles has a deck problem — and that
second verdict is trustworthy even from a weak pilot.

Method honesty: battlefield membership comes from board.py reconstruction,
which is inference over a log that never records cards entering the battlefield
(83-86% exit-match, see CLAUDE.md). Assembly rates inherit that ceiling and the
API payload says so. "Converted" means won after assembling — correlation, not
proven causation.

Combo knowledge comes from combos.py (Commander Spellbook, cached on disk).

CLI:
    python3 engine/analysis.py engine/sim_results/<result>.json [--no-fetch]
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board  # noqa: E402
import combos  # noqa: E402

_AI = re.compile(r"^Ai\(\d+\)-")
# Forge phrases losses both ways: "has lost because life total reached 0" and
# "has lost due to accumulation of 21 damage from generals". Match both, or
# every commander-damage kill classifies as unknown.
_LOST = re.compile(r"(.+?) has lost (?:because|due to)\s*(?:of\s+)?(.+?)\.?\s*$")
_SPELL = re.compile(r"won by spell '([^']+)'")

# Loss-reason text -> method label. Matched as substrings of Forge's reason.
_METHODS = [
    ("won by spell", "spell"),
    ("poison counter", "poison"),
    ("damage from general", "commander damage"),
    ("commander damage", "commander damage"),
    ("empty library", "deckout"),
    ("tried to draw", "deckout"),
    ("life total reached", "combat damage / life loss"),
]


def _bare(player: str) -> str:
    return _AI.sub("", player)


def _norm(name: str) -> str:
    """Combo card name -> the form board.py stores: front face, normalized."""
    import cards
    return cards.normalize_name(name.split(" // ")[0]).lower()


def win_method(game: dict) -> dict:
    """How this game actually ended, from the game_outcome record."""
    result = game.get("result") or {}
    if result.get("draw"):
        return {"method": "draw", "detail": "clock or stalemate"}

    losses: list[tuple[str, str]] = []
    for t in game.get("turns") or []:
        for e in t.get("events") or []:
            if e.get("action") != "game_outcome":
                continue
            m = _LOST.match(e.get("raw", ""))
            if m:
                losses.append((m.group(1), m.group(2)))

    # A spell win names the winner's method outright, whoever's loss line
    # carried it. Otherwise the loss that ended the game is the last one.
    for _who, reason in losses:
        sm = _SPELL.search(reason)
        if sm:
            return {"method": "spell", "detail": sm.group(1)}
    if losses:
        reason = losses[-1][1]
        for needle, label in _METHODS:
            if needle in reason:
                return {"method": label, "detail": reason}
        return {"method": "other", "detail": reason}
    # Some runs (mostly older 2-player logs) record only the winner's line, so
    # there is nothing to classify from. Say that, rather than guessing.
    return {"method": "not recorded", "detail": ""}


def deck_name_of(dck_path: Path) -> str:
    """The Name= Forge shows in logs, from the .dck metadata block."""
    try:
        for line in dck_path.read_text(encoding="utf-8").splitlines():
            if line.strip().lower().startswith("name="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return dck_path.stem.replace("_", " ").title()


def _find_deck_file(filename: str, deck_dirs: list[Path]) -> Path | None:
    for d in deck_dirs:
        p = d / Path(filename).name
        if p.is_file():
            return p
    return None


def analyse(result: dict, deck_dirs: list[Path] | None = None,
            fetch: bool = True) -> dict:
    """Full wincon report for one adapted result file."""
    if deck_dirs is None:
        base = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent)))
        deck_dirs = [base / "decks", Path(__file__).parent / "decks"]

    # Deck name -> known combos, via the .dck files this run was played with.
    deck_files = (result.get("meta") or {}).get("decks") or []
    per_deck: dict[str, dict] = {}
    for f in deck_files:
        p = _find_deck_file(f, deck_dirs)
        if p is None:
            continue
        name = deck_name_of(p)
        found = combos.combos_for_dck(p, fetch=fetch)
        per_deck[name] = {
            "deck_file": Path(f).name,
            # None = not analysed (Spellbook unreachable, cold cache) — distinct
            # from "no combos", which is an empty list.
            "combo_status": "ok" if found is not None else "unknown",
            "combos": [dict(c, games=[]) for c in (found or {}).get("included", [])],
            "almost_included": len((found or {}).get("almost_included", [])),
        }

    games_out: list[dict] = []
    for game in result.get("games") or []:
        n = len(games_out) + 1
        method = win_method(game)
        winner = (game.get("result") or {}).get("winner")
        turns = game.get("turns") or []
        end_turn = turns[-1].get("turn", 0) if turns else 0
        games_out.append({
            "n": n,
            "winner": _bare(winner) if winner else None,
            "ended_turn": end_turn,
            **method,
        })

        # Assembly: fold the log into per-turn battlefields once per game, then
        # test each known combo of each seated deck against its owner's board.
        players = game.get("players") or []
        seated = {name: key for key in players
                  if (name := _bare(key)) in per_deck and per_deck[name]["combos"]}
        if not seated:
            continue
        _, snapshots = board.reconstruct(game, fetch=False)

        for name, key in seated.items():
            for combo in per_deck[name]["combos"]:
                pieces = {c: _norm(c) for c in combo["cards"]}
                first_seen: dict[str, int | None] = {c: None for c in pieces}
                assembled_turn: int | None = None
                online_turns = 0
                for snap in snapshots:
                    on_board = {c["name"].lower() for c in (snap["board"].get(key) or [])}
                    for c, norm in pieces.items():
                        if first_seen[c] is None and norm in on_board:
                            first_seen[c] = snap["turn"]
                    if all(norm in on_board for norm in pieces.values()):
                        online_turns += 1
                        if assembled_turn is None:
                            assembled_turn = snap["turn"]
                combo["games"].append({
                    "n": n,
                    "pieces": first_seen,
                    "assembled_turn": assembled_turn,
                    "online_turns": online_turns,
                    "won": bool(winner) and _bare(winner) == name,
                })

    # Aggregates.
    total = len(games_out)
    for name, d in per_deck.items():
        for combo in d["combos"]:
            plays = [g for g in combo["games"]]
            assembled = [g for g in plays if g["assembled_turn"] is not None]
            combo["games_played"] = len(plays)
            combo["assembled_games"] = len(assembled)
            combo["converted_games"] = sum(1 for g in assembled if g["won"])
            combo["median_assembled_turn"] = (
                statistics.median(g["assembled_turn"] for g in assembled)
                if assembled else None)
            # Turns spent fully online without winning — the AI-pilot gap on record.
            combo["idle_online_turns"] = sum(
                g["online_turns"] for g in assembled if not g["won"])

    methods: dict[str, int] = {}
    for g in games_out:
        methods[g["method"]] = methods.get(g["method"], 0) + 1

    return {
        "file": result.get("file"),
        "games": games_out,
        "decks": per_deck,
        "summary": {"games": total, "methods": methods},
        "note": ("Assembly is inferred from board reconstruction (Forge never "
                 "logs battlefield entries; 83-86% exit-match). 'Converted' "
                 "means won after assembling, not proven causation."),
    }


def main() -> int:
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    fetch = "--no-fetch" not in sys.argv
    if not paths:
        print(__doc__)
        return 1
    for p in paths:
        result = json.loads(Path(p).read_text(encoding="utf-8"))
        result.setdefault("file", Path(p).name)
        rep = analyse(result, fetch=fetch)
        print(f"\n{rep['file']}: {rep['summary']['games']} games")
        print("  won by:", ", ".join(f"{k} x{v}" for k, v in
                                     sorted(rep["summary"]["methods"].items(),
                                            key=lambda kv: -kv[1])))
        for name, d in rep["decks"].items():
            if d["combo_status"] != "ok":
                print(f"  {name}: combos unknown (Spellbook not reachable)")
                continue
            if not d["combos"]:
                print(f"  {name}: no known combos in the 99 "
                      f"({d['almost_included']} one card away)")
                continue
            for c in d["combos"]:
                med = c["median_assembled_turn"]
                print(f"  {name}: {' + '.join(c['cards'])}")
                print(f"    assembled {c['assembled_games']}/{c['games_played']} games"
                      + (f" (median turn {med:.0f})" if med is not None else "")
                      + f", converted {c['converted_games']}"
                      + (f", sat online {c['idle_online_turns']} turns without winning"
                         if c["idle_online_turns"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
