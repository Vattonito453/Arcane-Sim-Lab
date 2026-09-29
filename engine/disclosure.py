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
                  Forge index instead (basis "index"): names Forge doesn't
                  know, and the joined "Front // Back" spelling of a
                  non-split card, both of which it refuses at load
                  (refused_as_written).
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
import unicodedata
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


def refused_as_written(idx, name: str) -> bool:
    """Whether Forge refuses this .dck name at load, read from the index.

    Forge loads a card by its own name (ignoring case): the front face of a
    transform, modal, battle, adventure or flip card, and "A // B" for a split
    card. So a name the index cannot resolve is refused (a typo, or a
    single-slash "Primal Amulet / Primal Wellspring", measured refused in the
    G0a stderr), and so is the joined "Front // Back" spelling of a non-split
    card, which the index resolves but Forge does not (measured: both Ral
    decks lost their commander that way). convert_decklist rewrites both
    forms it can on import; this is for deck files written before it did."""
    c = _clean(name)
    if not c:
        return False
    forge = idx.resolve(c)
    if forge is None:
        return True
    if " // " in c and " // " not in forge:
        return True
    return False


def unknown_to_forge(idx, names) -> list[str]:
    """Names Forge refuses at load, as the deck spells them, first-seen order."""
    out: list[str] = []
    for n in names:
        c = _clean(n)
        if c and c not in out and refused_as_written(idx, c):
            out.append(c)
    return out


def ai_wont_play(idx, names) -> list[str]:
    """The Forge names, in first-seen order, of the cards among `names` that
    Forge's AI doesn't cast on its own. A name Forge refuses at load is not
    listed here (it never reaches a game; it is in could_not_load instead)."""
    out: list[str] = []
    for n in names:
        c = _clean(n)
        if not c or refused_as_written(idx, c):
            continue
        forge = idx.resolve(c)
        if forge and forge not in out and ai_skips(idx.flag(forge)):
            out.append(forge)
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


def _refusal_fold(name: str) -> str:
    """Case- and accent-free form, as run_sim._fold compares refusals."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", _clean(name))
                   if not unicodedata.combining(ch)).casefold()


def _refused_here(cards, refused) -> list[tuple[str, str]]:
    """(deck spelling, Forge's refusal) for each of the deck's `cards` that a
    name in Forge's load report (meta.unsupported_cards) names.

    Forge prints the name the deck file requested, but on the JVM's stderr,
    whose encoding follows the container's locale; the worker sets none, so
    each character ASCII cannot encode arrives as '?' ("Lim-D?l's Vault").
    Compared as run_sim._refused_commanders does: accent- and case-free, a '?'
    in a refusal standing for exactly one character."""
    pats = []
    for r in refused:
        f = _refusal_fold(r)
        if not f:
            continue
        rx = "".join("." if ch == "?" else re.escape(ch) for ch in f) if "?" in f else None
        pats.append((r, f, re.compile(rx, re.S) if rx else None))
    out: list[tuple[str, str]] = []
    for c in cards:
        fc = _refusal_fold(c)
        for r, f, rx in pats:
            if fc == f or (rx is not None and rx.fullmatch(fc)):
                out.append((c, r))
                break
    return out


# Where Forge's log puts a card name between fixed delimiters, so a longer
# name that merely ends with it ("Big Nothing Like This (4)") is never read
# as it: a land drop, a line that opens with "Name (id)" (a zone change, a
# mana ability), and a damage event's source.
_LOG_PLAYED = re.compile(r"^.+?\splayed\s(.+?)\s\((\d+)\)")
_LOG_OPENS = re.compile(r"^([^()\[\]]+?)\s\((\d+)\)(?:\s+was put into|\s+-\s)")
_LOG_SOURCE = re.compile(r"^(.+?)\s\((\d+)\)$")


def shown_in_run(result: dict | None):
    """A predicate over card names: does the run's own record show a card
    by exactly this name in a game? Evidence is only what Forge printed or
    the shim recorded in a name's own slot: an event's `object` (a cast, a
    trigger), a zone record's `card`, a land drop, a line that opens with
    "Name (id)" (a zone change, a mana ability), and a damage source.
    Case-free, as Forge's lookup is.

    Used for a run older than Forge's load report, whose could-not-load
    list is today's index standing in: a name the run shows in play was
    loaded by the Forge that played it (measured: a July run cast Adamantium
    Bonding Tank in 2 games while today's index does not know it, and the
    page said it was "most likely left out of every game")."""
    names: set[str] = set()

    def add(n) -> None:
        n = str(n or "").strip()
        if n:
            names.add(n.casefold())

    for g in (result or {}).get("games") or []:
        if not isinstance(g, dict):
            continue
        for z in g.get("zones") or []:
            if isinstance(z, dict):
                add(z.get("card"))
        for t in g.get("turns") or []:
            if not isinstance(t, dict):
                continue
            for e in t.get("events") or []:
                if not isinstance(e, dict):
                    continue
                add(e.get("object"))
                raw = str(e.get("raw") or "")
                for rx in (_LOG_PLAYED, _LOG_OPENS):
                    m = rx.match(raw)
                    if m:
                        add(m.group(1))
                m = _LOG_SOURCE.match(str(e.get("source") or ""))
                if m:
                    add(m.group(1))

    def shows(card: str) -> bool:
        c = _clean(card)
        return bool(c) and c.casefold() in names
    return shows


def for_run(meta: dict, find=None, idx=_AUTO, result: dict | None = None) -> dict:
    """The run summary's `disclosures`: {"index": version or None, "decks":
    {deck Name=: {file, could_not_load, load_basis, ai_wont_play,
    commander_ai_wont_play}}}, keyed like `commanders` and the win rates.

    could_not_load: Forge's own load report when the run carries one
    (meta.unsupported_cards exists, even empty: basis "run"), else today's
    index against the deck file (basis "index"), else None. With the
    `result` itself, an index-basis name the run shows in play is dropped
    (shown_in_run): today's Forge may not be the one that played it. The
    joined "A // B" or "A / B" spelling is only cleared by that exact name,
    never by its front face, which another deck's copy could have put in
    play while this deck's line was refused. The report is
    attributed to each deck by run_sim's unsupported_by_deck AND by matching
    it against the deck file's own lines: a salvaged run (run_sim.salvage)
    carries unsupported_cards with no per-deck split, and run_sim's split
    compares exact names, so a refusal the JVM wrote with '?' for an accented
    letter reached no deck. When a refusal cannot be placed and a deck's file
    is gone, that deck's list is None ("cannot say"), never "none".
    ai_wont_play: what run_sim recorded on the worker, else today's index
    against the deck file, else None (no index, or the file is gone)."""
    meta = meta if isinstance(meta, dict) else {}
    find = find or _find_default
    idx = _load_index(idx)
    recorded_load = isinstance(meta.get("unsupported_cards"), list)
    refused = [str(c) for c in (meta.get("unsupported_cards") or []) if str(c).strip()] \
        if recorded_load else []
    split_at_run = isinstance(meta.get("unsupported_by_deck"), dict)
    by_file = meta.get("unsupported_by_deck") if split_at_run else {}
    stored = meta.get("ai_wont_play_by_deck")
    stored = stored if isinstance(stored, dict) else {}
    # The Name= each staged file was seated under, from run_sim's fidelity
    # rows, so a deck deleted after the run still gets its own name.
    seated = {str(r.get("deck")): str(r.get("player"))
              for r in (meta.get("commander_fidelity") or [])
              if isinstance(r, dict) and r.get("deck") and r.get("player")}
    decks: dict[str, dict] = {}
    shows = None                  # shown_in_run(result), built on first need
    placed: set[str] = set()      # refusals attributed to some deck
    unplaced_rows: list[dict] = []  # salvaged run, deck file gone: decided last
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
        row = {"file": base, "could_not_load": None, "load_basis": None}
        if recorded_load:
            listed = [str(c) for c in (by_file.get(base) or [])]
            placed.update(listed)
            row["load_basis"] = "run"
            if text is not None:
                hits = _refused_here(commanders + main, refused)
                placed.update(r for _c, r in hits)
                # The deck's own spelling ('?' restored), then anything the
                # run's split named that the file no longer lists.
                matched = {r for _c, r in hits}
                row["could_not_load"] = [c for c, _r in hits] + \
                    [r for r in listed if r not in matched]
            elif split_at_run:
                row["could_not_load"] = listed
            else:
                unplaced_rows.append(row)
        else:
            row["could_not_load"] = from_index["could_not_load"]
            row["load_basis"] = from_index["load_basis"]
            if row["could_not_load"] and result is not None:
                if shows is None:
                    shows = shown_in_run(result)
                row["could_not_load"] = [c for c in row["could_not_load"] if not shows(c)]
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
    # A salvaged run and a deleted deck: "none" only when every refusal is
    # already placed on another deck; otherwise this deck cannot be cleared.
    clear = all(r in placed for r in refused)
    for row in unplaced_rows:
        row["could_not_load"] = [] if clear else None
        if not clear:
            row["load_basis"] = None
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
    support-chain link such as "Commander: Winter, Cynical Opportunist").

    As a whole name, never inside a longer word: Forge 2.0.13's 2,404 listed
    spells include "Flux", "Flash" and "Raze", which a bare substring test
    finds in "Aetherflux Reservoir", "Flashback" and "Bloodcrazed Goblin",
    rejecting a sound coaching reply or re-marking a cached row."""
    t = _fold(text)
    out = []
    for s in skipped or []:
        k = _fold(s)
        if k and re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", t):
            out.append(s)
    return out
