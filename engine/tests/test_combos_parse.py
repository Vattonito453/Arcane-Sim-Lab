#!/usr/bin/env python3
"""combos.py: Forge's "|SET|art" suffix, the names Spellbook is sent, and the
poisoned-cache guard.

Forge's bundled precons write "1 Commodore Guff|CMM|1". parse_dck used to keep
the suffix, Spellbook recognised no card, answered identity "C" with no combos,
and that answer was cached forever and written up as "precons have no combos"
(diagnosis RC9; 38 cache entries). Separately, Spellbook knows a double-faced
card only by its full "Front // Back" name, while Forge and the import write the
front face, so the request widens front faces (the cache key does not change).

Offline: the network call is replaced by a canned response.
Run: py engine/tests/test_combos_parse.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import combos  # noqa: E402
import forge_index  # noqa: E402

PRECON = """[metadata]
Name=Planeswalker Party [CMM] [2023]
Set=CMM
[Commander]
1 Commodore Guff|CMM|1
[Main]
1 Ajani Steadfast|CMM|1
1 Arcane Signet|CMM
1 Chandra, Torch of Defiance|CMM|2
10 Island|CMM|1
[Sideboard]
1 Sol Ring|CMM|1
"""
CLEAN = """[Commander]
1 Commodore Guff
[Main]
1 Ajani Steadfast
1 Arcane Signet
1 Chandra, Torch of Defiance
10 Island
"""


def test_suffix_is_stripped():
    main, cmd = combos.parse_dck(PRECON)
    assert cmd == ["Commodore Guff"], cmd
    assert main == [("Ajani Steadfast", 1), ("Arcane Signet", 1),
                    ("Chandra, Torch of Defiance", 1), ("Island", 10)], main
    assert all("|" not in n for n, _ in main)
    # the sideboard is not the deck
    assert "Sol Ring" not in [n for n, _ in main]
    # a bare "|..." line has no name and is skipped, not sent as ""
    assert combos.parse_dck("[Main]\n1 |CMM|1\n") == ([], [])


def test_key_ignores_printing():
    """The same 99 hits the same entry whatever printing Forge wrote."""
    a = combos._key(*combos.parse_dck(PRECON))
    b = combos._key(*combos.parse_dck(CLEAN))
    assert a == b, (a, b)
    c = combos._key(*combos.parse_dck(PRECON.replace("|CMM|1", "|PLST|3")))
    assert a == c


CARDS = {
    "Birgi, God of Storytelling": {"mode": "Modal", "types": "Legendary Creature God",
                                   "faces": ["Birgi, God of Storytelling",
                                             "Harnfel, Horn of Bounty"]},
    "Brazen Borrower": {"mode": "Adventure", "types": "Creature Faerie Rogue",
                        "faces": ["Brazen Borrower", "Petty Theft"]},
    "Fire // Ice": {"mode": "Split", "types": "Instant", "faces": ["Fire", "Ice"]},
    "Ally Rogue": {"mode": "Specialize", "types": "Legendary Creature Halfling Rogue",
                   "faces": ["Ally Rogue", "Ally, White Rogue"]},
    "Sol Ring": {"mode": None, "types": "Artifact"},
}
IDX = forge_index.ForgeIndex(Path("."), {"forge_version": "test"}, CARDS, {})


class _Patch:
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def test_spellbook_names_from_the_index():
    with _Patch(forge_index, "load_index", lambda version=None: IDX):
        got = combos.spellbook_names(["Birgi, God of Storytelling", "Brazen Borrower",
                                      "Fire // Ice", "Ally Rogue", "Sol Ring",
                                      "Harnfel, Horn of Bounty", "Unknown Card"])
    assert got == {
        "Birgi, God of Storytelling": "Birgi, God of Storytelling // Harnfel, Horn of Bounty",
        "Brazen Borrower": "Brazen Borrower // Petty Theft",
    }, got       # split, specialize, plain, back face and unknown are sent as-is


def test_spellbook_names_from_the_card_cache():
    """No index: a front-face alias in the Scryfall cache carries face_of."""
    import cards
    facts = {"Birgi, God of Storytelling": {"face_of": "Birgi, God of Storytelling // "
                                            "Harnfel, Horn of Bounty", "layout": "modal_dfc"},
             "Harnfel, Horn of Bounty": {"face_of": "Birgi, God of Storytelling // "
                                         "Harnfel, Horn of Bounty", "layout": "modal_dfc"},
             "Fire": {"face_of": "Fire // Ice", "layout": "split"}}
    with _Patch(forge_index, "load_index", lambda version=None: None), \
            _Patch(cards, "get", lambda n, fetch=True: facts.get(n)):
        got = combos.spellbook_names(["Birgi, God of Storytelling", "Harnfel, Horn of Bounty",
                                      "Fire", "Sol Ring"])
    assert got == {"Birgi, God of Storytelling":
                   "Birgi, God of Storytelling // Harnfel, Horn of Bounty"}, got


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_find_combos_sends_full_names_and_keys_on_deck_names():
    sent: list[dict] = []
    canned = {"results": {"identity": "R", "included": [{
        "id": "1-2-3", "uses": [{"card": {"name": "Birgi, God of Storytelling // Harnfel, "
                                                  "Horn of Bounty"}},
                                {"card": {"name": "Seething Song"}}],
        "produces": [{"feature": {"name": "Infinite colored mana"}}]}],
        "almostIncluded": []}}

    def fake_urlopen(req, timeout=None):
        sent.append({"body": json.loads(req.data.decode()),
                     "ua": req.get_header("User-agent")})
        return _Resp(json.dumps(canned).encode())

    main = [("Birgi, God of Storytelling", 1), ("Seething Song", 1), ("Sol Ring", 1)]
    with tempfile.TemporaryDirectory() as d:
        with _Patch(combos, "CACHE_PATH", Path(d) / "combo_cache.json"), \
                _Patch(combos, "_cache", None), _Patch(combos, "_offline", False), \
                _Patch(forge_index, "load_index", lambda version=None: IDX), \
                _Patch(combos.urllib.request, "urlopen", fake_urlopen):
            res = combos.find_combos(main, [], fetch=True)
            assert len(sent) == 1, sent
            names = [c["card"] for c in sent[0]["body"]["main"]]
            assert names == ["Birgi, God of Storytelling // Harnfel, Horn of Bounty",
                             "Seething Song", "Sol Ring"], names
            assert sent[0]["ua"] == combos.USER_AGENT
            assert res["sent_as"] == {"Birgi, God of Storytelling":
                                      "Birgi, God of Storytelling // Harnfel, Horn of Bounty"}
            assert len(res["included"]) == 1
            # keyed by the deck's own names: the worker's cache-only lookup of
            # the same .dck hits it, index or no index
            with _Patch(forge_index, "load_index", lambda version=None: None):
                again = combos.find_combos(main, [], fetch=False)
            assert again == res and len(sent) == 1
            on_disk = json.loads((Path(d) / "combo_cache.json").read_text(encoding="utf-8"))
            assert combos._key(main, []) in on_disk


def test_committed_cache_carries_no_poisoned_answer():
    """The poison signature: identity "C" with no included AND no
    almost-included combos. A real colourless precon (Eldrazi Unbound) has
    almost-included combos, so it never matches."""
    path = ENGINE / "combo_cache.json"
    if not path.is_file():
        print("  (no combo_cache.json: poisoned-entry check skipped)")
        return
    cache = json.loads(path.read_text(encoding="utf-8"))
    poisoned = [k for k, v in cache.items() if isinstance(v, dict)
                and v.get("identity") == "C" and not v.get("included")
                and not v.get("almost_included")]
    assert poisoned == [], f"{len(poisoned)} poisoned entries: {poisoned[:5]}"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL ASSERTIONS PASSED")
