#!/usr/bin/env python3
"""Known-combo lookup for a deck, via Commander Spellbook's find-my-combos API.

Why this exists: Forge's AI cannot PILOT most multi-card combos, so a combo
deck's sim win rate is a floor, not a verdict (engine/SIM_CALIBRATION.md). The
honest fix is not a smarter pilot — it is knowing what the deck is trying to do,
so analysis.py can then measure how often the pieces actually assembled in real
games and whether the AI ever converted them. This module supplies the first
half: which known combos the 99 contains.

Data source: https://commanderspellbook.com — the community combo database
(~30k combos). One POST per unique decklist, cached on disk forever, so a warm
cache makes zero network calls (same etiquette as cards.py with Scryfall).

Stdlib only, like the rest of engine/.

CLI:
    python3 engine/combos.py engine/decks/drana_vampires.dck
    python3 engine/combos.py <deck.dck> --no-fetch     # cache only
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://backend.commanderspellbook.com/find-my-combos"
USER_AGENT = "SimLab/0.1 (Commander deck analysis; github: private prototype)"
TIMEOUT = 25

DATA_DIR = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent)))
CACHE_PATH = DATA_DIR / "combo_cache.json"

_cache: dict[str, dict] | None = None
_offline = os.environ.get("MTG_OFFLINE", "0") == "1"


def _load() -> dict[str, dict]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — missing or corrupt cache: start fresh
            _cache = {}
    return _cache


def _save() -> None:
    if _cache is None:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def parse_dck(text: str) -> tuple[list[tuple[str, int]], list[str]]:
    """(main [(name, qty)], commanders [name]) out of a Forge .dck body."""
    main: list[tuple[str, int]] = []
    commanders: list[str] = []
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.lower()
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        qty, name = int(parts[0]), parts[1].strip()
        if section == "[commander]":
            commanders.append(name)
        elif section == "[main]":
            main.append((name, qty))
    return main, commanders


def _key(main: list[tuple[str, int]], commanders: list[str]) -> str:
    """Content hash: the same 99 always hits the same cache entry."""
    basis = "\n".join(sorted(f"{q} {n}" for n, q in main)) + "\n#" + "\n".join(sorted(commanders))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _slim(variant: dict) -> dict:
    """The fields analysis and the UI need — not the whole Spellbook record."""
    return {
        "id": variant.get("id"),
        # `uses` order is the combo's own card order; keep it.
        "cards": [u["card"]["name"] for u in variant.get("uses", []) if u.get("card")],
        "produces": [p["feature"]["name"] for p in variant.get("produces", [])
                     if p.get("feature")],
        "description": (variant.get("description") or "")[:2000],
        "mana_needed": variant.get("manaNeeded") or "",
        "prerequisites": (variant.get("notablePrerequisites") or "")[:500],
    }


def find_combos(main: list[tuple[str, int]], commanders: list[str],
                fetch: bool = True) -> dict | None:
    """Combos this list contains. None when unknown (offline and not cached) —
    callers must treat None as "not analysed", never as "no combos"."""
    cache = _load()
    key = _key(main, commanders)
    if key in cache:
        return cache[key]
    if not fetch or _offline:
        return None

    body = json.dumps({
        "main": [{"card": n, "quantity": q} for n, q in main],
        "commanders": [{"card": n, "quantity": 1} for n in commanders],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        sys.stderr.write(f"combos: spellbook unreachable ({e}); deck not analysed\n")
        return None

    results = data.get("results") or {}
    slim = {
        "identity": results.get("identity") or "",
        "included": [_slim(v) for v in results.get("included") or []],
        # One card short of a combo — the "you are one swap away" signal.
        "almost_included": [_slim(v) for v in results.get("almostIncluded") or []],
    }
    cache[key] = slim
    _save()
    return slim


def combos_for_dck(path: str | Path, fetch: bool = True) -> dict | None:
    main, commanders = parse_dck(Path(path).read_text(encoding="utf-8"))
    if not main:
        return None
    return find_combos(main, commanders, fetch=fetch)


def stats() -> dict:
    return {"cached_decks": len(_load()), "path": str(CACHE_PATH), "offline": _offline}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fetch = "--no-fetch" not in sys.argv
    if not args:
        print(__doc__)
        return 1
    for path in args:
        res = combos_for_dck(path, fetch=fetch)
        name = Path(path).name
        if res is None:
            print(f"{name}: not analysed (offline and not cached)")
            continue
        inc, alm = res["included"], res["almost_included"]
        print(f"{name}: {len(inc)} combo(s) in the 99, {len(alm)} one card away")
        for c in inc:
            print(f"  [{c['id']}] " + " + ".join(c["cards"]))
            if c["produces"]:
                print(f"      -> {', '.join(c['produces'][:4])}")
        for c in alm[:5]:
            print(f"  (almost) " + " + ".join(c["cards"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
