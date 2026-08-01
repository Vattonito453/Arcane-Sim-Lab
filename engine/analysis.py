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
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board  # noqa: E402
import cards  # noqa: E402
import combos  # noqa: E402

# Bump when the payload shape or the maths change: the API caches reports on
# disk beside the results, and a stale cache would silently serve the old shape.
ANALYSIS_VERSION = 3

_AI = re.compile(r"^Ai\(\d+\)-")
# "X has kept a hand of 7 cards" / "X has mulliganed down to 6 cards" — take the
# last line per player, so a mulligan followed by a keep lands on the keep.
_KEPT = re.compile(r"^(.+?) has (?:kept a hand of|mulliganed down to) (\d+) cards?")
_WORDNUM = {"a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
# Forge phrases losses both ways: "has lost because life total reached 0" and
# "has lost due to accumulation of 21 damage from generals". Match both, or
# every commander-damage kill classifies as unknown.
_LOST = re.compile(r"(.+?) has lost (?:because|due to)\s*(?:of\s+)?(.+?)\.?\s*$")
_SPELL = re.compile(r"won by spell '([^']+)'")
# Actual casts only — board._CAST also matches "triggered"/"activated", which
# would count ability text as a spell piece being cast.
_CAST_LINE = re.compile(r"^(.+?)\s+cast\s+(.+?)(?:\s+targeting|\.|$)", re.I)

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
    return cards.normalize_name(name.split(" // ")[0]).lower()


def _cast_turns(game: dict) -> dict[tuple[str, str], set[int]]:
    """(player key, normalized card name) -> turns the player cast it.

    Non-permanent combo pieces (a sorcery like Rite of Replication) never sit
    on the battlefield, so battlefield membership can't detect them — their
    assembly criterion is "cast on a turn the permanent pieces were online".
    """
    out: dict[tuple[str, str], set[int]] = {}
    for t in game.get("turns") or []:
        turn = t.get("turn", 0)
        for e in t.get("events") or []:
            if e.get("action") != "stack_add":
                continue
            m = _CAST_LINE.match(e.get("raw", ""))
            if not m:
                continue
            norm = cards.normalize_name(m.group(2)).lower()
            out.setdefault((m.group(1).strip(), norm), set()).add(turn)
    return out


def _count_effect_draws(raw: str, player: str) -> int:
    """Cards `player` drew in this resolution line. Forge narrates resolved
    effect draws in the third person — "Ai(1)-X draws two cards." — while
    ability TEXT uses the imperative ("draw a card"), so matching the player's
    own name followed by "draws" counts resolutions and skips rules text."""
    total = 0
    for m in re.finditer(re.escape(player) + r" draws (\w+) (?:additional )?cards?",
                         raw):
        w = m.group(1).lower()
        total += _WORDNUM.get(w, int(w) if w.isdigit() else 0)
    return total


def draw_model(game: dict) -> dict[str, int]:
    """Cards each player has SEEN from their library by game end: kept opening
    hand + one per draw step + logged effect draws.

    A model, not a count Forge reports: natural draw-step draws are never
    logged, so they are inferred one per turn the player took (heads-up games
    skip the starting player's first, per rule 103.8a; multiplayer skips
    nobody). Effect draws are parsed from resolution lines. What was drawn is
    hidden information and stays that way — this is how MANY, which is all the
    hypergeometric needs.
    """
    players = list(game.get("players") or [])
    kept = {p: 7 for p in players}
    for e in game.get("events_pregame") or []:
        m = _KEPT.match(e.get("raw", ""))
        if m and m.group(1) in kept:
            kept[m.group(1)] = int(m.group(2))

    steps = {p: 0 for p in players}
    effect = {p: 0 for p in players}
    first_active = None
    for t in game.get("turns") or []:
        ap = t.get("active_player")
        if first_active is None and ap:
            first_active = ap
        if ap in steps:
            steps[ap] += 1
        for e in t.get("events") or []:
            raw = e.get("raw", "")
            if " draws " not in raw:
                continue
            for p in players:
                effect[p] += _count_effect_draws(raw, p)
    if len(players) == 2 and first_active in steps and steps[first_active] > 0:
        steps[first_active] -= 1
    return {p: {"seen": kept[p] + steps[p] + effect[p], "turns": steps[p]}
            for p in players}


def p_all_drawn(seen: int, lib_pieces: int, deck_size: int = 99) -> float:
    """Hypergeometric: chance every one of `lib_pieces` singletons is among the
    `seen` cards taken from a `deck_size` library. Commanders are excluded by
    the caller — the command zone makes them always available."""
    if lib_pieces == 0:
        return 1.0
    if seen < lib_pieces or deck_size < seen:
        return 0.0
    return comb(deck_size - lib_pieces, seen - lib_pieces) / comb(deck_size, seen)


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
        main, commanders = combos.parse_dck(p.read_text(encoding="utf-8"))
        per_deck[name] = {
            "deck_file": Path(f).name,
            "deck_size": sum(q for _, q in main) or 99,
            "commanders": commanders,
            # None = not analysed (Spellbook unreachable, cold cache) — distinct
            # from "no combos", which is an empty list.
            "combo_status": "ok" if found is not None else "unknown",
            "combos": [dict(c, games=[]) for c in (found or {}).get("included", [])],
            "almost_included": len((found or {}).get("almost_included", [])),
        }

    # One batched lookup warms the type cache for every combo piece (Scryfall
    # etiquette: never loop single fetches). is_permanent() below then runs
    # cache-only.
    piece_names = sorted({c for d in per_deck.values()
                          for combo in d["combos"] for c in combo["cards"]})
    if piece_names:
        cards.get_many(piece_names, fetch=fetch)

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

        # Draw model covers every seated deck, combos or not — draw velocity is
        # deck health information in its own right.
        players = game.get("players") or []
        seen = draw_model(game)
        for key in players:
            d = per_deck.get(_bare(key))
            if d is not None:
                dm = seen.get(key) or {"seen": 7, "turns": 0}
                d.setdefault("_draw_games", []).append((dm["seen"], dm["turns"]))

        # Assembly: fold the log into per-turn battlefields once per game, then
        # test each known combo of each seated deck against its owner's board.
        seated = {name: key for key in players
                  if (name := _bare(key)) in per_deck and per_deck[name]["combos"]}
        if not seated:
            continue
        _, snapshots = board.reconstruct(game, fetch=False)
        casts = _cast_turns(game)

        for name, key in seated.items():
            cmdrs = {_norm(c) for c in per_deck[name].get("commanders", [])}
            deck_size = per_deck[name].get("deck_size", 99)
            for combo in per_deck[name]["combos"]:
                pieces = {c: _norm(c) for c in combo["cards"]}
                # A sorcery/instant piece never sits on the battlefield: its
                # criterion is "cast this turn", the permanents' is "on board".
                spell = {c: n for c, n in pieces.items()
                         if cards.is_permanent(c) is False}
                perm = {c: n for c, n in pieces.items() if c not in spell}
                first_seen: dict[str, int | None] = {
                    c: (min(casts[(key, n)]) if (key, n) in casts else None)
                    for c, n in spell.items()}
                first_seen.update({c: None for c in perm})
                assembled_turn: int | None = None
                online_turns = 0
                for snap in snapshots:
                    on_board = {c["name"].lower() for c in (snap["board"].get(key) or [])}
                    turn = snap["turn"]
                    for c, norm in perm.items():
                        if first_seen[c] is None and norm in on_board:
                            first_seen[c] = turn
                    if (all(n in on_board for n in perm.values())
                            and all(turn in casts.get((key, n), ())
                                    for n in spell.values())):
                        online_turns += 1
                        if assembled_turn is None:
                            assembled_turn = turn
                # Draw odds: how likely the deck had DRAWN every library piece
                # by game end. Commander pieces are always available, so they
                # drop out of the hypergeometric.
                lib_pieces = sum(1 for norm in pieces.values() if norm not in cmdrs)
                combo["games"].append({
                    "n": n,
                    "pieces": first_seen,
                    "assembled_turn": assembled_turn,
                    "online_turns": online_turns,
                    "won": bool(winner) and _bare(winner) == name,
                    "cards_seen": (seen.get(key) or {}).get("seen", 7),
                    "p_all_drawn": round(p_all_drawn(
                        (seen.get(key) or {}).get("seen", 7), lib_pieces, deck_size), 3),
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
            # What raw draws alone predicted. Actual below this means pieces sat
            # in hand or died; actual above it means tutors did work.
            combo["expected_drawn_games"] = round(
                sum(g["p_all_drawn"] for g in plays), 1)
            combo["nonpermanent_pieces"] = [
                c for c in combo["cards"] if cards.is_permanent(c) is False]
            # The verdict the UI shows. "sample_too_small" is the honesty fix:
            # when raw draw odds predicted ~0 assemblies across the whole run,
            # a zero is the expected outcome, not a finding about the deck.
            if combo["converted_games"] > 0:
                combo["reading"] = "fired"
            elif combo["assembled_games"] > 0:
                combo["reading"] = "assembled_not_fired"
            elif combo["expected_drawn_games"] < 0.5:
                combo["reading"] = "sample_too_small"
            else:
                combo["reading"] = "not_assembled"

    for d in per_deck.values():
        dg = d.pop("_draw_games", [])
        if dg:
            # Per OWN turn taken, not per global player-turn: a player draws on
            # their turns, so this reads "cards seen per turn cycle" — 1.0 is
            # topdecking, higher means the draw engine is doing something.
            d["draws"] = {
                "games": len(dg),
                "avg_cards_seen": round(statistics.mean(s for s, _ in dg), 1),
                "per_own_turn": round(statistics.mean(
                    s / t for s, t in dg if t > 0), 2) if any(t for _, t in dg) else None,
            }

    methods: dict[str, int] = {}
    for g in games_out:
        methods[g["method"]] = methods.get(g["method"], 0) + 1

    return {
        "version": ANALYSIS_VERSION,
        "file": result.get("file"),
        "games": games_out,
        "decks": per_deck,
        "summary": {"games": total, "methods": methods},
        "note": ("Assembly is inferred from board reconstruction (Forge never "
                 "logs battlefield entries; 83-86% exit-match). Instant/sorcery "
                 "pieces count as present on turns they were cast. 'Converted' "
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
            if d.get("draws"):
                print(f"  {name}: sees ~{d['draws']['avg_cards_seen']} cards/game"
                      f" ({d['draws']['per_own_turn']}/turn cycle)")
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
                      + f" | draw odds predicted ~{c['expected_drawn_games']}"
                      + f" | converted {c['converted_games']}"
                      + f" | reading: {c['reading']}"
                      + (f" | sat online {c['idle_online_turns']} turns without winning"
                         if c["idle_online_turns"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
