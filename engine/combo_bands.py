#!/usr/bin/env python3
"""Which band a Commander Spellbook combo falls in, v0: can it win the game?

Why this exists (repair plan WS5 T1 item 6, diagnosis RC2/RC4): deck_plan used
to ship EVERY Spellbook variant in a deck as a pilot line, and the shim steers
tutors and casting toward pilot lines at the top value (8). 168 of the 238
lines shipped to the 32 cEDH pod decks produce no win at all, only resources
("Hullbreaker Horror + Sol Ring": infinite colorless mana and storm count), so
about 70% of the agent's combo casts and tutor targets went to engines with no
payoff. This module is the ONE classifier that separates the lines that end a
game from the ones that only generate resources. deck_plan (the pilot) imports
it now; WS8 extends it to v1 (five bands, an explicit map of every feature,
expert overrides) and the product imports the same module then.

Bands in v0:
  finisher  a feature that ends the game with the listed pieces: the lenient
            win set of studies/diagnosis_2026-09/verify/resource_lines/
            classify.py. "Win the game"; opponents lose the game; infinite or
            near-infinite damage, life loss or mill aimed at opponents;
            infinite combat phases; infinite hasty tokens or copies; infinite
            power ("infinitely large", "infinite power").
  lock      the table cannot act ("Lock", infinite turns, "opponents can't
            cast spells", mass land denial). Strong, but no win on its own.
  engine    resources only: mana, ETB/LTB, untaps, storm count, draw, tokens
            without haste, triggers, blinks, counters, recursion.
  other     anything v0 does not recognise (board wipes, "Draw the game",
            protection). Never a finisher: an unknown feature must not steer
            the pilot. v1 maps every feature by name and adds a test that
            fails on an unmapped one; v0 only guarantees the win set.

A variant takes the strongest band any of its features has (finisher > lock);
it is "engine" only when EVERY feature is a resource, otherwise "other".
is_win_band() is True for finisher only; deck_plan ships exactly those lines
as `plan.lines` (pursuit, value 8) and all lines as `plan.threatLines`.

Judgement calls, recorded so v1 can revisit them with evidence:
- Damage, life loss or mill to ALL players (the pilot included) is not a
  finisher: it kills the pilot too, a draw at best.
- Infinite +1/+1 counters without haste is an engine here, as in the
  diagnosis classifier the repair plan's figures come from (a big creature
  still has to connect; the same counters on a hasty token are a finisher).
- Infinite turns is a lock, not a finisher: it wins eventually but not with
  the listed pieces this turn. WS8's band "Lock, extra turns or extra combats"
  will hold it; infinite combat phases stays a finisher, as the plan says.
- Card count only rejects a variant with no pieces. It does not weaken a
  win: a one-card variant that wins is still a finisher.

Stdlib only, like the rest of engine/.

CLI:
    py engine/combo_bands.py "Win the game" "Infinite colorless mana"
    py engine/combo_bands.py --cache       # band counts over combo_cache.json
"""
from __future__ import annotations

import re
import sys
from collections import Counter

VERSION = 0
BANDS = ("finisher", "lock", "engine", "other")
WIN_BANDS = frozenset({"finisher"})

# Rules are matched against the casefolded feature name. Order inside a list
# does not matter; the band order (finisher, lock, engine) does.
_FINISHER = [
    re.compile(r"^win the game\b"),
    # "Each opponent loses the game", "Target opponent loses the game",
    # "Target player loses the game", "Each opponent with an even life total
    # loses the game". Never the pilot's own loss.
    re.compile(r"^(?:each|target) (?:opponent|player)\b.*\bloses the game$"),
    re.compile(r"^(?:near-)?infinite (?:combat )?damage"
               r"(?: to (?:one opponent|each opponent|target player|any target|most opponents))?$"),
    re.compile(r"^(?:near-)?infinite lifeloss"
               r"(?: for (?:target opponent|each opponent|up to \w+ target opponents))?$"),
    re.compile(r"^(?:near-)?infinite mill(?: for (?:target opponent|each opponent))?$"),
    re.compile(r"^exile (?:each opponent's|target opponent's) library$"),
    re.compile(r"^(?:near-)?infinite combat phases$"),
    # Hasty tokens or copies: "Infinite creature tokens with haste", "Infinite
    # copies of creatures you control with haste", "Infinite +1/+1 counters
    # on a creature token with haste".
    re.compile(r"^(?:near-)?infinite\b.*\bwith haste$"),
    re.compile(r"^(?:near-)?infinitely (?:large|powerful)\b"),
    re.compile(r"^infinite power\b"),
    re.compile(r"\bthat are infinitely large$"),
]

_LOCK = [
    re.compile(r"^lock$"),
    re.compile(r"^(?:near-)?infinite turns$"),
    re.compile(r"^mass land denial$"),
    re.compile(r"^(?:opponents|players|creatures|most creatures) "
               r"(?:can't|can only|skip|shuffle|put all cards)\b"),
    re.compile(r"^nobody can activate\b"),
    re.compile(r"^each opponent shuffles their hand\b"),
    re.compile(r"^you control one opponent\b"),
    re.compile(r"^(?:counter|exile) all\b.*\b(?:spells|instants and sorceries|copies)\b"),
    re.compile(r"\bspells opponents cast\b.*\bare countered$"),
    re.compile(r"^activated abilities\b.*\bcan't be activated$"),
    re.compile(r"^(?:you can't be attacked|most creatures can't attack you)$"),
]

_ENGINE = [
    re.compile(r"\bmana\b"),
    re.compile(r"\b(?:etb|ltb)\b"),
    re.compile(r"\buntap\b"),
    re.compile(r"\bstorm count\b"),
    re.compile(r"\b(?:card draw|looting|rummaging|scry \d|surveil)\b"),
    re.compile(r"\btriggers?\b"),
    re.compile(r"\blifegain\b"),
    re.compile(r"\bblinking\b"),
    re.compile(r"\btokens?\b"),
    re.compile(r"\bself-mill\b"),
    # +1/+1, charge, energy, radiation counters and proliferate. Not -1/-1
    # counters on opponents' creatures: that is removal, so it stays "other".
    re.compile(r"^(?:near-)?infinite (?:proliferate|(?:\+1/\+1|charge|energy|radiation) "
               r"counters)\b"),
    re.compile(r"\bcommander casts\b"),
    re.compile(r"\bcopies\b"),
    re.compile(r"\brecursion\b"),
    re.compile(r"\bcasts? of instants?\b"),
    re.compile(r"\bplaneswalker activations\b|\bactivations of most planeswalkers\b"),
    re.compile(r"\bventures into the dungeon\b"),
    re.compile(r"\bcascade\b"),
    re.compile(r"^exile your library\b"),
    re.compile(r"^arrange your library\b"),
    re.compile(r"^cast (?:a subset of|any) spells?\b"),
    re.compile(r"^manifest your entire library$"),
    re.compile(r"^put (?:all|most|a selection)\b.*\bfrom your (?:library|hand)\b"),
    re.compile(r"^return (?:all|some)\b.*\bfrom (?:your|all) graveyards?\b"),
    re.compile(r"^phase out any number of creatures\b"),
]


def _norm(feature: str) -> str:
    # Spellbook spells "Infnite" once; fold it rather than miss the feature.
    s = " ".join(str(feature or "").casefold().split())
    return s.replace("infnite", "infinite")


def feature_band(feature: str) -> str:
    """The band of one Spellbook feature name."""
    f = _norm(feature)
    if not f:
        return "other"
    for band, rules in (("finisher", _FINISHER), ("lock", _LOCK), ("engine", _ENGINE)):
        if any(r.search(f) for r in rules):
            return band
    return "other"


def _features(variant) -> list[str]:
    """Feature names from a slim variant ("produces": [str]) or a raw
    Spellbook record ("produces": [{"feature": {"name": str}}])."""
    out: list[str] = []
    for p in (variant or {}).get("produces") or []:
        if isinstance(p, dict):
            p = (p.get("feature") or {}).get("name") or p.get("name")
        if p:
            out.append(str(p))
    return out


def _pieces(variant) -> int:
    v = variant or {}
    if v.get("cards") is not None:
        return len(v.get("cards") or [])
    return len([u for u in v.get("uses") or [] if u.get("card")])


def classify(variant) -> dict:
    """{"band", "basis": [the features that set it], "pieces": n, "version": 0}."""
    feats = _features(variant)
    n = _pieces(variant)
    if n == 0 or not feats:
        return {"band": "other", "basis": [], "pieces": n, "version": VERSION}
    by = {f: feature_band(f) for f in feats}
    for band in ("finisher", "lock"):
        hit = [f for f in feats if by[f] == band]
        if hit:
            return {"band": band, "basis": hit, "pieces": n, "version": VERSION}
    if all(b == "engine" for b in by.values()):
        return {"band": "engine", "basis": feats, "pieces": n, "version": VERSION}
    return {"band": "other", "basis": [f for f in feats if by[f] == "other"],
            "pieces": n, "version": VERSION}


def band(variant) -> str:
    return classify(variant)["band"]


def is_win_band(variant) -> bool:
    """True when the variant can end the game with its own pieces (finisher)."""
    return band(variant) in WIN_BANDS


def _cache_report() -> int:
    import json
    from pathlib import Path
    import combos
    try:
        cache = json.loads(Path(combos.CACHE_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"no combo cache at {combos.CACHE_PATH} ({e})")
        return 1
    feats: Counter = Counter()
    bands: Counter = Counter()
    for entry in cache.values():
        if not isinstance(entry, dict):
            continue
        for v in entry.get("included") or []:
            bands[band(v)] += 1
            for f in _features(v):
                feats[(feature_band(f), f)] += 1
    print("included variants by band:", dict(bands))
    per = Counter(b for b, _ in feats)
    print("distinct features by band:", dict(per))
    for (b, f), n in sorted(feats.items()):
        if b in ("finisher", "other"):
            print(f"  {b:8s} {n:5d}  {f}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--cache":
        return _cache_report()
    for f in argv:
        print(f"{feature_band(f):8s} {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
