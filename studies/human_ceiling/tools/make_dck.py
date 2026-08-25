#!/usr/bin/env python3
"""Build Forge .dck files (with partner-commander support) from plain lists.

Input format (one file per deck):
  COMMANDER: Name            (one or two lines)
  1 Card Name
  6 Mountain

Differences from engine/convert_decklist.py, and why this exists:
  - two COMMANDER lines (partners) are written as two [Commander] entries,
    which the engine converter does not support
  - every name is checked against the local Forge card database
    (cardsfolder.zip); names Forge does not know are reported and the deck
    is NOT written, because Forge silently drops unknown cards
  - double-faced cards are written as the front face (how Forge registers
    them); true split cards ("Dead // Gone") keep the full name

Usage:
  python3 make_dck.py deck.txt [deck2.txt ...] --out-dir ./dck
  python3 make_dck.py deck.txt --allow-substitute   # unknown card -> basic land
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

CARDSFOLDER = Path.home() / "forge/res/cardsfolder/cardsfolder.zip"


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("'", "")          # Forge drops apostrophes: urzas_saga.txt
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def load_index(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path) as z:
        return {Path(n).stem for n in z.namelist() if n.endswith(".txt")}


def resolve(name: str, index: set[str]) -> str | None:
    """Return the name Forge knows this card by, or None if unsupported.

    Forge names multi-face card files front_back.txt (e.g.
    turntimber_symbiosis_turntimber_serpentine_wood.txt), so a bare front-face
    name (how TCGplayer's API reports DFCs) is matched by prefix."""
    if " // " in name:
        front, back = [p.strip() for p in name.split(" // ", 1)]
        if _norm(f"{front}_{back}") in index or _norm(name) in index:
            return name          # multi-face file, full name loads fine
        if _norm(front) in index:
            return front         # front face has its own file
        return None
    if _norm(name) in index:
        return name
    prefix = _norm(name) + "_"
    if any(stem.startswith(prefix) for stem in index):
        return name              # front face of a multi-face file
    return None


def convert(path: Path, index: set[str], allow_substitute: bool,
            submap: dict[str, str] | None = None) -> tuple[str, list[str]]:
    submap = submap or {}
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

    problems: list[str] = []
    out_cmd: list[str] = []
    for c in commanders:
        r = resolve(c, index)
        if r is None:
            sys.exit(f"{path.name}: commander not in Forge card DB: {c}")
        out_cmd.append(r)

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
        out_main.append((count, r))

    total = sum(c for c, _ in out_main) + len(out_cmd)
    lines = ["[metadata]", f"Name={path.stem}", "Deck Type=Commander",
             "[Commander]"] + [f"1 {c}" for c in out_cmd] + ["[Main]"] + [
             f"{c} {n}" for c, n in out_main]
    print(f"{path.stem}: {total} cards total, {len(problems)} unsupported"
          + (f" -> substituted with {basic}" if problems and allow_substitute else ""))
    for p in problems:
        print(f"  UNSUPPORTED: {p}")
    return "\n".join(lines) + "\n", problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("decks", nargs="+")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--allow-substitute", action="store_true")
    ap.add_argument("--map", action="append", default=[], metavar="ORIG=REPL",
                    help="explicit substitution for an unsupported card; "
                         "takes precedence over the basic-land fallback")
    ap.add_argument("--cardsfolder", default=str(CARDSFOLDER))
    a = ap.parse_args()

    index = load_index(Path(a.cardsfolder).expanduser())
    submap = dict(m.split("=", 1) for m in a.map)
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for d in a.decks:
        p = Path(d)
        content, problems = convert(p, index, a.allow_substitute, submap)
        unmapped = [x for x in problems if not x.endswith("(mapped)")]
        if unmapped and not a.allow_substitute:
            failed = True
            continue
        (out_dir / f"{p.stem}.dck").write_text(content, encoding="utf-8")
    if failed:
        sys.exit("some decks had unsupported cards; rerun with --allow-substitute "
                 "to swap them for basics (recorded above)")


if __name__ == "__main__":
    main()
