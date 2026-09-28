#!/usr/bin/env python3
"""Scenario JSON -> Forge GameState text (the puzzle-mode state format).

    py studies/scenarios/writer.py SCENARIO.json [--seed N] [--out FILE]

The shim's --scenario flag (0.17.1) hands the text to forge.game.GameState
once per game, after mulligans and before any priority (README.md). This
module is the only place scenario content is turned into Forge's format, so
every rule about that format lives here:

  * keys are p0..p3 (GameState reads one digit after "p"); seat i is the
    i-th --decks entry, which is Forge's registered player order;
  * every zone of every seat is written, empty ones as "p0graveyard=",
    because GameState clears every zone before it fills the ones it is given
    (an absent library is an empty library: the seat decks itself on its
    next draw);
  * no blank lines (GameState's line splitter throws on one);
  * a card is "Name|Opt|Opt:Value" and a zone is cards joined by ";";
  * a seat's commanders are marked |IsCommander wherever they are placed,
    and a commander the scenario does not place goes to the command zone;
  * "library": {"rest": "shuffled"} is the deck minus every card placed
    elsewhere, shuffled here with the trial's seed (Forge never shuffles
    it), top card first, which is the order GameState writes the zone in.

Stdlib only. No card knowledge: names are copied, never interpreted.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

FORMAT = "simlab-scenario/1"
ZONES = ("battlefield", "hand", "graveyard", "exile", "command", "library")
# Forge PhaseType names accepted by PhaseType.smartValueOf. Combat steps are
# refused: GameState seeds combat only for a two-player game.
PHASES = ("UNTAP", "UPKEEP", "DRAW", "MAIN1", "COMBAT_BEGIN", "COMBAT_END",
          "MAIN2", "END_OF_TURN", "CLEANUP")
MAX_SEATS = 4
# Scenario card keys -> Forge option. Booleans become a bare flag.
FLAG_OPTS = {"tapped": "Tapped", "sick": "SummonSick", "face_down": "FaceDown",
             "transformed": "Transformed", "flipped": "Flipped",
             "no_etb": "NoETBTrigs", "commander": "IsCommander",
             "token_flag": "IsToken", "monstrous": "Monstrous",
             "renowned": "Renowned"}
CARD_KEYS = {"card", "token", "token_info", "id", "attached_to", "counters",
             "damage", "set", "imprinting", "exiled_with", *FLAG_OPTS}
HEADS = ("card", "token", "token_info")   # exactly one per card spec
SEAT_KEYS = {"deck", "pilots", "life", "poison", "counters", "lands_played",
             "label", *ZONES}
TOP_KEYS = {"format", "id", "description", "seats", "active", "turn", "phase",
            "success", "line", "horizon_turns", "notes", "remove_sickness",
            "tests", "source"}
# success types -> required keys (run_scenarios.parse_trial scores them):
#   win:   the seat wins (at or before game turn by_turn, when given);
#   zone:  a card in cards moves from zone `from` to zone `to` for the seat
#          by by_turn (with "first": true, the seat's first such move must be
#          one of them), which is how a tutor's pick is scored;
#   alive: the seat has not lost when the game ends (cap the game at by_turn
#          with horizon_turns), which is how "do not kill yourself" is scored.
SUCCESS_TYPES = {"win": set(), "zone": {"from", "to", "cards", "by_turn"},
                 "alive": {"by_turn"}}


class ScenarioError(ValueError):
    pass


# --- decks ---------------------------------------------------------------

def read_deck(path: Path) -> dict:
    """{"name", "commanders": [..], "cards": Counter(name -> copies)} from a
    Forge .dck. cards holds the commanders too: the whole 100."""
    name = path.stem
    commanders: list[str] = []
    cards: Counter = Counter()
    section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if section == "metadata":
            if line.lower().startswith("name="):
                name = line.split("=", 1)[1].strip()
            continue
        m = re.match(r"(\d+)\s+(.+?)(?:\|.*)?$", line)
        if not m or section not in ("commander", "main"):
            continue
        n, card = int(m.group(1)), m.group(2).strip()
        cards[card] += n
        if section == "commander":
            commanders.extend([card] * n)
    return {"name": name, "commanders": commanders, "cards": cards, "path": str(path)}


def resolve_path(p: str, base: Path | None = None) -> Path:
    """A deck path: absolute, or relative to the scenario file, then to the
    repo. Environment variables expand ("$SIMLAB_PRIVATE/dck/x.dck"), so a
    scenario on a private deck can be committed without the deck."""
    q = Path(os.path.expandvars(p))
    if q.is_absolute():
        return q
    for root in ([base] if base else []) + [REPO]:
        cand = root / q
        if cand.exists():
            return cand
    return REPO / q


# --- cards ---------------------------------------------------------------

def _norm_card(spec) -> dict:
    if isinstance(spec, str):
        return {"card": spec}
    if not isinstance(spec, dict):
        raise ScenarioError(f"card spec must be a name or an object: {spec!r}")
    bad = set(spec) - CARD_KEYS
    if bad:
        raise ScenarioError(f"unknown card keys {sorted(bad)} in {spec!r}")
    if sum(h in spec for h in HEADS) != 1:
        raise ScenarioError(f"a card spec needs exactly one of {HEADS}: {spec!r}")
    return dict(spec)


def _label(spec: dict) -> str:
    """How a spec is named in info and reports: the card name, or the token
    in Forge's own syntax."""
    if "card" in spec:
        return spec["card"]
    if "token" in spec:
        return "T:" + spec["token"]
    return "t:" + spec["token_info"]


def _card_name(spec: dict) -> str | None:
    return spec.get("card")


def card_text(spec: dict, ids: dict[str, int]) -> str:
    """One card in Forge's zone syntax."""
    # token: a script name from Forge's res/tokenscripts (T:c_a_treasure_sac);
    # token_info: Forge's inline token string (t:Servo,P:1,T:1,...), which
    # shipped puzzles use.
    head = _label(spec)
    for bad in (";", "|", "\n", "="):
        if bad in head:
            raise ScenarioError(f"card name contains {bad!r}: {head!r}")
    opts = [head]
    if spec.get("set"):
        opts.append(f"Set:{spec['set']}")
    for key, flag in FLAG_OPTS.items():
        if spec.get(key):
            opts.append(flag)
    if spec.get("counters"):
        pairs = ",".join(f"{k}={int(v)}" for k, v in spec["counters"].items())
        opts.append(f"Counters:{pairs}")
    if spec.get("damage"):
        opts.append(f"Damage:{int(spec['damage'])}")
    if "id" in spec:
        opts.append(f"Id:{ids[str(spec['id'])]}")
    if "attached_to" in spec:
        ref = str(spec["attached_to"])
        if ref not in ids:
            raise ScenarioError(f"attached_to {ref!r} names no card id in the scenario")
        opts.append(f"AttachedTo:{ids[ref]}")
    # Imprint (Isochron Scepter holding Dramatic Reversal): the host names the
    # imprinted card(s) with Imprinting:, and the exiled card names its host
    # with ExiledWith:. Forge's Scepter reads both (IsImprinted+ExiledWithSource).
    if "imprinting" in spec:
        refs = spec["imprinting"] if isinstance(spec["imprinting"], list) else [spec["imprinting"]]
        for ref in map(str, refs):
            if ref not in ids:
                raise ScenarioError(f"imprinting {ref!r} names no card id in the scenario")
        opts.append("Imprinting:" + ",".join(str(ids[str(r)]) for r in refs))
    if "exiled_with" in spec:
        ref = str(spec["exiled_with"])
        if ref not in ids:
            raise ScenarioError(f"exiled_with {ref!r} names no card id in the scenario")
        opts.append(f"ExiledWith:{ids[ref]}")
    return "|".join(opts)


# --- scenario -> state ---------------------------------------------------

def load(path: str | Path) -> dict:
    p = Path(path)
    sc = json.loads(p.read_text(encoding="utf-8"))
    sc["_path"] = str(p)
    validate(sc)
    return sc


def validate(sc: dict) -> None:
    if sc.get("format") != FORMAT:
        raise ScenarioError(f"format must be {FORMAT!r}")
    bad = set(k for k in sc if not k.startswith("_")) - TOP_KEYS
    if bad:
        raise ScenarioError(f"unknown scenario keys {sorted(bad)}")
    seats = sc.get("seats")
    if not isinstance(seats, list) or not 2 <= len(seats) <= MAX_SEATS:
        raise ScenarioError(f"seats must be a list of 2 to {MAX_SEATS}")
    for i, seat in enumerate(seats):
        bad = set(seat) - SEAT_KEYS
        if bad:
            raise ScenarioError(f"seat {i}: unknown keys {sorted(bad)}")
        if "deck" not in seat:
            raise ScenarioError(f"seat {i}: deck is required")
        for z in ZONES:
            if z == "library" and isinstance(seat.get(z), dict):
                lib = seat[z]
                if set(lib) - {"top", "rest", "bottom"}:
                    raise ScenarioError(f"seat {i}: library keys are top, rest, bottom")
                if lib.get("rest") not in (None, "shuffled", "none"):
                    raise ScenarioError(f"seat {i}: library rest is 'shuffled' or 'none'")
                for c in lib.get("top", []) + lib.get("bottom", []):
                    _norm_card(c)
                continue
            for c in seat.get(z, []) or []:
                _norm_card(c)
    active = sc.get("active", 0)
    if not isinstance(active, int) or not 0 <= active < len(seats):
        raise ScenarioError("active must be a seat index")
    phase = sc.get("phase", "MAIN1")
    if phase not in PHASES:
        raise ScenarioError(f"phase {phase!r} is not one of {PHASES}")
    if int(sc.get("turn", 1)) < 1:
        raise ScenarioError("turn must be >= 1")
    succ = sc.get("success")
    if succ is not None:
        kind = succ.get("type")
        if kind not in SUCCESS_TYPES or not isinstance(succ.get("seat"), int) \
                or not 0 <= succ["seat"] < len(seats):
            raise ScenarioError(f"success type is one of {sorted(SUCCESS_TYPES)} with a seat index")
        missing = SUCCESS_TYPES[kind] - set(succ)
        if missing:
            raise ScenarioError(f"success {kind!r} needs {sorted(missing)}")
        if kind == "zone" and (not isinstance(succ["cards"], list) or not succ["cards"]):
            raise ScenarioError("success 'zone' needs a non-empty cards list")
    ids = [c.get("id") for seat in seats for z in ZONES
           for c in _zone_specs(seat, z) if isinstance(c, dict) and "id" in c]
    dup = [k for k, n in Counter(map(str, ids)).items() if n > 1]
    if dup:
        raise ScenarioError(f"card ids must be unique across the scenario: {dup}")


def _zone_specs(seat: dict, zone: str) -> list:
    v = seat.get(zone)
    if v is None:
        return []
    if zone == "library" and isinstance(v, dict):
        return list(v.get("top", [])) + list(v.get("bottom", []))
    return list(v)


def build(sc: dict, seed: int = 0) -> tuple[str, dict]:
    """(state text, info). info carries each seat's deck, the exact expected
    zone contents (names, library top first) for checking what Forge applied,
    and warnings (cards placed that the deck does not hold, over-placement)."""
    base = Path(sc["_path"]).parent if sc.get("_path") else None
    rng = random.Random(seed)
    # Numeric ids, in order of appearance, for Id:/AttachedTo:.
    ids: dict[str, int] = {}
    for seat in sc["seats"]:
        for z in ZONES:
            for c in _zone_specs(seat, z):
                if isinstance(c, dict) and "id" in c:
                    ids[str(c["id"])] = len(ids) + 1
    lines = [f"turn={int(sc.get('turn', 1))}",
             f"activeplayer=p{int(sc.get('active', 0))}",
             f"activephase={sc.get('phase', 'MAIN1')}"]
    if sc.get("remove_sickness"):
        lines.append("removesummoningsickness=true")
    info = {"seats": [], "warnings": [], "seed": seed}
    for i, seat in enumerate(sc["seats"]):
        deck_path = resolve_path(seat["deck"], base)
        if not deck_path.is_file():
            raise ScenarioError(f"seat {i}: deck not found: {deck_path}")
        deck = read_deck(deck_path)
        cmdrs = Counter(deck["commanders"])
        zones: dict[str, list[dict]] = {}
        for z in ZONES:
            if z == "library":
                continue
            zones[z] = [_norm_card(c) for c in (seat.get(z) or [])]
        lib = seat.get("library", {"rest": "shuffled"})
        if isinstance(lib, list):
            lib = {"top": lib, "rest": "none"}
        top = [_norm_card(c) for c in lib.get("top", [])]
        bottom = [_norm_card(c) for c in lib.get("bottom", [])]
        placed = Counter(_card_name(c) for z in zones.values() for c in z if _card_name(c))
        placed.update(_card_name(c) for c in top + bottom if _card_name(c))
        # Commanders: marked wherever placed; unplaced ones go to command.
        for name, n in cmdrs.items():
            everywhere = [c for z in zones.values() for c in z] + top + bottom
            for c in everywhere:
                if _card_name(c) == name:
                    c.setdefault("commander", True)
            missing = n - placed[name]
            for _ in range(max(0, missing)):
                zones["command"].append({"card": name, "commander": True})
                placed[name] += 1
        for name, n in placed.items():
            have = deck["cards"].get(name, 0)
            if n > have:
                info["warnings"].append(
                    f"seat {i} ({deck['name']}): {name} placed {n}x, deck holds {have}")
        middle: list[dict] = []
        if lib.get("rest", "shuffled") == "shuffled":
            rest = deck["cards"] - placed
            pool = sorted(rest.elements())
            rng.shuffle(pool)
            middle = [{"card": n} for n in pool]
        library = top + middle + bottom
        zones["library"] = library
        life = int(seat.get("life", 40))
        lines.append(f"p{i}life={life}")
        pc = dict(seat.get("counters") or {})
        if seat.get("poison"):
            pc["POISON"] = int(seat["poison"])
        if pc:
            lines.append(f"p{i}counters=" + ",".join(f"{k}={int(v)}" for k, v in pc.items()))
        lines.append(f"p{i}landsplayed={int(seat.get('lands_played', 0))}")
        for z in ZONES:
            lines.append(f"p{i}{z}=" + ";".join(card_text(c, ids) for c in zones[z]))
        info["seats"].append({
            "deck": deck["name"], "deck_path": deck["path"], "life": life,
            "poison": int(seat.get("poison", 0)),
            "commanders": deck["commanders"],
            "zones": {z: [_label(c) for c in zones[z]] for z in ZONES},
            "battlefield": [dict(c) for c in zones["battlefield"]],
        })
    # Battlefield signatures, comparable with the shim's scenario record
    # (run_scenarios.check_board): attached_to resolved to the host's label.
    names = {str(c["id"]): _label(c) for s in info["seats"] for c in s["battlefield"] if "id" in c}
    for s in info["seats"]:
        s["battlefield"] = [expected_sig(c, names) for c in s["battlefield"]]
    return "\n".join(lines) + "\n", info


def expected_sig(spec: dict, names: dict[str, str]) -> dict:
    """What a seeded battlefield card should read back as. Tokens are
    compared by count only: Forge names a token by its script's card name
    (Treasure Token), which the scenario does not spell."""
    token = "card" not in spec
    return {"card": None if token else spec["card"], "token": token,
            "tapped": bool(spec.get("tapped")), "sick": bool(spec.get("sick")),
            "counters": {k: int(v) for k, v in (spec.get("counters") or {}).items()},
            "attached_to": names.get(str(spec["attached_to"])) if "attached_to" in spec else None,
            "commander": bool(spec.get("commander")),
            "damage": int(spec.get("damage", 0))}


# --- Forge state text -> structure (for tests and for importing puzzles) --

_ALIAS = {"human": 0, "ai": 1}
_ZONE_KEYS = {"battlefield": "battlefield", "play": "battlefield", "hand": "hand",
              "graveyard": "graveyard", "library": "library", "exile": "exile",
              "command": "command", "sideboard": "sideboard"}


def _player_of(key: str) -> tuple[int | None, str]:
    for alias, idx in _ALIAS.items():
        if key.startswith(alias):
            return idx, key[len(alias):]
    if len(key) > 1 and key[0] == "p" and key[1].isdigit():
        return int(key[1]), key[2:]
    return None, key


def parse_state(text: str) -> dict:
    """Parse Forge state text the way GameState.parseLine does (keys lower
    cased, human = p0, ai = p1, the [state] block of a .pzl), into
    {"global": {...}, "players": {i: {"life", "counters", "landsplayed",
    "zones": {zone: [{"card"|"token", "opts": {...}}]}}}, "unknown": [...]}."""
    out: dict = {"global": {}, "players": {}, "unknown": []}
    in_meta = False
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if line.strip().lower() == "[metadata]":
            in_meta = True
            continue
        if line.strip().lower() == "[state]":
            in_meta = False
            continue
        if in_meta or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.lower()
        if key.startswith("active"):
            out["global"][key] = value.strip().lower() if key.endswith("player") else value.strip().upper()
            continue
        if key in ("turn", "removesummoningsickness"):
            out["global"][key] = value.strip()
            continue
        idx, rest = _player_of(key)
        if idx is None:
            out["unknown"].append(key)
            continue
        ps = out["players"].setdefault(idx, {"zones": {}})
        if rest in _ZONE_KEYS:
            cards = [] if not value.strip() else [_parse_card(t) for t in value.split(";")]
            ps["zones"][_ZONE_KEYS[rest]] = cards
        elif rest in ("life", "landsplayed"):
            ps[rest] = int(value)
        elif rest == "counters":
            ps["counters"] = dict(kv.split("=", 1) for kv in value.split(",") if kv)
        else:
            out["unknown"].append(key)
    return out


def _parse_card(token: str) -> dict:
    parts = token.strip().split("|")
    head, opts = parts[0], {}
    for o in parts[1:]:
        if ":" in o:
            k, v = o.split(":", 1)
            opts[k] = v
        else:
            opts[o] = True
    if head.startswith("T:"):
        return {"token": head[2:], "opts": opts}
    if head.startswith("t:"):
        return {"token_info": head[2:], "opts": opts}
    return {"card": head, "opts": opts}


_OPT_TO_KEY = {v: k for k, v in FLAG_OPTS.items()}


def state_to_seat_specs(parsed: dict) -> list[dict]:
    """Seat zone specs (the scenario's card objects) from parsed state text:
    the inverse of card_text for the options the scenario format carries.
    Ids become labels "id<N>"; options the format does not carry raise."""
    seats = []
    for idx in sorted(parsed["players"]):
        ps = parsed["players"][idx]
        seat: dict = {}
        for zone, cards in ps["zones"].items():
            specs = []
            for c in cards:
                spec = {h: c[h] for h in HEADS if h in c}
                for k, v in c["opts"].items():
                    if k in _OPT_TO_KEY:
                        if v is not True:       # FaceDown:Manifested and the like
                            raise ScenarioError(f"option {k}:{v} is not in the scenario format")
                        spec[_OPT_TO_KEY[k]] = True
                    elif k == "Id":
                        spec["id"] = f"id{v}"
                    elif k in ("AttachedTo", "Attaching"):
                        spec["attached_to"] = f"id{v}"
                    elif k == "Imprinting":
                        spec["imprinting"] = [f"id{x}" for x in v.split(",")]
                    elif k == "ExiledWith":
                        spec["exiled_with"] = f"id{v}"
                    elif k == "Counters":
                        spec["counters"] = {a: int(b) for a, b in
                                            (p.split("=", 1) for p in v.split(","))}
                    elif k == "Damage":
                        spec["damage"] = int(v)
                    elif k == "Set":
                        spec["set"] = v
                    else:
                        raise ScenarioError(f"option {k!r} is not in the scenario format")
                specs.append(spec if len(spec) > 1 or "card" not in spec else spec["card"])
            seat[zone] = specs
        if "life" in ps:
            seat["life"] = ps["life"]
        if "landsplayed" in ps:
            seat["lands_played"] = ps["landsplayed"]
        counters = dict(ps.get("counters", {}))
        if "POISON" in counters:
            seat["poison"] = int(counters.pop("POISON"))
        if counters:
            seat["counters"] = {k: int(v) for k, v in counters.items()}
        seats.append(seat)
    return seats


def canonical(parsed: dict) -> dict:
    """parse_state output with Id numbers renamed in order of first
    appearance, so two texts that differ only in id numbering compare equal."""
    ren: dict[str, str] = {}
    out = json.loads(json.dumps(parsed))
    for idx in sorted(out["players"], key=int):
        for zone in sorted(out["players"][idx]["zones"]):
            for c in out["players"][idx]["zones"][zone]:
                if "Id" in c["opts"]:
                    ren.setdefault(c["opts"]["Id"], str(len(ren) + 1))
    for ps in out["players"].values():
        for cards in ps["zones"].values():
            for c in cards:
                for k in ("Id", "AttachedTo", "Attaching", "ExiledWith"):
                    if k in c["opts"]:
                        v = c["opts"].pop(k)
                        c["opts"]["AttachedTo" if k == "Attaching" else k] = ren.get(v, v)
                if "Imprinting" in c["opts"]:
                    c["opts"]["Imprinting"] = ",".join(ren.get(x, x) for x in c["opts"]["Imprinting"].split(","))
    return out


def write_state(path: Path, text: str) -> None:
    """LF line ends on every platform (the shim strips a CR anyway)."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario")
    ap.add_argument("--seed", type=int, default=0, help="library shuffle seed")
    ap.add_argument("--out", default=None, help="write the state text here (default stdout)")
    args = ap.parse_args()
    text, info = build(load(args.scenario), seed=args.seed)
    for w in info["warnings"]:
        print("warning:", w, file=sys.stderr)
    if args.out:
        write_state(Path(args.out), text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
