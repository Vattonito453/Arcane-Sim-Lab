#!/usr/bin/env python3
"""The cards a deck carries that the simulation does not play as written.

Repair plan WS11 task 4 (the disclosure), WS4 (the load data) and WS6 task 4
(the product line): "Decks with an undisclosed dead card: all -> 0". Two
lists per deck, shown on the run page, the deck page and at import:

  could_not_load  cards Forge refused at load, so every game was played
                  without them. On a run this is Forge's own report, read
                  from its stderr (run_sim writes meta.unsupported_cards and
                  meta.unsupported_by_deck; basis "run"). A run older than
                  that check, a deck page and an import read it from the
                  Forge index instead: names Forge doesn't know, which it
                  refuses the same way (basis "index").
  ai_wont_play    cards scripted AI:RemoveDeck:All whose spell Forge's AI
                  doesn't cast on its own (the owner's wording, 2026-09-27).
                  ONE rule, the same one behind the import warning
                  (convert_decklist._warnings calls ai_skips): a flagged
                  nonland card whose flagged faces include a spell. A flagged
                  land is still played, and a flagged counterspell is still
                  cast by Forge's counterspell pre-pass, so neither is listed.
                  Sim Lab's pilot can cast some of these anyway (combo
                  pursuit, tutoring), and an effect can cast one for free.
                  Readmission (WS6, weeks 8-9) teaches the pilot the rest;
                  until then deck_telemetry and coach never call one "cold"
                  and never suggest cutting one, because a card the AI never
                  casts is not a cut candidate.

None means "cannot say" (no Forge index, or the deck file is gone), never
"none": the page says which. An empty list is a clean answer.

Where the data lives: the Forge index is generated at runtime from Forge's
own card scripts by the worker (engine/forge_index.py) into
$MTG_DATA_DIR/forge_index/<version>/ on the shared volume. The API image has
no Forge jar; it reads that volume. Nothing Forge-derived is committed.

Stdlib only. Deck files are found through mtg_engine._find_deck (imported
first, then bundled; CLAUDE.md gotcha 9), never a bare path.
"""
from __future__ import annotations

import re
from pathlib import Path

_AUTO = object()          # "load this machine's index / use _find_deck"
_COUNT = re.compile(r"^(?:\d+\s+)?(.+?)\s*$")
_IMPORT_HASH = re.compile(r"_[0-9a-f]{8}$")


# ------------------------------------------------------------------ rule --

def ai_skips(flag: dict | None) -> bool:
    """Forge's AI doesn't cast this card on its own. `flag` is the card's
    forge_index flags.json entry (None when it is not flagged)."""
    if not isinstance(flag, dict):
        return False
    return "spell" in (flag.get("kinds") or []) and not flag.get("land")


def _load_index(idx=_AUTO):
    if idx is not _AUTO:
        return idx
    try:
        import forge_index
        return forge_index.load_index()
    except Exception:  # noqa: BLE001 - a missing or broken index means "cannot say"
        return None


def _clean(name: str) -> str:
    """A .dck card name without Forge's "|SET|art" printing suffix."""
    return (name or "").split("|", 1)[0].strip()


def ai_wont_play(idx, names) -> list[str]:
    """The Forge names, in first-seen order, of the cards among `names` that
    Forge's AI doesn't cast on its own. A name Forge doesn't know is not
    listed here (it is in could_not_load instead)."""
    out: list[str] = []
    for n in names:
        forge = idx.resolve(_clean(n))
        if forge and forge not in out and ai_skips(idx.flag(forge)):
            out.append(forge)
    return out


def unknown_to_forge(idx, names) -> list[str]:
    """Names Forge doesn't know, as the deck spells them, first-seen order."""
    out: list[str] = []
    for n in names:
        c = _clean(n)
        if c and idx.resolve(c) is None and c not in out:
            out.append(c)
    return out


# ----------------------------------------------------------------- decks --

def parse_dck(text: str, default_name: str = "") -> tuple[str, list[str], list[str]]:
    """(Name=, commanders, main) from a .dck body, read the way Forge 2.0.13's
    CardPool reads one (as run_sim._dck_info and commanders.dck_identity do):
    an optional leading count, "#" and ";" comment lines, the "|SET|art"
    suffix dropped. Names are distinct and in file order."""
    name = default_name
    section = ""
    commanders: list[str] = []
    main: list[str] = []
    for line in (text or "").lstrip("﻿").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if section == "metadata" and line.lower().startswith("name="):
            name = line.split("=", 1)[1].strip() or name
            continue
        if not line or line[0] in "#;" or section not in ("commander", "main"):
            continue
        m = _COUNT.match(line)
        card = _clean(m.group(1)) if m else ""
        if not card:
            continue
        bucket = commanders if section == "commander" else main
        if card not in bucket:
            bucket.append(card)
    return name, commanders, main


def _read(path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except (OSError, TypeError):
        return None


def of_names(idx, commanders: list[str], main: list[str]) -> dict:
    """The two lists for one deck from the Forge index alone (a deck page,
    an import, or a run too old to carry Forge's own load report)."""
    if idx is None:
        return {"could_not_load": None, "load_basis": None,
                "ai_wont_play": None, "commander_ai_wont_play": []}
    everything = list(commanders) + list(main)
    wont = ai_wont_play(idx, everything)
    return {"could_not_load": unknown_to_forge(idx, everything), "load_basis": "index",
            "ai_wont_play": wont,
            "commander_ai_wont_play": [c for c in ai_wont_play(idx, commanders) if c in wont]}


def of_deck_text(text: str, idx=_AUTO) -> dict:
    """GET /decks/{file}: the two lists for one deck file, plus the Forge
    version they were read against (None when no index is built)."""
    idx = _load_index(idx)
    _name, commanders, main = parse_dck(text)
    return {"index": getattr(idx, "version", None), **of_names(idx, commanders, main)}


def record_for_run(deck_paths, idx=_AUTO) -> dict:
    """What run_sim stamps into a finished run's meta, on the worker (the
    machine whose Forge played it): {"ai_wont_play_by_deck": {Name=: [...]},
    "ai_wont_play_index": version}. Empty when no index is built yet (the
    worker builds it in the background at startup); the run page then reads
    the deck files at request time instead."""
    idx = _load_index(idx)
    if idx is None:
        return {}
    by_deck: dict[str, list[str]] = {}
    for p in deck_paths or []:
        text = _read(p)
        if text is None:
            continue
        name, commanders, main = parse_dck(text, Path(p).stem)
        by_deck[name] = ai_wont_play(idx, commanders + main)
    return {"ai_wont_play_by_deck": by_deck, "ai_wont_play_index": idx.version}


def _find_default(filename: str):
    try:
        from mtg_engine import _find_deck  # noqa: PLC0415 (lazy; gotcha 9)
        return _find_deck(filename)
    except Exception:  # noqa: BLE001 - CLI use without the server module
        p = Path(__file__).resolve().parent / "decks" / filename
        return p if p.is_file() else None


def for_run(meta: dict, find=None, idx=_AUTO) -> dict:
    """The run summary's `disclosures`: {"index": version or None, "decks":
    {deck Name=: {file, could_not_load, load_basis, ai_wont_play,
    commander_ai_wont_play}}}, keyed like `commanders` and the win rates.

    could_not_load: Forge's own load report when the run carries one
    (meta.unsupported_cards exists, even empty: basis "run"), else today's
    index against the deck file (basis "index"), else None.
    ai_wont_play: what run_sim recorded on the worker, else today's index
    against the deck file, else None (no index, or the file is gone)."""
    meta = meta if isinstance(meta, dict) else {}
    find = find or _find_default
    idx = _load_index(idx)
    recorded_load = isinstance(meta.get("unsupported_cards"), list)
    by_file = meta.get("unsupported_by_deck")
    by_file = by_file if isinstance(by_file, dict) else {}
    stored = meta.get("ai_wont_play_by_deck")
    stored = stored if isinstance(stored, dict) else {}
    # The Name= each staged file was seated under, from run_sim's fidelity
    # rows, so a deck deleted after the run still gets its own name.
    seated = {str(r.get("deck")): str(r.get("player"))
              for r in (meta.get("commander_fidelity") or [])
              if isinstance(r, dict) and r.get("deck") and r.get("player")}
    decks: dict[str, dict] = {}
    for raw in meta.get("decks") or []:
        base = Path(str(raw)).name
        try:
            path = find(base)
        except Exception:  # noqa: BLE001
            path = None
        text = _read(path) if path else None
        fallback = _IMPORT_HASH.sub("", Path(base).stem).replace("_", " ").title()
        name, commanders, main = parse_dck(text, seated.get(base, fallback)) \
            if text is not None else (seated.get(base, fallback), [], [])
        from_index = of_names(idx if text is not None else None, commanders, main)
        row = {"file": base}
        if recorded_load:
            row["could_not_load"] = [str(c) for c in (by_file.get(base) or [])]
            row["load_basis"] = "run"
        else:
            row["could_not_load"] = from_index["could_not_load"]
            row["load_basis"] = from_index["load_basis"]
        if isinstance(stored.get(name), list):
            wont = [str(c) for c in stored[name]]
            row["ai_wont_play"] = wont
            # The file may be gone; the run's own commander record is not.
            cmd_names = commanders or [str(c) for c in
                                       ((meta.get("commanders") or {}).get(name) or [])]
            row["commander_ai_wont_play"] = [c for c in wont if matches(c, cmd_names)]
        else:
            row["ai_wont_play"] = from_index["ai_wont_play"]
            row["commander_ai_wont_play"] = from_index["commander_ai_wont_play"]
        decks[name] = row
    version = meta.get("ai_wont_play_index") if stored else None
    return {"index": version or getattr(idx, "version", None), "decks": decks}


def for_result_deck(meta: dict, deck: str, find=None, idx=_AUTO) -> dict | None:
    """The disclosure row for one entry of meta.decks (telemetry, coaching)."""
    base = Path(str(deck or "")).name
    for row in for_run(meta, find=find, idx=idx)["decks"].values():
        if row.get("file") == base:
            return row
    return None


def _fold(name: str) -> str:
    try:
        from forge_index import fold  # noqa: PLC0415 - no index load, just the key
        return fold(_clean(name))
    except Exception:  # noqa: BLE001
        return " ".join(_clean(name).casefold().split())


def matches(card: str, skipped) -> bool:
    """Whether `card` (a telemetry watch name, a coaching card, a .dck
    commander line) names one of the `skipped` cards. Case-, accent- and
    printing-suffix-insensitive; a "Front // Back" name matches its front."""
    c = _fold(card)
    if not c:
        return False
    front = c.split(" // ", 1)[0].strip()
    for s in skipped or []:
        k = _fold(s)
        if k and (c == k or front == k or front == k.split(" // ", 1)[0].strip()):
            return True
    return False


def mentions(text: str, skipped) -> list[str]:
    """The `skipped` cards whose full name appears in free text (a coaching
    support-chain link such as "Commander: Winter, Cynical Opportunist")."""
    t = _fold(text)
    return [s for s in skipped or [] if _fold(s) and _fold(s) in t]
