#!/usr/bin/env python3
"""Convert Moxfield/Arena-style decklist exports to Forge .dck files.

Handles entries like:
  1 Inspirit, Flagship Vessel (EOC) 2 F
  3 Island (EOE) 269
  1 Flux Channeler (PLST) WAR-52
  1 Tekuthal, Inquiry Dominus (PONE) 71p

Rules applied:
  - set codes, collector numbers, and foil markers are stripped (Forge wants names)
  - first entry is treated as the commander unless --commander is given
  - SIDEBOARD: sections are dropped (Commander has no sideboard)
  - reports main-deck count and duplicate non-basics so you can fix before simming

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


def parse(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (main_entries, sideboard_entries) as (count, name) lists."""
    if "SIDEBOARD:" in text:
        main_text, side_text = text.split("SIDEBOARD:", 1)
    else:
        main_text, side_text = text, ""
    def entries(t: str) -> list[tuple[int, str]]:
        return [(int(m.group(1)), m.group(2).strip()) for m in ENTRY.finditer(t)]
    return entries(main_text), entries(side_text)


def convert(text: str, deck_name: str, commander: str | None = None) -> tuple[str, dict]:
    main, side = parse(text)
    if not main:
        sys.exit("no card entries recognized — is this a Moxfield/Arena export with (SET) codes?")

    if commander is None:
        commander = main[0][1]
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
              "sideboard_dropped": len(side)}
    return "\n".join(lines) + "\n", report


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
    if not report["ok"]:
        print(f"WARNING: main deck is {report['main_count']} cards, expected 99", file=sys.stderr)


if __name__ == "__main__":
    main()
