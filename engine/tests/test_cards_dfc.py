#!/usr/bin/env python3
"""Double-faced cards must resolve by the face name Forge logs.

A playtester saw Bloodline Keeper in Drana Vampires' hand with no art and no
card data. The cache held the card, keyed "bloodline keeper // lord of
lineage" (Scryfall's full name); Forge names the object "Bloodline Keeper",
so every lookup missed, the miss was never recorded, and each page load
re-asked Scryfall for it. 72 cards in the local cache were affected.

Run: python3 engine/tests/test_cards_dfc.py   (no network)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cards  # noqa: E402

TRANSFORM = {
    "name": "Bloodline Keeper // Lord of Lineage",
    "layout": "transform",
    "type_line": "Creature — Vampire // Creature — Vampire",
    "cmc": 4.0,
    "color_identity": ["B"],
    "scryfall_uri": "https://scryfall.com/card/isd/90",
    "card_faces": [
        {"name": "Bloodline Keeper", "mana_cost": "{2}{B}{B}",
         "type_line": "Creature — Vampire", "power": "3", "toughness": "3",
         "oracle_text": "Flying\n{T}: Create a 2/2 black Vampire creature token with flying.",
         "colors": ["B"],
         "image_uris": {"normal": "https://c.scryfall.io/normal/front/b.jpg",
                        "art_crop": "https://c.scryfall.io/art_crop/front/b.jpg"}},
        {"name": "Lord of Lineage", "mana_cost": "",
         "type_line": "Creature — Vampire", "power": "5", "toughness": "5",
         "oracle_text": "Flying\nOther Vampires you control get +2/+2.",
         "colors": ["B"],
         "image_uris": {"normal": "https://c.scryfall.io/normal/back/l.jpg",
                        "art_crop": "https://c.scryfall.io/art_crop/back/l.jpg"}},
    ],
}
SPLIT = {
    "name": "Wear // Tear",
    "layout": "split",
    "type_line": "Instant // Instant",
    "cmc": 3.0,
    "color_identity": ["R", "W"],
    "image_uris": {"normal": "https://c.scryfall.io/normal/front/w.jpg",
                   "art_crop": "https://c.scryfall.io/art_crop/front/w.jpg"},
    "card_faces": [
        {"name": "Wear", "mana_cost": "{1}{R}", "type_line": "Instant",
         "oracle_text": "Destroy target artifact.", "colors": ["R"]},
        {"name": "Tear", "mana_cost": "{W}", "type_line": "Instant",
         "oracle_text": "Destroy target enchantment.", "colors": ["W"]},
    ],
}


def _fresh(tmp: Path, seed: dict | None = None) -> None:
    cards.CACHE_PATH = tmp / "card_cache.json"
    if seed is not None:
        cards.CACHE_PATH.write_text(json.dumps(seed), encoding="utf-8")
    cards._cache = None


def test_store_writes_every_face() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        cache = cards._load()
        cards._store(cache, TRANSFORM)
        cards._store(cache, SPLIT)

        front = cards.get("Bloodline Keeper", fetch=False)
        assert front and front["power"] == "3", front
        assert front["normal"].endswith("front/b.jpg"), front
        assert front["face_of"] == "Bloodline Keeper // Lord of Lineage"
        back = cards.get("Lord of Lineage", fetch=False)
        assert back and back["power"] == "5" and back["mana_cost"] == "", back
        assert back["normal"].endswith("back/l.jpg"), back
        assert "+2/+2" in back["oracle_text"]
        # The full name still resolves, as it always did.
        full = cards.get("Bloodline Keeper // Lord of Lineage", fetch=False)
        assert full and full["power"] == "3" and "face_of" not in full, full
        # Forge decorations are stripped before the lookup, as for any card.
        assert cards.get("Bloodline Keeper (312)", fetch=False) is not None

        # Split halves share the one image but keep their own text.
        wear = cards.get("Wear", fetch=False)
        tear = cards.get("Tear", fetch=False)
        assert wear and tear, (wear, tear)
        assert wear["normal"] == tear["normal"] == SPLIT["image_uris"]["normal"]
        assert "artifact" in wear["oracle_text"] and "enchantment" in tear["oracle_text"]
        assert wear["type_line"] == "Instant"

        # What the board logic asks: a permanent, a creature.
        assert cards.is_permanent("Bloodline Keeper") is True
        assert cards.card_kind("Lord of Lineage") == "creature"
        assert cards.card_kind("Wear") == "spell"
    print("  store: front, back and full names all resolve")


def test_existing_cache_gets_front_aliases_on_load() -> None:
    """A cache written by the old code, keyed by full name only."""
    old = {
        "bloodline keeper // lord of lineage": {
            "name": "Bloodline Keeper // Lord of Lineage",
            "type_line": "Creature — Vampire // Creature — Vampire",
            "mana_cost": "{2}{B}{B}", "cmc": 4.0, "power": "3", "toughness": "3",
            "oracle_text": "Flying", "colors": ["B"], "color_identity": ["B"],
            "art_crop": "a", "normal": "n", "scryfall_uri": "u",
        },
        "sol ring": {"name": "Sol Ring", "type_line": "Artifact", "mana_cost": "{1}",
                     "cmc": 1.0, "power": None, "toughness": None, "oracle_text": "",
                     "colors": [], "color_identity": [], "art_crop": None,
                     "normal": None, "scryfall_uri": None},
        "nonesuch": {"name": "Nonesuch", "not_found": True, "type_line": ""},
    }
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d), seed=old)
        cache = cards._load()
        front = cards.get("Bloodline Keeper", fetch=False)
        assert front and front["power"] == "3" and front["face_of"], front
        # The back face is deliberately NOT invented from front-face data.
        assert cards.get("Lord of Lineage", fetch=False) is None
        # Nothing else changed shape; not_found stays not_found.
        assert cards.get("Sol Ring", fetch=False)["name"] == "Sol Ring"
        assert cards.get("Nonesuch", fetch=False) is None
        assert len(cache) == 4, sorted(cache)
        # Aliasing is idempotent.
        assert cards._alias_faces(cache) == 0
    print("  load: an old full-name-only cache gains front-face aliases")


def test_get_many_reports_faces_as_found() -> None:
    with tempfile.TemporaryDirectory() as d:
        _fresh(Path(d))
        cards._store(cards._load(), TRANSFORM)
        found = cards.get_many(["Bloodline Keeper (312)", "Lord of Lineage", "Sol Ring"], fetch=False)
        assert set(found) == {"Bloodline Keeper", "Lord of Lineage"}, sorted(found)
    print("  get_many: keyed by the normalized name the caller asked for")


def main() -> None:
    test_store_writes_every_face()
    test_existing_cache_gets_front_aliases_on_load()
    test_get_many_reports_faces_as_found()
    print("test_cards_dfc: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
