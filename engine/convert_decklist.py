#!/usr/bin/env python3
"""Convert decklist exports (Moxfield/Arena/MTGO/plain text) to Forge .dck files.

Handles entries like:
  1 Inspirit, Flagship Vessel (EOC) 2 F
  3 Island (EOE) 269
  1 Flux Channeler (PLST) WAR-52
  1 Tekuthal, Inquiry Dominus (PONE) 71p
  1 Kilo, Apogee Mind          (plain lines, no set code — MTGO exports)
  3x Island

Rules applied:
  - set codes, collector numbers, and foil markers are stripped (Forge wants names)
  - every name becomes the name FORGE loads (repair plan WS4 task 2): a
    transform, modal, battle, adventure or flip card pasted as "Front // Back"
    becomes its front face, because Forge 2.0.13 refuses the joined name and
    says so only on stderr (both Ral decks were simmed with no commander that
    way); a split card keeps "A // B", which is how Forge names it
  - first entry is treated as the commander unless --commander is given
  - SIDEBOARD: sections are dropped (Commander has no sideboard)
  - reports main-deck count and duplicate non-basics so you can fix before simming
  - pre-check (WS4 task 3): the report carries `warnings`, a list of
    {"kind": "unknown_card" | "ai_wont_cast" | "index_missing", "cards", "message"}.
    A commander Forge does not know rejects the deck.

Where the names come from: Forge's own card index (engine/forge_index.py),
because Forge decides what Forge loads. When the index is not built, a
"Front // Back" name falls back to the Scryfall `layout` stored in the card
cache (cache only, no fetch); failing both it is left as pasted and the
index_missing warning says so.

Usage:
  python3 convert_decklist.py input.txt --name "My Deck" --out decks/my_deck.dck
  python3 convert_decklist.py input.txt --name "My Deck" --commander "Kilo, Apogee Mind"
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

BASICS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes",
          "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
          "Snow-Covered Mountain", "Snow-Covered Forest"}

# count, name, (SET) collector-number, optional foil flag — tolerant of
# multi-entry lines (Moxfield single-line exports)
ENTRY = re.compile(
    r"(\d+)\s+"                       # count
    r"([^()]+?)\s+"                   # card name (no parens in MTG card names)
    r"\(([A-Z0-9]{2,6})\)\s+"         # (SET)
    r"([A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)"  # collector number (WAR-52, 118p, 351)
    r"(\s+F\b)?"                      # optional foil marker
)

# Plain "1 Card Name" / "3x Island" line, MTGO-style. Applied per line and only
# when ENTRY found nothing on that line, so multi-entry single-line Moxfield
# exports (which always carry set codes) still split on each "(SET) num" anchor
# rather than being swallowed whole. The whole remainder is ONE name — card
# names contain commas ("Kilo, Apogee Mind"), so a plain line is never split.
PLAIN = re.compile(r"^(\d+)\s*[xX]?\s+(.+?)\s*$")
# Trailing junk stripped off plain names — keep in lockstep with parseList()
# in web/app/import/page.tsx, which runs the same two substitutions.
FOIL_TAIL = re.compile(r"\s*\*[A-Za-z]+\*\s*$")               # foil markers like *F*
SET_TAIL = re.compile(r"\s*\([A-Za-z0-9]{2,6}\)\s*[\w★-]*\s*$")  # (SET) 123p


def _line_entries(line: str) -> list[tuple[int, str]]:
    hits = [(int(m.group(1)), m.group(2).strip()) for m in ENTRY.finditer(line)]
    if hits:
        return hits
    m = PLAIN.match(line)
    if not m:
        return []
    name = SET_TAIL.sub("", FOIL_TAIL.sub("", m.group(2))).strip()
    return [(int(m.group(1)), name)] if name else []


def parse(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (main_entries, sideboard_entries) as (count, name) lists."""
    if "SIDEBOARD:" in text:
        main_text, side_text = text.split("SIDEBOARD:", 1)
    else:
        main_text, side_text = text, ""
    def entries(t: str) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for line in t.splitlines():
            line = line.strip()
            # Comment lines match PLAIN ("# 85 more cards…" would parse as
            # 85 "more cards…"), so they are skipped exactly like the client.
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            out.extend(_line_entries(line))
        return out
    return entries(main_text), entries(side_text)


# Scryfall layouts whose "Front // Back" Forge loads by the front face. Only
# consulted when the Forge index is missing; the index is the authority.
FRONT_FACE_LAYOUTS = {"transform", "modal_dfc", "battle", "adventure", "flip", "meld",
                      "reversible_card"}
SPLIT_LAYOUTS = {"split"}

_AUTO = object()   # "load the Forge index yourself"


def _load_index():
    try:
        import forge_index
        return forge_index.load_index()
    except Exception as e:  # noqa: BLE001 — a missing or broken index skips checks
        print(f"convert_decklist: Forge index unavailable ({e})", file=sys.stderr)
        return None


def _cached_facts(names: list[str]) -> dict[str, dict]:
    """Scryfall facts from the card cache only: an import never fetches here."""
    try:
        import cards
        return cards.get_many(names, fetch=False)
    except Exception:  # noqa: BLE001
        return {}


def _join(names: list[str]) -> str:
    return ", ".join(names)


class _Names:
    """Pasted name -> the name Forge loads, remembering what it could not do."""

    def __init__(self, index, card_facts) -> None:
        self.index = index
        self.card_facts = card_facts
        self.unknown: list[str] = []       # Forge has no such card (index only)
        self.unresolved: list[str] = []    # "A // B" left as pasted (no index)
        self.renamed: list[dict] = []
        self._memo: dict[str, str] = {}
        self._facts: dict[str, dict] = {}

    def prime(self, names: list[str]) -> None:
        """One cache read for every "A // B" name, instead of one per name."""
        if self.index is None and self.card_facts is not None:
            slash = [n for n in names if " // " in n]
            self._facts = (self.card_facts(slash) or {}) if slash else {}

    def __call__(self, name: str) -> str:
        if name in self._memo:
            return self._memo[name]
        out = name
        if self.index is not None:
            forge = self.index.resolve(name)
            if forge is None:
                if name not in self.unknown:
                    self.unknown.append(name)
            else:
                out = forge
        elif " // " in name:
            layout = (self._facts.get(name) or {}).get("layout")
            if layout in FRONT_FACE_LAYOUTS:
                out = name.split(" // ", 1)[0].strip()
            elif layout not in SPLIT_LAYOUTS and name not in self.unresolved:
                self.unresolved.append(name)
        if out != name:
            self.renamed.append({"from": name, "to": out})
        self._memo[name] = out
        return out


def convert(text: str, deck_name: str, commander: str | None = None,
            index=_AUTO, card_facts=_cached_facts) -> tuple[str, dict]:
    """(.dck text, report). sys.exit()s on a hard failure, which POST /decks
    turns into {"ok": false, "error"}.

    `index` is a forge_index.ForgeIndex, None to run as if none were built, or
    omitted to load this machine's. `card_facts(names) -> {name: facts}` is the
    no-index fallback (the card cache, never the network)."""
    main, side = parse(text)
    if not main:
        sys.exit("no card entries recognized: is this a Moxfield/Arena export with (SET) codes?")

    idx = _load_index() if index is _AUTO else index
    names = _Names(idx, card_facts)
    names.prime([n for _, n in main] + ([commander] if commander else []))
    main = [(n, names(name)) for n, name in main]

    commander = names(commander) if commander is not None else main[0][1]
    if idx is not None and commander in names.unknown:
        sys.exit(f"Forge doesn't know these cards: {commander}. That is the commander, "
                 f"so this deck can't be simulated. Check the spelling, or choose "
                 f"another commander.")
    # remove ONE copy of the commander from main
    out_main: list[tuple[int, str]] = []
    removed = False
    for n, name in main:
        if not removed and name.lower() == commander.lower():
            removed = True
            if n > 1:
                out_main.append((n - 1, name))
            continue
        out_main.append((n, name))
    if not removed:
        sys.exit(f"commander '{commander}' not found in list")

    total = sum(n for n, _ in out_main)
    dupes = [name for name, c in Counter(
        name for n, name in out_main for _ in range(n) if name not in BASICS
    ).items() if c > 1]

    lines = ["[metadata]", f"Name={deck_name}", "Deck Type=Commander",
             "[Commander]", f"1 {commander}", "[Main]"]
    lines += [f"{n} {name}" for n, name in out_main]

    report = {"deck": deck_name, "commander": commander, "main_count": total,
              "expected": 99, "ok": total == 99, "duplicates_nonbasic": dupes,
              "sideboard_dropped": len(side),
              "renamed": names.renamed,
              "forge_index": getattr(idx, "version", None),
              "warnings": _warnings(idx, names, commander, [name for _, name in out_main])}
    return "\n".join(lines) + "\n", report


def _warnings(idx, names: _Names, commander: str, main_names: list[str]) -> list[dict]:
    """The import pre-check (WS4 task 3), in the shape the import page renders."""
    out: list[dict] = []
    if idx is None:
        msg = ("Forge's card list isn't available yet, so two checks were skipped: "
               "cards Forge doesn't know, and cards its AI doesn't cast on its own.")
        if names.unresolved:
            msg += (f" These double-faced names were left as pasted and may not load: "
                    f"{_join(names.unresolved)}.")
        out.append({"kind": "index_missing", "cards": list(names.unresolved), "message": msg})
        return out
    if names.unknown:
        out.append({"kind": "unknown_card", "cards": list(names.unknown),
                    "message": f"Forge doesn't know these cards: {_join(names.unknown)}. "
                               f"The simulation will play without them."})
    # Forge's AI drops every AI:RemoveDeck:All card from its choices. Lands are
    # still played, and a flagged counterspell is still cast by Forge's
    # counterspell pre-pass, so only a flagged SPELL gets this warning. The
    # wording is "doesn't cast on its own" (owner decision 2026-09-27), not
    # "won't cast": the plan agent does cast some flagged spells itself (line
    # pieces and tutors), and an effect can still cast one for free.
    wont: list[str] = []
    for nm in [commander] + main_names:
        flag = idx.flag(nm)
        if flag and "spell" in flag.get("kinds", []) and not flag.get("land") \
                and nm not in wont:
            wont.append(nm)
    if wont:
        msg = f"Forge's AI doesn't cast these cards on its own: {_join(wont)}."
        if commander in wont:
            msg += " This includes your commander."
        out.append({"kind": "ai_wont_cast", "cards": wont, "message": msg})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", help="text file containing the exported list")
    p.add_argument("--name", required=True)
    p.add_argument("--commander", default=None, help="default: first entry in the list")
    p.add_argument("--out", default=None, help="default: decks/<name>.dck")
    a = p.parse_args()

    text = Path(a.input).read_text(encoding="utf-8")
    content, report = convert(text, a.name, a.commander)
    out = Path(a.out) if a.out else Path(__file__).parent / "decks" / (
        re.sub(r"[^a-z0-9]+", "_", a.name.lower()).strip("_") + ".dck")
    out.write_text(content, encoding="utf-8")
    print(f"wrote {out}")
    print(report)
    for w in report.get("warnings", []):
        print(f"WARNING [{w['kind']}]: {w['message']}", file=sys.stderr)
    if not report["ok"]:
        print(f"WARNING: main deck is {report['main_count']} cards, expected 99", file=sys.stderr)


if __name__ == "__main__":
    main()
