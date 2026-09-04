#!/usr/bin/env python3
"""Scryfall card-data cache — static card facts for the sim pipeline and UI.

Why this exists: Forge's text log never records cards ENTERING the battlefield,
only leaving it (verified: 134 Battlefield->Graveyard, 15 ->Exile, 0 entries in a
real 16-game log). So board state has to be reconstructed from resolve events —
and that requires knowing whether a resolved card is a permanent or a one-shot
spell. `type_line` is what makes that decision correct, so this cache is
load-bearing for board accuracy, not just for display.

Scryfall etiquette (https://scryfall.com/docs/api):
  * identifies itself with a real User-Agent
  * uses POST /cards/collection to batch up to 75 names per request
  * sleeps between requests
  * caches everything on disk; a warm cache makes zero network calls
Legal posture (frontend_architecture.md §5): we store the small subset of fields
we display, hotlink images rather than rehosting, and do not republish bulk data.

CLI:
  python3 cards.py warm <result.json>   # populate cache from a sim result
  python3 cards.py get "Sol Ring"       # look one up
  python3 cards.py stats
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA_DIR = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent)))
CACHE_PATH = DATA_DIR / "card_cache.json"
API = "https://api.scryfall.com"
UA = "MTG-Sim-Lab/0.1 (deck analysis tool; contact: local install)"
BATCH = 75          # Scryfall's documented maximum per collection request
SLEEP = 0.12        # ~8 req/s, inside their 10 req/s guidance

# Types that stay on the battlefield when a spell resolves.
PERMANENT_TYPES = ("Creature", "Artifact", "Enchantment", "Land",
                   "Planeswalker", "Battle")

_cache: dict[str, dict] | None = None
_offline = False     # set once a fetch fails, so we stop retrying in a loop


# ---------- cache file ----------

def _load() -> dict[str, dict]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
        _alias_faces(_cache)
    return _cache


def _alias_faces(cache: dict[str, dict]) -> int:
    """Give every cached double-faced card an entry under its FRONT face name.

    The cache used to be keyed only by Scryfall's full name, "Bloodline Keeper
    // Lord of Lineage", while Forge names the object by the face it shows:
    "Bloodline Keeper". Every lookup by face name therefore missed, the UI drew
    a name-only tile ("no card data"), board.py typed the card as unknown, and
    the miss was never recorded as not_found, so each page load re-asked
    Scryfall for the same card (42 such cards in the committed cache). The
    stored entry already holds front-face stats (_slim reads the front face),
    but its type line is the joined "Instant // Land", which a substring test
    reads as a land: the alias takes the front half. Back faces are NOT
    aliased here: their art, type and P/T differ, and a lookup for one fetches
    the card once and _store() fills it in.
    """
    added = 0
    for k, c in list(cache.items()):
        if not isinstance(c, dict):
            continue
        name = c.get("name") or ""
        if " // " not in name or c.get("not_found"):
            continue
        front = name.split(" // ")[0].strip()
        fk = key(front)
        if fk and fk not in cache:
            alias = dict(c)
            alias["name"] = front
            alias["type_line"] = (c.get("type_line") or "").split(" // ")[0].strip()
            alias["face_of"] = name
            cache[fk] = alias
            added += 1
    return added


def save() -> None:
    if _cache is None:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")


def key(name: str) -> str:
    return normalize_name(name).lower()


# ---------- name cleaning ----------

def normalize_name(raw: str) -> str:
    """Forge decorates names; strip that down to a Scryfall-lookupable name.

    "Kilo, Apogee Mind (100)"        -> "Kilo, Apogee Mind"
    "Sol Ring (263) - Add {C}{C}."   -> "Sol Ring"
    "Zombie Token (406)"             -> "Zombie Token"   (tokens aren't cards)
    """
    s = raw.strip()
    s = re.split(r"\s+-\s+", s)[0]            # trailing ability text
    s = re.sub(r"\s*\(\d+\)\s*$", "", s)      # Forge instance id
    s = re.sub(r"\s*\([A-Z0-9]{2,6}\)\s*[\w★]*$", "", s)  # (SET) 123p
    return s.strip()


def is_token(name: str) -> bool:
    """Tokens are not Scryfall cards; never try to fetch them."""
    return bool(re.search(r"\bTokens?\b", normalize_name(name), re.I))


# ---------- fetching ----------

def _cmc_of(mana_cost: str) -> float:
    """Mana value of one face's cost. Scryfall gives cmc per CARD, so a split
    half needs its own: "{1}{R}" -> 2, hybrid "{2/W}" -> 2, "{X}" -> 0."""
    total = 0.0
    for sym in re.findall(r"\{([^}]*)\}", mana_cost or ""):
        parts = sym.split("/")
        nums = [int(p) for p in parts if p.isdigit()]
        if nums:
            total += max(nums)
        elif any(p.upper() in ("X", "Y", "Z") for p in parts):
            continue
        else:
            total += 1
    return total


def _slim(c: dict, face: dict | None = None) -> dict:
    """Keep only the fields we actually use (display + board logic).

    With `face`, the entry describes that one face of a double-faced card: its
    own name, type line, cost, stats, text and art (a split half shares the
    card's single image). Without it, the historical full-name entry: the
    card's name and joined type line with front-face stats.
    """
    faces = c.get("card_faces") or []
    front = face or (faces[0] if faces else c)
    named = face or c
    img = (front.get("image_uris") or c.get("image_uris") or {})
    if face is not None:
        mana = face.get("mana_cost") or ""
        cmc = _cmc_of(mana) if mana else c.get("cmc")
        colors = face["colors"] if "colors" in face else (c.get("colors") or [])
    else:
        mana = front.get("mana_cost") or c.get("mana_cost") or ""
        cmc = c.get("cmc")
        colors = front.get("colors") or c.get("colors") or []
    return {
        "name": named.get("name"),
        "type_line": named.get("type_line") or c.get("type_line") or front.get("type_line") or "",
        "mana_cost": mana,
        "cmc": cmc,
        "power": front.get("power"),
        "toughness": front.get("toughness"),
        "oracle_text": front.get("oracle_text") or c.get("oracle_text") or "",
        "colors": colors,
        "color_identity": c.get("color_identity") or [],
        "art_crop": img.get("art_crop"),
        "normal": img.get("normal"),
        "scryfall_uri": c.get("scryfall_uri"),
    }


def _face_slims(c: dict) -> dict[str, dict]:
    """{cache key: slim} for one Scryfall card: the full name plus each face.

    Forge logs a double-faced card by the face it currently shows, so both
    "Bloodline Keeper" and "Lord of Lineage" must resolve. A transform or modal
    face carries its own image_uris, type line, P/T and text; a split or
    adventure face shares the card's single image but keeps its own type line
    and text. `face_of` names the full card so a reader can tell an alias from
    a card of its own.
    """
    out = {key(c.get("name") or ""): _slim(c)}
    for face in c.get("card_faces") or []:
        fk = key((face.get("name") or "").strip())
        if not fk or fk in out:
            continue
        slim = _slim(c, face)
        slim["face_of"] = c.get("name")
        out[fk] = slim
    return out


def _store(cache: dict[str, dict], c: dict) -> int:
    """Cache one fetched card under every name Forge might use for it.

    A face never displaces a card of its own: "Naktamun Lorespinner // Wheel
    of Fortune" must not overwrite the real Wheel of Fortune (both are in the
    committed cache). A not_found record at a face name IS replaced. Returns
    the number of entries written."""
    n = 0
    full = key(c.get("name") or "")
    for k, slim in _face_slims(c).items():
        have = cache.get(k)
        if (k != full and isinstance(have, dict) and not have.get("not_found")
                and not have.get("face_of")):
            continue
        cache[k] = slim
        n += 1
    return n


def _post(path: str, payload: dict) -> dict | None:
    global _offline
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        _offline = True
        print(f"cards.py: Scryfall unreachable ({e}) — serving cache only", file=sys.stderr)
        return None


def fetch_missing(names: list[str]) -> int:
    """Fetch any uncached names in batches. Returns how many were added."""
    cache = _load()
    want: list[str] = []
    seen: set[str] = set()
    for n in names:
        if is_token(n):
            continue
        k = key(n)
        if not k or k in cache or k in seen:
            continue
        seen.add(k)
        want.append(normalize_name(n))
    if not want or _offline:
        return 0

    added = 0
    for i in range(0, len(want), BATCH):
        chunk = want[i:i + BATCH]
        body = {"identifiers": [{"name": n} for n in chunk]}
        data = _post("/cards/collection", body)
        if data is None:
            break
        for c in data.get("data", []):
            _store(cache, c)
            added += 1          # cards, not entries: callers report it as such
        # Record misses so we don't re-request them every run.
        for miss in data.get("not_found", []):
            nm = miss.get("name")
            if nm:
                cache[key(nm)] = {"name": nm, "not_found": True, "type_line": ""}
        if i + BATCH < len(want):
            time.sleep(SLEEP)
    if added:
        save()
    return added


def get(name: str, fetch: bool = True) -> dict | None:
    """One card. Returns None for tokens, misses, and offline-cache-misses."""
    if is_token(name):
        return None
    cache = _load()
    k = key(name)
    if k not in cache and fetch:
        fetch_missing([name])
        cache = _load()
    c = cache.get(k)
    if not isinstance(c, dict) or c.get("not_found"):
        return None          # a hand-edited or damaged value is a miss, not a crash
    return c


def get_many(names: list[str], fetch: bool = True) -> dict[str, dict]:
    """Batch lookup keyed by normalized name."""
    if fetch:
        fetch_missing(names)
    cache = _load()
    out = {}
    for n in names:
        c = cache.get(key(n))
        if isinstance(c, dict) and not c.get("not_found"):
            out[normalize_name(n)] = c
    return out


# ---------- the board-logic question this module exists to answer ----------

def is_permanent(name: str, fetch: bool = False) -> bool | None:
    """Does this card stay on the battlefield when it resolves?

    True / False when known; None when unknown (uncached, offline, or a token) —
    callers must treat None as "don't guess", not as False.
    """
    if is_token(name):
        return True      # a token that exists at all is on the battlefield
    c = get(name, fetch=fetch)
    if not c:
        return None
    tl = c.get("type_line") or ""
    if not tl:
        return None
    return any(t in tl for t in PERMANENT_TYPES)


def card_kind(name: str, fetch: bool = False) -> str:
    """Coarse grouping for the UI board rows."""
    if is_token(name):
        return "token"
    c = get(name, fetch=fetch)
    tl = (c or {}).get("type_line") or ""
    if "Land" in tl:
        return "land"
    if "Creature" in tl:
        return "creature"
    if "Planeswalker" in tl:
        return "planeswalker"
    if "Battle" in tl:
        return "battle"
    if "Artifact" in tl or "Enchantment" in tl:
        return "artifact"
    if "Instant" in tl or "Sorcery" in tl:
        return "spell"
    return "unknown"


# ---------- harvesting names out of a sim result ----------

# Forge log verbs/labels that can precede a card reference. Deliberately contains
# NO bare prepositions ("of", "and", "to"): those appear inside real card names
# constantly, and cutting on them shredded names like "Gray Merchant of Asphodel"
# and "Sword of Hearth and Home". Multi-word phrases ("damage to") are safe.
_LOG_VERBS = re.compile(
    r"\b(?:assigned|didn't\s+block|doesn't\s+block|blocks?|blocked|discards?|discarded"
    r"|countered|milled|casts?|plays?|played|activated|triggered|targeting"
    r"|deals?|receives?|sacrifices?|sacrificed|destroys?|destroyed"
    r"|exiles?|exiled|returns?|returned|searches|draws?|gains?"
    r"|regenerate|shuffle|tapped|untapped|tap|untap|attach\s+to|counter|puts?|wear"
    r"|damage\s+to|poison\s+counter|Zone\s+Changer|Zone\s+Change"
    r"|Attacker|Blocker|Defender|Card)\b[:\s]*",
    re.I,
)


def name_before_id(text: str) -> str | None:
    """Extract the card name from Forge's "… <Name> (123)" reference.

    The reference is unambiguous but the left edge is not, so we cut at the last
    log verb and then drop any leading lowercase residue ("of", "the", …).
    Card names themselves may contain lowercase words, but never *start* with one.
    """
    seg = text
    # Deck/section prefixes ("Ai(2)-Kilo Helm Final: Crystalline Crawler").
    if ": " in seg:
        seg = seg.rsplit(": ", 1)[-1]
    seg = _LOG_VERBS.split(seg)[-1] if _LOG_VERBS.search(seg) else seg
    seg = seg.strip().strip("[]").lstrip(":").strip()
    words = seg.split()
    # Card names start with a capital (or a quote); drop lowercase/numeric residue.
    while words and not re.match(r"^[A-Z\"']", words[0]):
        words.pop(0)
    name = " ".join(words).strip().rstrip(",")
    return name if 2 < len(name) <= 40 else None


def _card_refs(raw: str) -> list[str]:
    """Card names referenced as "<Name> (123)" in one Forge line.

    Segmenting on the ids first means each candidate is bounded by the previous
    reference, so comma-containing names ("Kilo, Apogee Mind") survive intact
    while comma-separated lists ("[A (1), B (2)]") still split correctly.
    """
    # A card id is " (123)". Forge player keys look like "Ai(2)-Name": no leading
    # space and a trailing hyphen, so requiring both excludes them.
    parts = re.split(r"(?<=\s)\(\d+\)(?!-)", raw)
    out = []
    for seg in parts[:-1]:            # every part except the tail precedes an id
        nm = name_before_id(seg)
        if nm and " Ai" not in nm and "(" not in nm:
            out.append(nm)
    return out


def names_in_result(result: dict) -> list[str]:
    """Every card name a result file mentions, for cache warming."""
    found: set[str] = set()
    for g in result.get("games", []):
        for t in list(g.get("turns", [])) + [{"events": g.get("events_pregame", [])}]:
            for e in t.get("events", []):
                if e.get("object"):
                    found.add(normalize_name(e["object"]))
                for nm in _card_refs(e.get("raw", "")):
                    found.add(normalize_name(nm))
    return sorted(n for n in found if n and not is_token(n))


def stats() -> dict:
    cache = _load()
    entries = [c for c in cache.values() if isinstance(c, dict)]
    return {
        # Cards, as before this cache learned faces: face entries are listed
        # separately so the number does not jump when a cache is migrated.
        "cached": sum(1 for c in entries if not c.get("face_of")),
        "face_entries": sum(1 for c in entries if c.get("face_of")),
        "not_found": sum(1 for c in entries if c.get("not_found")),
        "path": str(CACHE_PATH),
        "offline": _offline,
    }


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "warm":
        if len(args) < 2:
            sys.exit("usage: cards.py warm <result.json>")
        result = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        names = names_in_result(result)
        print(f"{len(names)} distinct card names in {args[1]}")
        added = fetch_missing(names)
        print(f"added {added} to cache; {json.dumps(stats())}")
        unknown = [n for n in names if get(n, fetch=False) is None]
        if unknown:
            print(f"{len(unknown)} still unknown (first 10): {unknown[:10]}")
    elif cmd == "get":
        print(json.dumps(get(" ".join(args[1:])), indent=2, ensure_ascii=False))
    elif cmd == "stats":
        print(json.dumps(stats(), indent=2))
    else:
        print(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
