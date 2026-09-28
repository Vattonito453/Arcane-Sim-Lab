#!/usr/bin/env python3
"""Build the readers' evidence files for the knockout and turning-point audit
(studies/knockout_audit/PREREG.md, "What readers see").

One plain-text file per game in the reading set: a header, Forge's log in
order, then a per-turn digest computed mechanically from the same records.
It reads only each game's events, pregame events and, on shim runs, Forge's
zone records. It imports no analyzer (engine/qa, analysis.py) and never
reads agent_events, plans, rubric, boardfx or validity. Card types for
shim logs older than 0.3.0 (zone records without types) come from the
committed Scryfall cache, never fetched.

The output holds a playtester's game logs, so it goes to a scratch folder and
is never committed.

Usage:
    py studies/knockout_audit/build_evidence.py <sample.json> <runs_dir> <out_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[2] / "engine"
sys.path.insert(0, str(_ENGINE))
import cards  # noqa: E402  (display and typing only; fetch=False throughout)

SIZE_LIMIT = 250 * 1024

# Forge's step lines, as printed after the player's possessive, and the short
# label each event line carries. Matched as a suffix, so a possessive name
# ("Ai(2)-Skrat's Revenge's Untap step") cannot confuse it.
_STEPS = (
    ("untap step", "Untap"),
    ("upkeep step", "Upkeep"),
    ("draw step", "Draw"),
    ("main phase, precombat", "Main 1"),
    ("beginning of combat step", "Begin combat"),
    ("declare attackers step", "Declare attackers"),
    ("declare blockers step", "Declare blockers"),
    ("first strike damage step", "First strike damage"),
    ("combat damage step", "Combat damage"),
    ("end of combat step", "End combat"),
    ("main phase, postcombat", "Main 2"),
    ("end step", "End step"),
    ("cleanup step", "Cleanup"),
)
_ZONE_STEPS = {
    "UNTAP": "Untap", "UPKEEP": "Upkeep", "DRAW": "Draw", "MAIN1": "Main 1",
    "COMBAT_BEGIN": "Begin combat", "COMBAT_DECLARE_ATTACKERS": "Declare attackers",
    "COMBAT_DECLARE_BLOCKERS": "Declare blockers",
    "COMBAT_FIRST_STRIKE_DAMAGE": "First strike damage",
    "COMBAT_DAMAGE": "Combat damage", "COMBAT_END": "End combat", "MAIN2": "Main 2",
    "END_OF_TURN": "End step", "CLEANUP": "Cleanup",
}
_LIFE = re.compile(r"^Life:\s+(?P<p>.+?)\s+(?P<a>-?\d+)\s*>\s*(?P<b>-?\d+)\s*$")
_POISON = re.compile(r"^(?P<p>.+?) receives (?P<n>\d+) poison counters? from (?P<src>.+?)\s*$")
_DMG = re.compile(r"^(?P<src>.+?) deals (?P<n>\d+) (?P<kind>combat |non-combat )?"
                  r"damage (?:\([^)]*\)\s*)?to (?P<tgt>.+?)\.?\s*$")
_RESOLVE_CREATURE = re.compile(
    r"^(?P<name>[^\[\]()]+?)\s+-\s+(?:[A-Za-z ]*\s)?Creature\s+(?P<p>[\d*+-]+)\s*/\s*(?P<t>[\d*+-]+)\s*$")
_TOKEN_BURST = re.compile(r" creates (?P<n>\w+) (?P<p>\d+)/(?P<t>\d+) (?P<desc>.+?) creature tokens?\b")
_EXIT = re.compile(r"^(?P<card>.+?\(\d+\)) was put into (?P<to>[A-Za-z ]+?) from Battlefield\.?\s*$")
_ID = re.compile(r"\s*\(\d+\)\s*$")
# Token names that are never creatures, for pre-0.3.0 zone records.
_NONCREATURE_TOKENS = {"treasure", "clue", "food", "blood", "gold", "map", "powerstone",
                       "incubator", "junk", "shard", "walker"}


def step_of(raw: str) -> str | None:
    low = raw.strip().lower()
    for suffix, label in _STEPS:
        if low.endswith(suffix):
            return label
    return None


def seat_prefix(text: str, seats: list[str]) -> str | None:
    for s in sorted(seats, key=len, reverse=True):
        if text.startswith(s + " "):
            return s
    return None


def strip_id(name: str) -> str:
    return _ID.sub("", name).strip()


def creature_info_shim(z: dict) -> tuple[bool | None, str]:
    """(is creature, label) for one zone record. None = type unknown."""
    types = z.get("types")
    if types is not None and types != "":
        is_c = "Creature" in types
        pt = z.get("pt") or ""
        tok = " token" if z.get("token") else ""
        return is_c, (f"{z.get('card')} {pt}{tok}".strip())
    name = z.get("card") or ""
    if cards.is_token(name):
        base = re.sub(r"\s*\bTokens?\b.*$", "", name, flags=re.I).strip().lower()
        if base in _NONCREATURE_TOKENS:
            return False, name
        return None, f"{name} (token; type not recorded)"
    c = cards.get(name, fetch=False)
    if not c or not c.get("type_line"):
        return None, f"{name} (type unknown)"
    if "Creature" in c["type_line"]:
        pt = f"{c.get('power')}/{c.get('toughness')}" if c.get("power") is not None else ""
        return True, f"{name} (printed {pt})" if pt else name
    return False, name


def is_creature_name(name: str) -> bool | None:
    """Stdout path: is a named card a creature? None = unknown."""
    n = strip_id(name)
    if cards.is_token(n):
        base = re.sub(r"\s*\bTokens?\b.*$", "", n, flags=re.I).strip().lower()
        return False if base in _NONCREATURE_TOKENS else None
    c = cards.get(n, fetch=False)
    if not c or not c.get("type_line"):
        return None
    return "Creature" in c["type_line"]


def build_game(key: str, game: dict, run_meta: dict, tp_requested: bool,
               drop_mana: bool) -> tuple[str, int, int]:
    seats = list(game.get("players") or [])
    zones = game.get("zones") or []
    shim = bool(zones)
    typed = shim and any(z.get("types") not in (None, "") for z in zones)
    out: list[str] = []
    w = out.append

    # ---- PART 1: the log ----
    log: list[str] = []
    dropped = 0
    log.append("Pregame")
    for e in game.get("events_pregame") or []:
        log.append(f"  {e.get('raw', '')}")
    for t in game.get("turns") or []:
        log.append("")
        log.append(f"=== Turn {t.get('turn')} | active player: {t.get('active_player')} ===")
        step = "-"
        for e in t.get("events") or []:
            raw = e.get("raw", "")
            if e.get("action") == "phase":
                s = step_of(raw)
                if s:
                    step = s
                    continue
            if drop_mana and e.get("action") == "mana":
                dropped += 1
                continue
            # Forge's end-of-game block is printed after play stops; the last
            # step label would wrongly place it inside that step.
            label = "Game over" if e.get("action") in ("game_outcome", "match_result") else step
            log.append(f"[{label}] {raw}")
            for m in e.get("more") or []:
                log.append(f"      {m}")

    # ---- PART 2: the digest ----
    dig: list[str] = []
    life: dict[str, int] = {}
    poison: dict[str, int] = {}
    zones_by_turn: dict[int, list[dict]] = {}
    for z in zones:
        zones_by_turn.setdefault(z.get("turn"), []).append(z)
    for t in game.get("turns") or []:
        n = t.get("turn")
        casts, dmg, entered, left, control, elim = [], [], [], [], [], []
        pending_cast: dict[str, str] = {}
        step = "-"
        for e in t.get("events") or []:
            raw = e.get("raw", "")
            act = e.get("action")
            if act == "phase":
                s = step_of(raw)
                if s:
                    step = s
                continue
            if act == "stack_add":
                p = seat_prefix(raw, seats)
                if p and raw[len(p):].startswith(" cast "):
                    spell = raw[len(p) + 6:]
                    casts.append(f"{p}: {spell}")
                    pending_cast[re.split(r" targeting ", spell)[0].strip()] = p
            m = _LIFE.match(raw)
            if m:
                life[m.group("p")] = int(m.group("b"))
            m = _POISON.match(raw)
            if m and m.group("p") in seats:
                poison[m.group("p")] = poison.get(m.group("p"), 0) + int(m.group("n"))
            m = _DMG.match(raw)
            if m and act == "damage":
                tgt = m.group("tgt")
                as_poison = "(as poison counters)" in tgt
                tgt = tgt.replace("(as poison counters)", "").strip().rstrip(".")
                if tgt in seats:
                    kind = (m.group("kind") or "").strip() or "unspecified"
                    extra = ", as poison counters" if as_poison else ""
                    dmg.append(f"[{step}] {m.group('src')} -> {tgt}: {m.group('n')} ({kind}{extra})")
            if act == "game_outcome":
                elim.append(raw)
            else:
                p = seat_prefix(raw, seats)
                if p and re.match(r" (has lost|has conceded|concedes)\b", raw[len(p):]):
                    elim.append(raw)
            if not shim:
                m = _RESOLVE_CREATURE.match(raw) if act == "stack_resolve" else None
                if m:
                    nm = m.group("name").strip()
                    by = pending_cast.get(nm)
                    entered.append(f"[{step}] {nm} {m.group('p')}/{m.group('t')}"
                                   + (f" (cast by {by})" if by else ""))
                m = _TOKEN_BURST.search(raw)
                if m:
                    entered.append(f"[{step}] {raw.split(' creates ')[0]} creates {m.group('n')} "
                                   f"{m.group('p')}/{m.group('t')} {m.group('desc')} token(s)")
                m = _EXIT.match(raw) if act == "zone_change" else None
                if m:
                    c = is_creature_name(m.group("card"))
                    if c is True:
                        left.append(f"[{step}] {m.group('card')} -> {m.group('to')}")
                    elif c is None:
                        left.append(f"[{step}] {m.group('card')} -> {m.group('to')} "
                                    f"(type unknown; may not be a creature)")
        if shim:
            for z in zones_by_turn.get(n, []):
                frm, to = z.get("from"), z.get("to")
                if frm == to == "Battlefield":
                    if z.get("fromPlayer") != z.get("toPlayer"):
                        is_c, label = creature_info_shim(z)
                        if is_c is not False:
                            control.append(f"{label} #{z.get('cardId')}: {z.get('fromPlayer')} -> {z.get('toPlayer')}")
                    continue
                if to != "Battlefield" and frm != "Battlefield":
                    continue
                is_c, label = creature_info_shim(z)
                if is_c is False:
                    continue
                st = _ZONE_STEPS.get(z.get("phase") or "", "")
                where = f"[{st}] " if st else ""
                if to == "Battlefield":
                    who = z.get("toPlayer") or "?"
                    src = f" from {frm}" if frm and frm not in ("Stack",) else ""
                    if frm in (None, "", "None"):
                        src = " (created)"
                    entered.append(f"{where}{label} #{z.get('cardId')} [{who}]{src}")
                else:
                    who = z.get("fromPlayer") or "?"
                    left.append(f"{where}{label} #{z.get('cardId')} [{who}] -> {to}")

        dig.append("")
        dig.append(f"--- Turn {n} | active player: {t.get('active_player')} ---")
        dig.append("Spells cast: " + ("none" if not casts else ""))
        dig.extend(f"  {c}" for c in casts)
        dig.append("Damage to players: " + ("none" if not dmg else ""))
        dig.extend(f"  {d}" for d in dmg)
        dig.append("Creatures entered: " + ("none logged" if not entered else ""))
        dig.extend(f"  {x}" for x in entered)
        dig.append("Creatures left the battlefield: " + ("none logged" if not left else ""))
        dig.extend(f"  {x}" for x in left)
        if control:
            dig.append("Creatures changed control:")
            dig.extend(f"  {x}" for x in control)
        dig.append("Life at end of turn (as last logged): " + "; ".join(
            f"{s} {life[s]}" if s in life else f"{s} (no change logged yet)" for s in seats))
        if poison:
            dig.append("Poison at end of turn (summed from Forge's 'receives N poison counter' lines): "
                       + "; ".join(f"{s} {poison[s]}" for s in seats if poison.get(s)))
        if elim:
            dig.append("Eliminations and outcome, exactly as Forge prints them:")
            dig.extend(f"  {x}" for x in elim)

    # ---- header ----
    agent = run_meta.get("agent") or "stock Forge"
    w("KNOCKOUT AND TURNING-POINT AUDIT: EVIDENCE FILE")
    w(f"Game: {key}")
    w("Seats, exactly as Forge prints them: " + " | ".join(seats))
    w(f"Turning point requested: {'yes' if tp_requested else 'no'}")
    if shim and typed:
        w("Record: Forge's log plus Forge's own zone records. The digest's creature lists are READ "
          "from those zone records: every creature moving onto or off the battlefield, with its "
          "types and power/toughness as of the move (#n is Forge's card id). P/T changes while a "
          "creature stays on the battlefield are not re-read.")
    elif shim:
        w("Record: Forge's log plus Forge's own zone records from an early logger version that did "
          "not record card types or P/T. The digest's creature lists come from those zone records, "
          "typed with the Scryfall card list (printed P/T). Tokens' types were not recorded, so "
          "tokens are listed as such; cards whose type is unknown are marked.")
    else:
        w("Record: Forge's text log only. Forge's text log does NOT record cards entering the "
          "battlefield, so the digest's 'entered' lists hold only creature spells that resolved and "
          "tokens the log narrates being created; creatures or tokens put onto the battlefield any "
          "other way appear only when they act or leave. Exits come from Forge's 'put into ... from "
          "Battlefield' lines, typed with the Scryfall card list; untyped ones are marked.")
    w(f"Pilot as recorded: {agent}.")
    if drop_mana:
        w(f"Dropped: {dropped} pure mana lines (\"... Add {{G}}.\") to keep this file near 250 KB. "
          "Nothing else was dropped.")
    else:
        w("Dropped: nothing.")
    w("Forge's standalone step lines (\"X's Upkeep step\") are not printed as lines of their own; "
      "every event line starts with the step it happened in, in brackets. Forge's end-of-game "
      "outcome block is marked [Game over].")
    w("Turn numbers: the headers use Forge's game-turn counter. Forge's end-of-game outcome block "
      "starts with a 'Turn N' line of its own on a different counter; ignore it and use the headers. "
      "Forge prints the outcome lines for every player at the very end of the game, so their "
      "position does not date a knockout.")
    w("")
    w("=" * 78)
    w("PART 1: FORGE'S LOG, IN ORDER")
    w("=" * 78)
    out.extend(log)
    w("")
    w("=" * 78)
    w("PART 2: PER-TURN DIGEST (computed mechanically from the records above; the log is authoritative)")
    w("=" * 78)
    out.extend(dig)
    text = "\n".join(out) + "\n"
    return text, len(text.encode("utf-8")), dropped


def main(argv: list[str]) -> int:
    sample_p, runs_dir, out_dir = (Path(a) for a in argv[:3])
    sample = json.loads(sample_p.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    by_label = {lab: v["file"] for lab, v in sample["files"].items()}
    loaded: dict[str, dict] = {}
    report = {}
    for key in sample["reading_set"]:
        info = sample["games"][key]
        lab = info["run"]
        if lab not in loaded:
            loaded[lab] = json.loads((runs_dir / by_label[lab]).read_text(encoding="utf-8"))
        data = loaded[lab]
        game = data["games"][info["n"] - 1]
        text, size, dropped = build_game(key, game, data.get("meta") or {},
                                         info["turning_point_requested"], drop_mana=False)
        if size > SIZE_LIMIT:
            text, size, dropped = build_game(key, game, data.get("meta") or {},
                                             info["turning_point_requested"], drop_mana=True)
        p = out_dir / f"{key}.txt"
        p.write_text(text, encoding="utf-8")
        report[key] = {"file": str(p), "bytes": size, "mana_lines_dropped": dropped}
        print(f"{key}: {size / 1024:.0f} KB, mana lines dropped: {dropped}")
    # Beside the evidence folder, not in it: readers get the evidence files only.
    (out_dir.parent / "evidence_build_report.json").write_text(json.dumps(report, indent=1),
                                                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
