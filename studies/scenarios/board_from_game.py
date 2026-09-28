#!/usr/bin/env python3
"""A scenario board from a real shim game: every seat's zones as they stood
just before the active seat's first combat of a given turn.

    py studies/scenarios/board_from_game.py GAME.jsonl --game 10 --turn 27 \\
        --id c1_rot0_g10 --out c1/c1_rot0_g10.json [--deck-dir DIR]

This is how the suite grows from real games (WS3 task 5) and how C1 reproduces
the Helm-attached boards of real stock games. It reads only the shim's
real-time records (zone, tap, counters, attach), which are exact on the shim
path, plus life totals from Forge's log entries (walked to the same point by
the TURN and PHASE entries). The snapshot point is the last record of the
turn's precombat main phase.

What it carries: battlefield (cards, tapped, P1P1/M1M1/charge/loyalty
counters, equipment and aura attachments, summoning sickness for what the
active seat took control of this turn), hand, graveyard, exile, life, lands
played this turn, and each seat's deck (the game's own seat order).
What it cannot carry, and says so in the scenario's notes: tokens with no
known Forge token script, poison and other player counters (not in the shim's
records), the library order (the rest of the deck is shuffled per trial),
commander tax and damage, this-turn effects, and the discarded mana pool.
The decks are today's files: a card the game held that today's deck does not
is written anyway and the writer warns.

Stdlib only; no card knowledge beyond the token-name table below.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PRE_COMBAT = ("", "UNTAP", "UPKEEP", "DRAW", "MAIN1")
# Forge counter display names (GameEventCardCounters type.getName) -> the
# CounterEnumType names GameState reads.
COUNTERS = {"+1/+1": "P1P1", "-1/-1": "M1M1", "Charge": "CHARGE", "Loyalty": "LOYALTY",
            "Lore": "LORE", "Oil": "OIL", "Time": "TIME", "Stun": "STUN", "Shield": "SHIELD",
            "Defense": "DEFENSE", "Age": "AGE", "Depletion": "DEPLETION", "Wish": "WISH",
            "Luck": "LUCK", "Film": "FILM"}
# Token (name Forge logs, P/T as it moved or None for any) -> the
# res/tokenscripts script that makes the same token. The creature entries are
# identified by name and P/T only, from the cards that make them in the cEDH
# study decks (Swan Song's 2/2 flying Bird, Pongify's 3/3 Ape, Urza's Saga's
# Construct, amass's Orc Army); a colour or keyword could differ. Anything
# else is dropped from the board and named in the scenario's notes.
TOKENS = {("Treasure Token", None): "c_a_treasure_sac", ("Clue Token", None): "c_a_clue_draw",
          ("Food Token", None): "c_a_food_sac", ("Blood Token", None): "c_a_blood_draw",
          ("Gold Token", None): "c_a_gold_draw", ("Zombie Token", "2/2"): "b_2_2_zombie",
          ("Insect Token", "1/1"): "g_1_1_insect", ("Bird Token", "2/2"): "u_2_2_bird_flying",
          ("Ape Token", "3/3"): "g_3_3_ape", ("Construct Token", None): "c_0_0_a_construct_total_artifacts",
          ("Orc Army Token", None): "b_0_0_orc_army"}


def token_script(name: str, pt: str) -> str | None:
    return TOKENS.get((name, pt)) or TOKENS.get((name, None))
LIFE = re.compile(r"^Life: (.+?) (-?\d+) > (-?\d+)$")
TURN = re.compile(r"^Turn (\d+) \((.*)\)$")


def load_game(path: Path, game: int) -> tuple[dict, list[dict]]:
    meta, recs = {}, []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("rec") == "meta":
            meta = r
        elif r.get("game") == game:
            recs.append(r)
    return meta, recs


def life_at(recs: list[dict], players: list[str], turn: int) -> dict[str, int]:
    """Life totals from Forge's log entries, walked to the first step after
    turn `turn`'s precombat main phase."""
    life = {p: 40 for p in players}
    in_turn = False
    for r in recs:
        if r.get("rec") != "entry":
            continue
        msg = r.get("message", "")
        if r.get("type") == "TURN":
            m = TURN.match(msg)
            if m:
                if in_turn:
                    break
                in_turn = int(m.group(1)) == turn
            continue
        if in_turn and r.get("type") == "PHASE" and not any(
                s in msg for s in ("Untap step", "Upkeep step", "Draw step", "Main phase, precombat")):
            break
        m = LIFE.match(msg)
        if m and m.group(1) in life:
            life[m.group(1)] = int(m.group(3))
    return life


def snapshot(recs: list[dict], turn: int) -> dict:
    """Card state from the real-time records up to the snapshot point."""
    cards: dict[int, dict] = {}
    tapped: dict[int, bool] = {}
    counters: dict[int, dict] = defaultdict(dict)
    attach: dict[int, str | None] = {}
    lands_played = defaultdict(int)
    names: dict[int, str] = {}
    for r in recs:
        kind = r.get("rec")
        if kind not in ("zone", "tap", "counters", "attach"):
            continue
        t = int(r.get("turn", 0))
        if t > turn or (t == turn and r.get("phase", "") not in PRE_COMBAT):
            break
        cid = r.get("cardId")
        if kind == "zone":
            owner = r.get("toPlayer") or r.get("fromPlayer")
            # A card keeps the name it was first seen under (its printed name):
            # a clone that entered as a copy of Rograkh is logged as Rograkh
            # but is a Phyrexian Metamorph, and the state must place the
            # Metamorph (Forge then asks its controller what to copy).
            printed = names.setdefault(cid, r.get("card"))
            cards[cid] = {"card": printed, "zone": r.get("to"), "player": owner,
                          "token": bool(r.get("token")), "types": r.get("types", ""),
                          "pt": r.get("pt", ""), "logged_as": r.get("card"),
                          "entered": t if r.get("to") == "Battlefield" else None}
            tapped.pop(cid, None)
            counters.pop(cid, None)
            attach.pop(cid, None)
            if t == turn and r.get("from") == "Hand" and r.get("to") == "Battlefield" \
                    and "Land" in r.get("types", ""):
                lands_played[owner] += 1
        elif kind == "tap":
            tapped[cid] = bool(r.get("tapped"))
        elif kind == "counters":
            counters[cid][r.get("type")] = int(r.get("n", 0))
        elif kind == "attach":
            attach[cid] = r.get("to")
    return {"cards": cards, "tapped": tapped, "counters": counters, "attach": attach,
            "lands_played": dict(lands_played)}


def back_faces(index: Path | None) -> dict[str, str]:
    """Back-face name -> front-face name, from the Forge index's cards.json
    (engine/forge_index.py; $MTG_DATA_DIR/forge_index/<version>/cards.json)."""
    if not index:
        return {}
    cards = json.loads(Path(index).read_text(encoding="utf-8")).get("cards", {})
    return {face: front for front, c in cards.items() for face in (c.get("faces") or [])[1:]}


def build(path: Path, game: int, turn: int, sid: str, deck_dir: Path | None,
          index: Path | None = None) -> dict:
    meta, recs = load_game(path, game)
    backs = back_faces(index)
    players = meta.get("players", [])
    if not players:
        sys.exit(f"{path}: no meta players")
    decks = [Path(d) for d in meta.get("decks", [])]
    if deck_dir:
        decks = [deck_dir / (p.split("-", 1)[1] + ".dck") for p in players]
    owners = {}
    for r in recs:
        if r.get("rec") == "entry" and r.get("type") == "TURN":
            m = TURN.match(r.get("message", ""))
            if m:
                owners[int(m.group(1))] = m.group(2)
    active = owners.get(turn)
    if active not in players:
        sys.exit(f"turn {turn} has no owner among {players}")
    snap = snapshot(recs, turn)
    life = life_at(recs, players, turn)
    notes = [f"Board from {path.name} game {game}, turn {turn} ({active}), as it stood at the end of the "
             f"precombat main phase: shim zone, tap, counter and attach records; life from Forge's log."]
    dropped, copies = [], []
    seats = []
    labels: dict[int, str] = {}
    bf_by_player: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for cid, c in sorted(snap["cards"].items()):
        if c["zone"] == "Battlefield":
            bf_by_player[c["player"]].append((cid, c))
    # Attachment hosts get labels first so every attached card can name one.
    hosts = {}
    for cid, to in snap["attach"].items():
        c = snap["cards"].get(cid)
        if not to or not c or c["zone"] != "Battlefield":
            continue
        cands = [(hid, h) for p in players for hid, h in bf_by_player[p] if h["card"] == to]
        cands.sort(key=lambda x: (x[1]["player"] != c["player"], x[1]["token"], x[0]))
        if cands:
            hosts[cid] = cands[0][0]
            labels.setdefault(cands[0][0], f"c{cands[0][0]}")
    for i, p in enumerate(players):
        hp = life.get(p, 40)
        if hp == 0:
            # A seat at 0 has already lost. Forge's GameState crashes on a
            # life of 0 in a multiplayer state (writer.validate says why); at
            # -1 the seat loses at the game's first state-based check, as it
            # had in the game.
            notes.append(f"{p} had already lost (life 0); written at -1, which GameState can load.")
            hp = -1
        seat = {"deck": _rel(decks[i]), "life": hp,
                "lands_played": snap["lands_played"].get(p, 0),
                "battlefield": [], "hand": [], "graveyard": [], "exile": []}
        for cid, c in bf_by_player[p]:
            if c["token"]:
                script = token_script(c["logged_as"], c["pt"])
                if not script:
                    dropped.append(f"{c['logged_as']} {c['pt']} ({p})")
                    continue
                spec = {"token": script}
            else:
                spec = {"card": c["card"]}
                if c["logged_as"] != c["card"] and backs.get(c["logged_as"]) == c["card"]:
                    spec["transformed"] = True          # a double-faced card on its back face
                elif c["logged_as"] != c["card"]:
                    copies.append(f"{c['card']} as {c['logged_as']} ({p})")
            if snap["tapped"].get(cid):
                spec["tapped"] = True
            if p == active and c.get("entered") == turn and "Creature" in c["types"]:
                spec["sick"] = True
            cs = {COUNTERS[k]: v for k, v in snap["counters"].get(cid, {}).items() if k in COUNTERS and v > 0}
            if cs:
                spec["counters"] = cs
            if cid in labels:
                spec["id"] = labels[cid]
            if cid in hosts:
                spec["attached_to"] = labels[hosts[cid]]
            seat["battlefield"].append(spec)
        for zone, key in (("Hand", "hand"), ("Graveyard", "graveyard"), ("Exile", "exile")):
            seat[key] = [c["card"] for cid, c in sorted(snap["cards"].items())
                         if c["zone"] == zone and c["player"] == p and not c["token"]]
        seats.append(seat)
    # An attachment whose host was left off (an unknown token) is left unattached.
    emitted = {c["id"] for s in seats for c in s["battlefield"] if "id" in c}
    for s in seats:
        for c in s["battlefield"]:
            if c.get("attached_to") and c["attached_to"] not in emitted:
                dropped.append(f"(attachment of {c.get('card')} to that token)")
                del c["attached_to"]
    if dropped:
        notes.append("Tokens with no known Forge token script, left off the board: " + ", ".join(dropped) + ".")
    if copies:
        notes.append("Placed under their printed names, so Forge asks again what they copy: "
                     + ", ".join(copies) + ".")
    notes.append("Not carried: poison and other player counters, the library order (the rest of each deck "
                 "is shuffled per trial), commander tax and damage, this-turn effects, the mana pool.")
    return {"format": "simlab-scenario/1", "id": sid,
            "description": "", "source": {"file": path.name, "game": game, "turn": turn,
                                          "active": active, "agents": meta.get("agents"),
                                          "shim": meta.get("shim")},
            "seats": seats, "active": players.index(active), "turn": turn, "phase": "MAIN1",
            "notes": notes}


def _rel(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        # The game ran from another checkout of this repo: keep the path under
        # studies/ so it resolves against this one.
        s = Path(p).as_posix()
        return s[s.index("studies/"):] if "studies/" in s else s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl")
    ap.add_argument("--game", type=int, required=True)
    ap.add_argument("--turn", type=int, required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--deck-dir", help="take each seat's deck from DIR/<name>.dck instead of the meta path")
    ap.add_argument("--forge-index", help="Forge index cards.json, to seed double-faced cards on their back face")
    ap.add_argument("--out")
    args = ap.parse_args()
    sc = build(Path(args.jsonl), args.game, args.turn, args.id, Path(args.deck_dir) if args.deck_dir else None,
               Path(args.forge_index) if args.forge_index else None)
    text = json.dumps(sc, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
