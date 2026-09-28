#!/usr/bin/env python3
"""Commander names for a run, read from each deck's own [Commander] section.

Why (repair plan WS11 task 6, UX review problem 5): the front end guessed a
deck's commander by matching the deck name's first word against the spells
it cast, so "Skrat's Revenge" and "Nekusar Punisher" got no avatar and
"Kess, Reanimator" was shortened to "Kess,". The engine already has the
answer in the .dck file the run was played with; this module reads it and
nothing else. Never a guess: a deck whose file cannot be found has no
commanders here, and the caller shows the deck name alone.

Rules:
  - The .dck is read the way Forge 2.0.13's CardPool reads it (the same rules
    run_sim._dck_info uses): an optional leading count, "#" and ";" comment
    lines, and the "|SET|art" printing suffix dropped. utf-8-sig, so a byte
    order mark cannot hide the [metadata] Name=.
  - Partners and backgrounds: every [Commander] line, in file order.
  - A "Front // Back" name becomes the name Forge loads and logs, by
    convert_decklist.forge_name (the rule every import applies): the front
    face of a transform, modal, battle, adventure or flip card, the joined
    name of a split card. A pre-fix import can still hold the joined DFC
    name ("Ral, Monsoon Mage // Ral, Leyline Prodigy"); when neither the
    Forge index nor the card cache knows it, the front face is shown, since
    no split card can be a commander.
  - Keyed by the deck's Name=, which is the name Forge seats the deck under
    (player keys are "Ai(n)-<Name>"), so the front end can look a seat's
    commanders up without parsing paths.

Stdlib only. Deck files are found through mtg_engine._find_deck (imported
first, then bundled; CLAUDE.md gotcha 9), never a bare path.
"""
from __future__ import annotations

import re
from pathlib import Path

_COUNT = re.compile(r"^(?:\d+\s+)?(.+?)\s*$")
_AUTO = object()   # "the machine's own": the Forge index, the card cache


def display_name(name: str, index=_AUTO, card_facts=_AUTO) -> str:
    """The name to show for one [Commander] entry (see module docstring).

    `index` / `card_facts` default to the machine's Forge index and the card
    cache (no fetch), as convert_decklist does. Tests pass their own; index
    None means "as if no index were built", as in convert_decklist."""
    n = (name or "").split("|", 1)[0].strip()
    if " // " not in n:
        return n
    import convert_decklist as cd  # lazy: the name path must not load it
    facts_of = cd._cached_facts if card_facts is _AUTO else card_facts
    out = cd.forge_name(n, index=cd._AUTO if index is _AUTO else index,
                        card_facts=facts_of)
    if " // " not in out:
        return out
    facts = facts_of([n]) or {}
    if (facts.get(n) or {}).get("layout") in cd.SPLIT_LAYOUTS:
        return out
    return out.split(" // ", 1)[0].strip()


def dck_identity(path: Path, index=_AUTO, card_facts=_AUTO) -> dict:
    """{"name": Name=, "commanders": [display names]} for one .dck file.
    An unreadable file gives the file stem and no commanders."""
    info = {"name": Path(path).stem, "commanders": []}
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return info
    section = ""
    raw: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if section == "metadata" and line.lower().startswith("name="):
            info["name"] = line.split("=", 1)[1].strip() or info["name"]
            continue
        if section != "commander" or not line or line[0] in "#;":
            continue
        m = _COUNT.match(line)
        if m:
            nm = m.group(1).split("|", 1)[0].strip()
            if nm:
                raw.append(nm)
    seen: set[str] = set()
    for nm in raw:
        shown = display_name(nm, index=index, card_facts=card_facts)
        if shown and shown not in seen:
            seen.add(shown)
            info["commanders"].append(shown)
    return info


def _find(filename: str):
    from mtg_engine import _find_deck  # noqa: PLC0415  (lazy; CLAUDE.md gotcha 9)
    return _find_deck(filename)


def lookup(deck_paths: list, find=None) -> tuple[dict[str, list[str]], list[str]]:
    """({deck Name=: [commanders]}, [deck files not found]) for meta.decks.

    meta.decks holds the paths the run was played with, which are container
    paths ("/data/decks/skrat_s_revenge_239c6293.dck"); only the basename is
    looked up. A deck whose file is gone (deleted after the run) is reported,
    not guessed."""
    find = find or _find
    out: dict[str, list[str]] = {}
    missing: list[str] = []
    for raw in deck_paths or []:
        stem = Path(str(raw)).name
        path = find(stem)
        if path is None:
            missing.append(stem)
            continue
        info = dck_identity(path)
        out[info["name"]] = info["commanders"]
    return out, missing


def of_run(meta: dict, find=None) -> dict[str, list[str]]:
    """The commanders a result names: meta.commanders when run_sim or readapt
    wrote them, else read now from the deck files (an old run nobody has
    backfilled). A deck missing from both simply has no entry."""
    stored = (meta or {}).get("commanders")
    if isinstance(stored, dict) and stored:
        return {str(k): [str(c) for c in (v or [])] for k, v in stored.items()}
    try:
        found, _missing = lookup((meta or {}).get("decks") or [], find=find)
    except Exception:  # noqa: BLE001 - a label must never take a payload down
        return {}
    return found
