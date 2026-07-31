#!/usr/bin/env python3
"""Convert simlab-forge-shim JSON-lines output into the standard result schema.

The shim (separate GPL repo; see CLAUDE.md "Legal posture") emits typed
GameLog entries whose `message` fields are the exact texts Forge prints in
`sim` mode, minus the `<Caption>: ` prefix. This module rebuilds that
pseudo-stdout and reuses forge_log_adapter.parse_forge_log verbatim, so the
downstream schema (games/turns/events/summary) is identical to a stock run.

What the shim adds on top — and what this module preserves — is the `zone`
records from Forge's event bus: EVERY card movement including battlefield
ENTRIES, which the stdout log never contains (the measured 86.5% board
reconstruction ceiling). They are attached per game under `"zones"`, an
additive key no existing consumer reads yet.

Zero dependencies (stdlib only).
"""
from __future__ import annotations

import json
import sys

from forge_log_adapter import parse_forge_log

# GameLogEntryType enum name -> the caption Forge prints in sim mode
# (forge_log_adapter's CAPTION_TO_ACTION is keyed on the captions).
TYPE_TO_CAPTION = {
    "TURN": "Turn",
    "PHASE": "Phase",
    "MULLIGAN": "Mulligan",
    "ANTE": "Ante",
    "DRAFT": "Draft",
    "ZONE_CHANGE": "Zone Change",
    "PLAYER_CONTROL": "Player Control",
    "DAMAGE": "Damage",
    "LIFE": "Life",
    "LAND": "Land",
    "DISCARD": "Discard",
    "COMBAT": "Combat",
    "INFORMATION": "Information",
    "STACK_RESOLVE": "Resolve Stack",
    "STACK_ADD": "Add To Stack",
    "EFFECT_REPLACED": "Replacement Effect",
    "MANA": "Mana",
    "GAME_OUTCOME": "Game Outcome",
    "MATCH_RESULTS": "Match Result",
}


def parse_shim_jsonl(text: str, source: str = "simlab-forge-shim") -> dict:
    """Parse one shim invocation's JSONL (may contain several games)."""
    meta_rec: dict = {}
    entries: dict[int, list[dict]] = {}
    results: dict[int, dict] = {}
    zones: dict[int, list[dict]] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue  # defensive: a stray non-JSON line loses one record, not the run
        rec = r.get("rec")
        if rec == "meta":
            meta_rec = r
        elif rec == "entry":
            entries.setdefault(r["game"], []).append(r)
        elif rec == "result":
            results[r["game"]] = r
        elif rec == "zone":
            zones.setdefault(r["game"], []).append(
                {k: r[k] for k in ("turn", "card", "cardId", "from", "to",
                                   "fromPlayer", "toPlayer") if k in r})

    # Rebuild the stdout Forge's sim mode would have printed.
    lines: list[str] = []
    game_order = sorted(entries.keys() | results.keys())
    for g in game_order:
        for e in entries.get(g, []):
            caption = TYPE_TO_CAPTION.get(e.get("type", ""))
            if caption:
                lines.append(f"{caption}: {e.get('message', '')}")
        res = results.get(g)
        if res:
            ms = res.get("ms", 0)
            if res.get("draw") or not res.get("winner"):
                lines.append(f"Game Result: Game {g + 1} ended in a Draw! Took {ms} ms.")
            else:
                lines.append(f"Game Result: Game {g + 1} ended in {ms} ms. "
                             f"{res['winner']} has won!")

    result = parse_forge_log("\n".join(lines), source=source)
    result["meta"]["agent"] = f"simlab-forge-shim/{meta_rec.get('shim', '?')}"

    # Attach ground-truth zone movements per game (order matches game_order
    # because every shim game produces turn entries).
    for i, g in enumerate(game_order):
        if i < len(result["games"]):
            result["games"][i]["zones"] = zones.get(g, [])
    total_zones = sum(len(z) for z in zones.values())
    entries_bf = sum(1 for zz in zones.values() for z in zz if z.get("to") == "Battlefield")
    result["meta"]["zone_records"] = total_zones
    result["meta"]["battlefield_entries"] = entries_bf
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: shim_log_adapter.py <shim_out.jsonl> [out.json]", file=sys.stderr)
        sys.exit(1)
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    result = parse_shim_jsonl(text, source=sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None
    payload = json.dumps(result, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {out}: {result['summary']}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
