#!/usr/bin/env python3
"""Reconstruct battlefield state from a Forge event log, and emit snapshots.

## Why this is inference rather than a read

Forge's text log records cards LEAVING the battlefield but never ENTERING it.
Verified on a real 16-game log: 134 "Battlefield -> Graveyard", 15 "-> Exile",
zero entries. There is no verbosity flag that adds them, and patching Forge is
off the table (it must stay an unmodified GPL process, per
frontend_architecture.md §5). So entries have to be inferred:

  land_drop      "X played Island (254)"        -> explicit, reliable
  stack_resolve  a resolved PERMANENT enters    -> needs the card's type_line
  tokens         only visible once they act     -> first sighting adds them
  zone_change    "… from Battlefield"           -> explicit, reliable

The middle case is why engine/cards.py exists: without a type_line we cannot tell
"Sol Ring" (stays) from "Swords to Plowshares" (does not). Cards whose type is
unknown are recorded with kind "unknown" and `assumed: true` rather than being
silently dropped or silently kept.

## Self-validation

Because exits ARE explicit, they act as an oracle: any card Forge says left the
battlefield must have been on our reconstruction at that moment. `validate()`
counts "orphan exits" (a card leaving a board it was never on). Orphans are the
honest error rate of this module, reported per run rather than hidden.

CLI:
  python3 board.py <result.json>            # accuracy report
  python3 board.py <result.json> --write    # add board_snapshot events in place
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import cards

# "Ai(2)-Kilo Helm Final played Island (254)"
_PLAYED = re.compile(r"^(.+?)\s+played\s+(.+?)\s*\((\d+)\)")
# "Ai(3)-Wyleth Voltron B3 cast Leonin Shikari" / "… activated Sol Ring"
_CAST = re.compile(r"^(.+?)\s+(?:cast|casts|played|activated|triggered)\s+(.+?)(?:\s+targeting|\.|$)", re.I)
# "Leonin Shikari (274) was put into Graveyard from Battlefield."
_EXIT = re.compile(r"^(.+?)\s*\((\d+)\)\s+was put into\s+(\w+)\s+from\s+(\w+)")
# "Leonin Shikari - Creature 2 / 2"
_RESOLVE_PT = re.compile(r"^(.+?)\s+-\s+Creature\s+(\d+)\s*/\s*(\d+)")
# "Ai(2)-Wilhelt … assigned Zombie Token (420) to attack Ai(3)-Wyleth …"
# Forge batches attackers onto ONE line: "assigned A (1), B (2), C (3) to attack X",
# so the attacker list must be parsed as a list, not a single reference.
_ATTACK = re.compile(r"^(.+?)\s+assigned\s+(.+?)\s+to attack\s+(.+?)\.?$")
# "Ai(4)-Drana Vampires didn't block Kilo, Apogee Mind (100)." — the named player
# is the DEFENDER; the referenced creature belongs to whoever is attacking.
_NOBLOCK = re.compile(r"^(.+?)\s+(?:didn't|doesn't)\s+block\s+(.+?)\.?$")
# "Name (123)" pairs inside a list segment. The name must NOT exclude commas:
# real lists read "Kilo, Apogee Mind (100) and Crystalline Crawler (72)", and card
# names carry commas of their own, so cutting on them yielded "Apogee Mind" and
# "and Crystalline Crawler". Each name instead runs up to its own instance id,
# with only the joining punctuation trimmed off the front.
_REF = re.compile(r"([^()\[\]]+?)\s*\((\d+)\)")
_JOIN = re.compile(r"^[\s,;]*(?:and\s+)?")


def _refs(segment: str) -> list[tuple[str, str]]:
    """[(name, instance_id)] for every "Name (123)" in a list segment."""
    return [(_JOIN.sub("", nm).strip(), inst) for nm, inst in _REF.findall(segment)]


def _clean(name: str) -> str:
    return cards.normalize_name(name)


class Board:
    """Battlefield membership per player, keyed by Forge instance id.

    Instance ids matter: "Zombie Token (406)" and "(420)" are different objects,
    as are two copies of Island. Cards seen without an id (a resolve line carries
    no id) get a synthetic key so they can still be displayed and later removed
    by name if an exit names them.
    """

    def __init__(self, players: list[str]) -> None:
        self.players = list(players)
        # player -> {key: {"name","id","kind","assumed"}}
        self.zones: dict[str, dict[str, dict]] = {p: {} for p in players}
        self.orphan_exits: list[dict] = []
        self.entries = 0
        self.assumed_entries = 0
        self._synth = 0

    # ---- membership ----

    def _owner_of(self, key: str) -> str | None:
        for p, z in self.zones.items():
            if key in z:
                return p
        return None

    def _find_by_name(self, name: str) -> tuple[str, str] | None:
        """(player, key) for the most recently added card of this name."""
        for p, z in self.zones.items():
            for k in reversed(list(z)):
                if z[k]["name"] == name:
                    return p, k
        return None

    def add(self, player: str, name: str, inst: str | None, kind: str,
            assumed: bool = False) -> None:
        name = _clean(name)
        if not name or player not in self.zones:
            return
        if inst is None:
            self._synth += 1
            key = f"{name}#s{self._synth}"
        else:
            key = inst
            if any(key in z for z in self.zones.values()):
                return  # already tracked
        self.zones[player][key] = {"name": name, "id": inst, "kind": kind,
                                   "assumed": assumed}
        self.entries += 1
        if assumed:
            self.assumed_entries += 1

    def remove(self, name: str, inst: str | None, turn: int, raw: str) -> bool:
        """Remove on an explicit exit. Returns False when nothing matched."""
        name = _clean(name)
        if inst is not None:
            owner = self._owner_of(inst)
            if owner:
                del self.zones[owner][inst]
                return True
        hit = self._find_by_name(name)
        if hit:
            p, k = hit
            del self.zones[p][k]
            return True
        self.orphan_exits.append({"turn": turn, "name": name, "id": inst,
                                  "raw": raw[:120]})
        return False

    def sight(self, player: str, name: str, inst: str, kind: str,
              assumed: bool = False) -> None:
        """Record an object proven to be on `player`'s battlefield right now.

        Idempotent: re-sighting an object already tracked (for anyone) is a no-op,
        so repeated combat lines don't duplicate it.
        """
        if any(inst in z for z in self.zones.values()):
            return
        self.add(player, name, inst, kind, assumed)

    def owner_of_any(self, insts: list[str]) -> str | None:
        for i in insts:
            o = self._owner_of(i)
            if o:
                return o
        return None

    def snapshot(self) -> dict:
        return {
            p: [
                {"name": c["name"], "id": c["id"], "kind": c["kind"],
                 **({"assumed": True} if c["assumed"] else {})}
                for c in z.values()
            ]
            for p, z in self.zones.items()
        }


def _kind_for(name: str, fetch: bool) -> tuple[str, bool]:
    """(kind, assumed). assumed=True when we had no type data to go on."""
    if cards.is_token(name):
        return "token", False
    kind = cards.card_kind(name, fetch=fetch)
    return (kind, True) if kind == "unknown" else (kind, False)


def reconstruct(game: dict, fetch: bool = False) -> tuple[Board, list[dict]]:
    """Fold one game's events into board state, collecting per-turn snapshots."""
    board = Board(game.get("players", []))
    snapshots: list[dict] = []
    pending_cast: dict[str, str] = {}   # cleaned name -> caster
    last_attackers: list[str] = []      # instance ids in the current combat

    for t in game.get("turns", []):
        turn = t.get("turn", 0)
        for e in t.get("events", []):
            raw = e.get("raw", "")
            act = e.get("action")

            if act == "land_drop":
                m = _PLAYED.match(raw)
                if m:
                    board.add(m.group(1).strip(), m.group(2), m.group(3), "land")
                continue

            if act == "stack_add":
                m = _CAST.match(raw)
                if m:
                    pending_cast[_clean(m.group(2))] = m.group(1).strip()
                continue

            if act == "stack_resolve":
                # Creature resolves state their type outright; trust that first.
                pm = _RESOLVE_PT.match(raw)
                nm = _clean(pm.group(1) if pm else raw)
                if not nm:
                    continue
                caster = pending_cast.pop(nm, None)
                if caster is None:
                    continue          # a triggered ability, not a spell we tracked
                if pm:
                    board.add(caster, nm, None, "creature")
                    continue
                perm = cards.is_permanent(nm, fetch=fetch)
                if perm is True:
                    kind, assumed = _kind_for(nm, fetch)
                    board.add(caster, nm, None, kind, assumed)
                elif perm is None:
                    # Unknown type: record it, flagged, rather than guessing.
                    board.add(caster, nm, None, "unknown", assumed=True)
                continue

            if act == "combat":
                m = _ATTACK.match(raw)
                if m:
                    attacker = m.group(1).strip()
                    last_attackers.clear()
                    # Anything assigned to attack is provably on the attacker's
                    # battlefield — the strongest entry signal the log offers.
                    for nm, inst in _refs(m.group(2)):
                        board.sight(attacker, nm, inst, *_kind_for(nm, fetch))
                        last_attackers.append(inst)
                    continue
                m = _NOBLOCK.match(raw)
                if m and last_attackers:
                    # Defender named; the creature is the current attacker's.
                    owner = board.owner_of_any(last_attackers)
                    if owner:
                        for nm, inst in _refs(m.group(2)):
                            board.sight(owner, nm, inst, *_kind_for(nm, fetch))
                continue

            if act == "damage":
                # "X (12) deals 2 combat damage to P." — a creature dealing combat
                # damage was on the battlefield; attribute to the attacking side
                # when we know it, otherwise leave it alone rather than guess.
                if "combat damage" in raw and last_attackers:
                    owner = board.owner_of_any(last_attackers)
                    if owner:
                        head = raw.split(" deals ")[0]
                        for nm, inst in _refs(head):
                            board.sight(owner, nm, inst, *_kind_for(nm, fetch))
                continue

            if act == "zone_change":
                m = _EXIT.match(raw)
                if m and m.group(4).lower() == "battlefield":
                    board.remove(m.group(1), m.group(2), turn, raw)
                continue

        snapshots.append({"turn": turn, "board": board.snapshot()})

    return board, snapshots


def validate(result: dict, fetch: bool = False) -> dict:
    """Accuracy report across every game in a result file."""
    total_exits = orphans = entries = assumed = 0
    per_game = []
    for i, g in enumerate(result.get("games", []), 1):
        board, snaps = reconstruct(g, fetch=fetch)
        exits = sum(
            1
            for t in g.get("turns", [])
            for e in t.get("events", [])
            if e.get("action") == "zone_change"
            and (m := _EXIT.match(e.get("raw", "")))
            and m.group(4).lower() == "battlefield"
        )
        total_exits += exits
        orphans += len(board.orphan_exits)
        entries += board.entries
        assumed += board.assumed_entries
        per_game.append({
            "game": i, "exits": exits, "orphans": len(board.orphan_exits),
            "entries": board.entries, "assumed": board.assumed_entries,
            "final_sizes": {p: len(v) for p, v in board.snapshot().items()},
        })
    matched = total_exits - orphans
    return {
        "games": len(per_game),
        "exits_total": total_exits,
        "exits_matched": matched,
        "exit_match_rate": round(matched / total_exits, 4) if total_exits else None,
        "entries_total": entries,
        "entries_assumed": assumed,
        "assumed_share": round(assumed / entries, 4) if entries else None,
        "cache": cards.stats(),
        "per_game": per_game,
    }


def annotate(result: dict, fetch: bool = False) -> dict:
    """Add a board_snapshot event to the end of each turn, in place."""
    added = 0
    for g in result.get("games", []):
        _, snaps = reconstruct(g, fetch=fetch)
        by_turn = {s["turn"]: s["board"] for s in snaps}
        for t in g.get("turns", []):
            board = by_turn.get(t.get("turn"))
            if board is None:
                continue
            last_seq = t["events"][-1]["seq"] if t.get("events") else 0
            t.setdefault("events", []).append({
                "seq": last_seq,
                "action": "board_snapshot",
                "raw": "end-of-turn battlefield reconstruction",
                "board": board,
            })
            added += 1
    result.setdefault("meta", {})["board_snapshots"] = {
        "generator": "board.py",
        "turns_annotated": added,
        "basis": "inferred entries (Forge logs no battlefield entries) + explicit exits",
    }
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = Path(sys.argv[1])
    result = json.loads(path.read_text(encoding="utf-8"))
    fetch = "--no-fetch" not in sys.argv

    if "--write" in sys.argv:
        annotate(result, fetch=fetch)
        out = Path(sys.argv[sys.argv.index("--write") + 1]) if len(sys.argv) > sys.argv.index("--write") + 1 and not sys.argv[sys.argv.index("--write") + 1].startswith("--") else path
        out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"wrote snapshots to {out}")
        return

    rep = validate(result, fetch=fetch)
    print(json.dumps({k: v for k, v in rep.items() if k != "per_game"}, indent=2))
    print("\nper game:")
    for g in rep["per_game"]:
        print(f"  game {g['game']:2}  exits {g['exits']:3}  orphans {g['orphans']:3}"
              f"  entries {g['entries']:3}  assumed {g['assumed']:3}")


if __name__ == "__main__":
    main()
