#!/usr/bin/env python3
"""writer.py: scenario JSON -> Forge GameState text, and the round trip.

    py studies/scenarios/tests/test_writer.py

The round trip parses puzzle-style state text (the [state] block of Forge's
res/puzzle/*.pzl: human/ai keys, Id/AttachedTo, Counters, Tapped,
SummonSick, inline t: tokens, IsCommander), turns it into scenario seats,
writes it back with writer.build and parses the result: the two must be
the same state. The fixture below is written in that style for this test.
When Forge's own puzzles are on disk ($FORGE_RES, else ~/forge/res), every
shipped puzzle the format can carry is round-tripped too.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import writer as W  # noqa: E402

REPO = HERE.parent.parent.parent

# Puzzle-style state, 2 players, in the shipped .pzl layout.
PUZZLE = """[metadata]
Name:Harness round-trip fixture
Goal:Win
Turns:1
Description:Not a Forge puzzle; written for this test in the puzzle format.
[state]
humanlife=20
ailife=7
turn=3
activeplayer=human
activephase=MAIN1
removesummoningsickness=true
humanhand=Lightning Bolt;Dark Ritual
humanbattlefield=Godo, Bandit Warlord|Id:1|IsCommander;Helm of the Host|AttachedTo:1;Mountain|Tapped;Mountain;Walking Ballista|Counters:P1P1=2|SummonSick|Damage:1;t:Servo,P:1,T:1,Cost:no cost,Types:Artifact-Creature-Servo,Keywords:,Image:c_1_1_servo
humangraveyard=Lotus Petal
humanlibrary=Sol Ring;Mox Opal;Island
humancommand=
aibattlefield=Island|Tapped;Birds of Paradise;Swamp
aihand=Counterspell
aiexile=Force of Will
ailibrary=Brainstorm;Ponder
aicounters=POISON=4
"""


def _normalise(parsed: dict) -> dict:
    """The comparable content of a parsed state: absent zones are empty,
    absent lands played are 0, human/ai are p0/p1."""
    c = W.canonical(parsed)
    g = dict(c["global"])
    ap = g.get("activeplayer", "")
    g["activeplayer"] = {"human": "p0", "ai": "p1"}.get(ap, ap)
    g["turn"] = g.get("turn", "1")          # GameState's default
    g["removesummoningsickness"] = str(g.get("removesummoningsickness", "false")).lower() == "true"
    players = {}
    for idx, ps in c["players"].items():
        zones = {z: ps["zones"].get(z, []) for z in W.ZONES}
        players[int(idx)] = {"life": ps.get("life"), "landsplayed": ps.get("landsplayed", 0),
                             "counters": ps.get("counters", {}), "zones": zones}
    return {"global": g, "players": players}


def roundtrip(text: str, tmp: Path, tag: str) -> tuple[dict, dict]:
    """(original, rewritten), both normalised. Decks are written from the
    state's own cards so "rest of deck" is empty and libraries are explicit."""
    parsed = W.parse_state(text)
    if parsed["unknown"]:
        raise W.ScenarioError(f"keys outside the format: {parsed['unknown']}")
    extra = set(parsed["global"]) - {"turn", "activeplayer", "activephase", "removesummoningsickness"}
    if extra:
        raise W.ScenarioError(f"global keys outside the format: {sorted(extra)}")
    ap = parsed["global"].get("activeplayer", "")
    if not (ap in ("human", "ai") or (len(ap) == 2 and ap[0] == "p" and ap[1].isdigit())):
        raise W.ScenarioError(f"active player {ap!r} is not a seat")
    for ps in parsed["players"].values():
        if "life" not in ps:
            raise W.ScenarioError("a seat without a life line (the format always writes one)")
        if ps["zones"].get("sideboard"):
            raise W.ScenarioError("sideboard is not in the format")
    seats = W.state_to_seat_specs(parsed)
    sc = {"format": W.FORMAT, "id": tag, "seats": [],
          "turn": int(parsed["global"].get("turn", 1)),
          "active": int(_normalise(parsed)["global"]["activeplayer"][1:]),
          "phase": parsed["global"].get("activephase", "MAIN1")}
    if parsed["global"].get("removesummoningsickness", "").lower() == "true":
        sc["remove_sickness"] = True
    for i, seat in enumerate(seats):
        names = Counter()
        commanders = []
        for zone, specs in seat.items():
            if zone not in W.ZONES:
                continue
            for s in specs:
                s = W._norm_card(s)
                if "card" in s:
                    names[s["card"]] += 1
                    if s.get("commander"):
                        commanders.append(s["card"])
        deck = tmp / f"{tag}_{i}.dck"
        lines = ["[metadata]", f"Name={tag}_{i}", "[Commander]"]
        lines += [f"1 {c}" for c in commanders]
        lines.append("[Main]")
        for n, k in sorted((names - Counter(commanders)).items()):
            lines.append(f"{k} {n}")
        deck.write_text("\n".join(lines) + "\n", encoding="utf-8")
        s2 = {k: v for k, v in seat.items() if k != "sideboard"}
        s2["deck"] = str(deck)
        s2["library"] = seat.get("library", [])     # explicit: rest none
        s2.setdefault("life", 20)
        sc["seats"].append(s2)
    W.validate(sc)
    text2, info = W.build(sc, seed=0)
    assert not info["warnings"], info["warnings"]
    return _normalise(parsed), _normalise(W.parse_state(text2))


def main() -> None:
    # 1. The committed spike scenario: every seat, every zone, the syntax.
    sc = W.load(REPO / "studies/scenarios/spike/spike_4p.json")
    text, info = W.build(sc, seed=1)
    lines = text.splitlines()
    assert all(l.strip() for l in lines), "no blank lines (GameState throws on one)"
    keys = [l.split("=", 1)[0] for l in lines]
    assert keys[:3] == ["turn", "activeplayer", "activephase"]
    assert "activeplayer=p1" in lines and "activephase=MAIN1" in lines and "turn=5" in lines
    for i in range(4):
        for z in W.ZONES:
            assert f"p{i}{z}" in keys, f"seat {i} zone {z} must be written, even empty"
        assert f"p{i}life" in keys
    st = dict(l.split("=", 1) for l in lines)
    assert st["p2counters"] == "POISON=3" and st["p2life"] == "30" and st["p3life"] == "40"
    bf1 = st["p1battlefield"].split(";")
    assert bf1[0] == "Godo, Bandit Warlord|IsCommander|Id:1", bf1[0]
    assert bf1[1] == "Helm of the Host|AttachedTo:1"
    assert "Urza's Saga|Counters:LORE=2" in bf1 and "T:c_a_treasure_sac" in bf1
    assert "Mountain|Tapped" in bf1
    bf0 = st["p0battlefield"].split(";")
    assert bf0[0] == "Derevi, Empyrial Tactician|SummonSick|IsCommander"
    assert "Birds of Paradise|Counters:P1P1=1|Damage:1" in bf0
    assert st["p3command"] == ("Rograkh, Son of Rohgahh|IsCommander;"
                               "Silas Renn, Seeker Adept|IsCommander"), "unplaced commanders go to command"
    assert st["p0command"] == "" and st["p2exile"] == "Force of Negation"
    lib0 = st["p0library"].split(";")
    assert lib0[:2] == ["Ancient Tomb", "Mana Crypt"], "explicit top first"
    placed0 = 5 + 2 + 1       # battlefield + hand + graveyard
    assert len(lib0) == 100 - placed0, len(lib0)
    deck0 = W.read_deck(REPO / sc["seats"][0]["deck"])
    everything0 = Counter(lib0) + Counter(c.split("|")[0] for z in ("battlefield", "hand", "graveyard")
                                          for c in st[f"p0{z}"].split(";"))
    assert everything0 == deck0["cards"], "the seat holds exactly its 100 cards"
    assert info["seats"][1]["battlefield"][1] == {
        "card": "Helm of the Host", "token": False, "tapped": False, "sick": False, "counters": {},
        "attached_to": "Godo, Bandit Warlord", "commander": False, "damage": 0}
    assert info["seats"][1]["battlefield"][-1]["token"] is True
    assert info["warnings"] == [], info["warnings"]
    print("  spike scenario: 4 seats, every zone written, syntax and 100-card seats: OK")

    # 2. Library shuffle: seeded, reproducible, same multiset.
    t1, _ = W.build(sc, seed=1)
    t2, _ = W.build(sc, seed=2)
    assert t1 == text, "same seed, same text"
    l1 = dict(l.split("=", 1) for l in t1.splitlines())["p3library"].split(";")
    l2 = dict(l.split("=", 1) for l in t2.splitlines())["p3library"].split(";")
    assert l1 != l2 and Counter(l1) == Counter(l2)
    print("  library 'rest shuffled': seeded, reproducible, same cards: OK")

    # 3. Round trip against the puzzle-style fixture.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        a, b = roundtrip(PUZZLE, tmp, "fixture")
        assert a == b, json.dumps({"orig": a, "rewritten": b}, indent=1)[:3000]
        assert a["players"][1]["counters"] == {"POISON": "4"}
        assert a["players"][0]["zones"]["battlefield"][0]["opts"]["Id"] == "1"
        assert a["players"][0]["zones"]["battlefield"][1]["opts"]["AttachedTo"] == "1"
        print("  round trip, puzzle-style fixture (human/ai, Id/AttachedTo, t: token): OK")

        # 4. Forge's shipped puzzles, when present: every one the format can carry.
        res = Path(os.environ.get("FORGE_RES", Path.home() / "forge" / "res")) / "puzzle"
        if res.is_dir():
            ok, skipped = 0, 0
            for pz in sorted(res.glob("*.pzl")):
                try:
                    a, b = roundtrip(pz.read_text(encoding="utf-8", errors="replace"), tmp, pz.stem)
                except W.ScenarioError:
                    skipped += 1        # precast, putonstack, manapool, ... : not in the format
                    continue
                assert a == b, f"{pz.name} does not round-trip"
                ok += 1
            assert ok >= 50, f"only {ok} shipped puzzles round-tripped"
            print(f"  round trip, Forge's shipped puzzles: {ok} identical, {skipped} outside the format: OK")
        else:
            print(f"  (Forge puzzles not found at {res}; shipped round trip skipped)")

    # 5. Validation refuses what Forge cannot seed or the writer cannot say.
    base = json.loads((REPO / "studies/scenarios/spike/spike_4p.json").read_text(encoding="utf-8"))
    bad_cases = {
        "combat phase": dict(base, phase="COMBAT_DECLARE_ATTACKERS"),
        "five seats": dict(base, seats=base["seats"] + base["seats"][:1]),
        "unknown key": dict(base, manapool="R"),
        "active out of range": dict(base, active=4),
        "bad format": dict(base, format="x"),
    }
    dup = json.loads(json.dumps(base))
    dup["seats"][0]["battlefield"].append({"card": "Sol Ring", "id": "godo"})
    bad_cases["duplicate id"] = dup
    dangling = json.loads(json.dumps(base))
    dangling["seats"][0]["battlefield"].append({"card": "Sol Ring", "attached_to": "nobody"})
    bad_cases["dangling attached_to"] = dangling
    two_heads = json.loads(json.dumps(base))
    two_heads["seats"][0]["hand"].append({"card": "Sol Ring", "token": "c_a_treasure_sac"})
    bad_cases["card and token"] = two_heads
    zero = json.loads(json.dumps(base))
    zero["seats"][3]["life"] = 0
    bad_cases["life 0 (Forge's GameState indexes past the removed seat)"] = zero
    for name, case in bad_cases.items():
        case["_path"] = str(REPO / "studies/scenarios/spike/spike_4p.json")
        try:
            W.validate(case)
            W.build(case, seed=0)
        except W.ScenarioError:
            continue
        raise AssertionError(f"{name} was accepted")
    print(f"  validation refuses {len(bad_cases)} malformed scenarios: OK")

    # 6. A card placed beyond the deck's copies is warned about, not dropped.
    over = json.loads(json.dumps(base))
    over["seats"][0]["hand"].append("Sol Ring")          # derevi holds one, already on the battlefield
    over["_path"] = base_path = str(REPO / "studies/scenarios/spike/spike_4p.json")
    _, info = W.build(over, seed=0)
    assert any("Sol Ring placed 2x" in w for w in info["warnings"]), info["warnings"]
    print("  over-placement warns: OK")

    # 7. Imprint: the host names the exiled card, the exiled card names its host.
    imp = json.loads(json.dumps(base))
    imp["_path"] = base_path
    imp["seats"][0]["battlefield"].append({"card": "Isochron Scepter", "id": "scepter", "imprinting": "rev"})
    imp["seats"][0]["exile"] = [{"card": "Dramatic Reversal", "id": "rev", "exiled_with": "scepter"}]
    W.validate(imp)
    text_i, info_i = W.build(imp, seed=0)
    st_i = dict(l.split("=", 1) for l in text_i.splitlines())
    scepter = [c for c in st_i["p0battlefield"].split(";") if c.startswith("Isochron Scepter")][0]
    rev = st_i["p0exile"]
    sid = scepter.split("Id:")[1].split("|")[0]
    rid = rev.split("Id:")[1].split("|")[0]
    assert f"Imprinting:{rid}" in scepter and f"ExiledWith:{sid}" in rev, (scepter, rev)
    assert any("Isochron Scepter placed 1x, deck holds 0" in w for w in info_i["warnings"])
    back = W.state_to_seat_specs(W.parse_state(text_i))[0]
    assert {"card": "Dramatic Reversal", "id": f"id{rid}", "exiled_with": f"id{sid}"} in back["exile"]
    dang = json.loads(json.dumps(imp))
    dang["seats"][0]["exile"][0]["exiled_with"] = "nobody"
    try:
        W.build(dang, seed=0)
        raise AssertionError("dangling exiled_with accepted")
    except W.ScenarioError:
        pass
    print("  imprint (Imprinting / ExiledWith), inverse parse, dangling reference refused: OK")

    print("writer: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
