#!/usr/bin/env python3
"""Build Forge .dck files (with partner-commander support) from plain lists.

Input format (one file per deck):
  COMMANDER: Name            (one or two lines)
  1 Card Name
  6 Mountain

Differences from engine/convert_decklist.py, and why this exists:
  - two COMMANDER lines (partners) are written as two [Commander] entries,
    which the engine converter does not support
  - a name Forge does not know stops the deck from being written (Forge
    silently drops unknown cards) unless it has a recorded substitute
    (RECORDED_SUBSTITUTES below, or --map)

Names are normalised EXACTLY as engine/convert_decklist.py does (repair plan
WS4 tasks 2 and 6): every name goes through engine/forge_index.py's
ForgeIndex.resolve(), built from Forge's own card scripts, because Forge
decides what Forge loads. A transform, modal, battle, adventure or flip card
pasted as "Front // Back" becomes its front face; a split card keeps
"A // B"; accents and case follow Forge's spelling.

This used to resolve names by matching script FILE names, which went wrong
twice (2026-09 diagnosis, RC9):
  - every double-faced card has a front_back.txt script, which looks exactly
    like a split card's, so "Front // Back" was written unchanged. Forge
    2.0.13 refuses that spelling ("An unsupported card was requested", on
    stderr only) and plays on without the card: 48 slots in 23 of the 32
    decks, including both Ral commanders;
  - a bare name matched any script that started with it, so "_____ Goblin"
    (Unfinity, not in Forge 2.0.13; its name folds to "goblin") was accepted
    because goblin_*.txt scripts exist.

Usage:
  py make_dck.py deck.txt [deck2.txt ...] --out-dir ./dck
  py make_dck.py ../decks/*/*.txt --in-place     # regenerate every study deck
  py make_dck.py deck.txt --allow-substitute      # unknown card -> basic land
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "engine"))
import forge_index  # noqa: E402  (engine/ is stdlib only; this is its resolver)

CARDSFOLDER = Path.home() / "forge/res/cardsfolder/cardsfolder.zip"

# Published cards Forge 2.0.13 does not have, and the substitute each deck
# plays instead. Every entry is recorded in tools/FETCH_NOTES.md and in the
# deck's manifest.json note. Applied only to a name Forge cannot load; --map
# adds to or overrides this table.
RECORDED_SUBSTITUTES = {
    # Magda pilot (n7WpsqsZtdQ/magda) and natalie_magda (sZA0KqXCGrY): post-2.0.13
    # dwarves -> Forge dwarves, which keeps the Dwarf count Magda counts.
    "Fíli and Kíli, Joyous": "Seven Dwarves",
    "Dwarven Mauler": "Dwarven Warriors",
    "Óin the Brave": "Dwarven Pony",
    # Plain land slots.
    "Dragon-Cursed Halls": "Mountain",     # magda
    "Gleaming Splendor": "Island",         # dallas_bluefarm (CxKMqO36DdM)
    # joseph_ral (both pods). A sticker card: {2}{R} 2/2 whose ETB adds {R} per
    # unique vowel on the sticker. Forge has no stickers and no such card; the
    # old file-name matcher accepted it by prefix, so Forge silently dropped
    # it. Priest of Urabrask ({2}{R} creature, ETB add {R}{R}{R}) is the same
    # slot: a three-mana creature ritual. Added 2026-09-27 (repair plan WS4
    # task 6).
    "_____ Goblin": "Priest of Urabrask",
}


def load_index(cardsfolder: Path) -> forge_index.ForgeIndex:
    """The Forge index for this Forge install.

    Built in memory from cardsfolder.zip (about 1.5 s) when it exists, so the
    decks are checked against exactly the scripts that Forge will load;
    otherwise the index engine/forge_index.py built for this machine."""
    if cardsfolder.exists():
        cards, flags, _tutors, counts = forge_index.build_data(cardsfolder)
        # <forge>/res/cardsfolder/cardsfolder.zip: the version is on the jar
        # in <forge>, not on the zip.
        home = cardsfolder.parents[2] if cardsfolder.suffix == ".zip" else cardsfolder.parents[1]
        meta = {"forge_version": forge_index.forge_version(home, cardsfolder),
                "source": str(cardsfolder), "counts": counts}
        return forge_index.ForgeIndex(cardsfolder, meta, cards, flags)
    idx = forge_index.load_index()
    if idx is None:
        sys.exit(f"no Forge card scripts at {cardsfolder} and no built index; pass "
                 f"--cardsfolder, or run: py engine/forge_index.py build")
    return idx


def resolve(name: str, index: forge_index.ForgeIndex) -> str | None:
    """The name Forge loads this card by, or None when Forge does not know it.
    The same resolver engine/convert_decklist.py uses."""
    return index.resolve(name)


def parse(path: Path) -> tuple[list[str], list[tuple[int, str]]]:
    commanders: list[str] = []
    main: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if raw.upper().startswith("COMMANDER:"):
            commanders.append(raw.split(":", 1)[1].strip())
            continue
        m = re.match(r"^(\d+)\s+(.+)$", raw)
        if not m:
            sys.exit(f"{path.name}: unparseable line: {raw}")
        main.append((int(m.group(1)), m.group(2).strip()))
    if not commanders:
        sys.exit(f"{path.name}: no COMMANDER: line")
    return commanders, main


def convert(path: Path, index: forge_index.ForgeIndex, allow_substitute: bool,
            submap: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """(.dck text, problems). A problem ending "(mapped)" was substituted from
    the recorded table or --map; any other problem is an unsupported card."""
    submap = {**RECORDED_SUBSTITUTES, **(submap or {})}
    commanders, main = parse(path)

    renamed: list[str] = []
    out_cmd: list[str] = []
    for c in commanders:
        r = resolve(c, index)
        if r is None:
            sys.exit(f"{path.name}: commander not in Forge card DB: {c}")
        if r != c:
            renamed.append(f"{c} -> {r}")
        out_cmd.append(r)

    problems: list[str] = []
    out_main: list[tuple[int, str]] = []
    basic = "Mountain" if "magda" in path.stem else "Forest"
    for count, name in main:
        r = resolve(name, index)
        if r is None:
            if name in submap:
                repl = resolve(submap[name], index)
                if repl is None:
                    sys.exit(f"{path.name}: mapped replacement also unsupported: {submap[name]}")
                problems.append(f"{name} -> {repl} (mapped)")
                out_main.append((count, repl))
                continue
            problems.append(name)
            if allow_substitute:
                out_main.append((count, basic))
            continue
        if r != name:
            renamed.append(f"{name} -> {r}")
        out_main.append((count, r))

    total = sum(c for c, _ in out_main) + len(out_cmd)
    lines = ["[metadata]", f"Name={path.stem}", "Deck Type=Commander",
             "[Commander]"] + [f"1 {c}" for c in out_cmd] + ["[Main]"] + [
             f"{c} {n}" for c, n in out_main]
    unsupported = [p for p in problems if not p.endswith("(mapped)")]
    print(f"{path.parent.name}/{path.stem}: {total} cards total, "
          f"{len(renamed)} renamed to Forge's name, "
          f"{len(problems) - len(unsupported)} substituted (recorded), "
          f"{len(unsupported)} unsupported"
          + (f" -> substituted with {basic}" if unsupported and allow_substitute else ""))
    for r in renamed:
        print(f"  RENAMED: {r}")
    for p in problems:
        print(f"  {'SUBSTITUTED' if p.endswith('(mapped)') else 'UNSUPPORTED'}: {p}")
    # Forge's AI never casts a card scripted AI:RemoveDeck:All (Winter, Cynical
    # Opportunist). For a commander that makes the seat a test of nothing.
    flagged = [c for c in out_cmd
               if "spell" in ((index.flag(c) or {}).get("kinds") or [])]
    if flagged:
        print(f"  NOTE: Forge's AI doesn't cast these cards on its own: "
              f"{', '.join(flagged)} (commander)")
    return "\n".join(lines) + "\n", problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("decks", nargs="+")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--in-place", action="store_true",
                    help="write each deck to dck/<name>.dck beside its .txt "
                         "(the study layout: decks/<video>/dck/); ignores --out-dir")
    ap.add_argument("--allow-substitute", action="store_true")
    ap.add_argument("--map", action="append", default=[], metavar="ORIG=REPL",
                    help="explicit substitution for an unsupported card; adds to "
                         "RECORDED_SUBSTITUTES and takes precedence over the "
                         "basic-land fallback")
    ap.add_argument("--cardsfolder", default=str(CARDSFOLDER))
    a = ap.parse_args()

    index = load_index(Path(a.cardsfolder).expanduser())
    print(f"Forge index: {index.version} ({len(index.cards)} cards, "
          f"from {index.meta.get('source') or index.path})")
    submap = dict(m.split("=", 1) for m in a.map)
    failed = False
    for d in a.decks:
        p = Path(d)
        content, problems = convert(p, index, a.allow_substitute, submap)
        unmapped = [x for x in problems if not x.endswith("(mapped)")]
        if unmapped and not a.allow_substitute:
            failed = True
            continue
        out_dir = p.parent / "dck" if a.in_place else Path(a.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        # LF on every OS: .dck is stored byte-for-byte (.gitattributes -text),
        # and Python 3.8's write_text has no newline argument.
        with open(out_dir / f"{p.stem}.dck", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
    if failed:
        sys.exit("some decks had unsupported cards; add a recorded substitute "
                 "(--map ORIG=REPL) or rerun with --allow-substitute to swap them "
                 "for basics (listed above)")


if __name__ == "__main__":
    main()
