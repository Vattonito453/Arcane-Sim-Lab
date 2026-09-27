#!/usr/bin/env python3
"""Plan version 2, the tutoring hotfix's data (repair plan WS5 T1 item 6,
Appendix B task 20, and task 17's line-name mapping).

What this proves:
  1. Version 1 (the default, and MTG_PLAN_VERSION unset) is byte-identical to
     the plans built before versions existed:
       - in one process, against the pre-hotfix deck_plan.py (commit REF) read
         from git: the synthetic decks and every bundled deck (real card and
         combo caches), synergy off and on. Exact under any hash seed and any
         Python version, because both modules see the same seed. Skipped, and
         said so, without git;
       - on the synthetic decks, against a golden file written from REF with
         `--write-golden`, so the check still holds on a clone without the
         commit. See "Hash seed" for the one field compared up to tie order.
  2. Version 2, per the plan JSON contract shared with the shim:
       - Thassa's Oracle + Demonic Consultation stays in plan.lines;
       - Hullbreaker Horror + Sol Ring moves to threatLines only, and its
         pieces lose the blanket value 8;
       - Magda + Clock of Omens + Liquimetal Torque leaves plan.lines. This is
         documented and intended: Spellbook gives it no win feature, and it is
         the steer that overrode Portal to Phyrexia in 33 of 47 cases. WS8
         restores it as an expert-banded finisher with steer: false;
       - a Kess-like deck gets graveyardTargets for its reanimation targets
         and its castable-from-graveyard spells, and NOT for Sol Ring;
       - self-loss (Pact of Negation) and saboteur text are no longer
         finishers; opponent-loss and poison text still are;
       - the opponent-facing threat list is version 1's;
       - line and target names are the names Forge uses, from the Forge index
         when it is built and from the fallbacks when it is not;
       - the fix flags are all true and planVersion is 2.

Synthetic card facts and combo lines (feature strings copied from real
Spellbook records); a temp MTG_DATA_DIR, so the tracked plan_feedback.json is
never written; no network, no Forge.

Hash seed: version 1 sorts the threat list by weight, then power, and leaves
ties in set-iteration order, which follows the process's string hash (its
seed, and its function: CPython 3.11 moved str hashing from siphash24 to
siphash13, so even PYTHONHASHSEED=0 differs across versions). That was true
before this change too, and version 1 is frozen, so it stays. The golden
file therefore stores, and the test compares, each threat list with every
run of equal (plan weight, power) sorted by name (canonical_threat): every
tie group lies inside one such run, so tie order cannot fail the check,
while a card out of weight or power order still does. Every other field is
compared byte for byte.
Order inside a run is proved by the exact in-process comparison against REF.
The test also rebuilds the golden's plans under three fixed hash seeds in
child processes, so a seed-dependent field fails here on every run instead
of on one machine. Version 2 breaks the ties by name and is reproducible.

Run: py engine/tests/test_plan_hotfix.py
     py engine/tests/test_plan_hotfix.py --write-golden   # regenerate from REF
"""
from __future__ import annotations

import copy
import glob
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))
import cards  # noqa: E402
import combos  # noqa: E402
import deck_plan  # noqa: E402
import forge_index  # noqa: E402

# main before the hotfix. Version 1 is frozen at this commit's behaviour: a
# DELIBERATE change to version-1 plans must move REF, regenerate the golden
# file and say why in the commit.
REF = "ef80299"
GOLDEN = ENGINE / "tests" / "fixtures" / "plan_hotfix_v1_golden.json"
# Child-process hash seeds for the golden check (see "Hash seed").
SEEDS = ("1", "2", "3")

_REAL_GET_MANY = cards.get_many
_REAL_COMBOS = combos.combos_for_dck
_REAL_LOAD_INDEX = forge_index.load_index


def creature(text: str, cmc: int, power: str = "2", sub: str = "Wizard") -> dict:
    return {"oracle_text": text, "type_line": f"Creature — {sub}", "cmc": cmc,
            "power": power, "toughness": power}


FACTS = {
    # --- the cEDH-style deck ------------------------------------------------
    "Tymna Toy": {"oracle_text": "Lifelink", "type_line": "Legendary Creature — Cleric",
                  "cmc": 2, "power": "2", "toughness": "2"},
    "Thassa's Oracle": creature("When this creature enters, look at the top X cards of your "
                                "library. If X is greater than or equal to the number of cards "
                                "in your library, you win the game.", 2, "1", "Merfolk"),
    "Demonic Consultation": {"oracle_text": "Name a card. Exile the top six cards of your "
                                            "library, then reveal cards until you reveal the "
                                            "named card.", "type_line": "Instant", "cmc": 1},
    "Tainted Pact": {"oracle_text": "Exile the top card of your library. Repeat this until "
                                    "you choose to stop.", "type_line": "Instant", "cmc": 2},
    "Hullbreaker Horror": creature("Flash\nThis spell can't be countered.\nWhenever you cast a "
                                   "spell, return target nonland permanent to its owner's hand.",
                                   7, "7", "Kraken Horror"),
    "Sol Ring": {"oracle_text": "{T}: Add {C}{C}.", "type_line": "Artifact", "cmc": 1},
    "Mechanized Production": {"oracle_text": "At the beginning of your upkeep, create a copy of "
                                             "enchanted artifact. Then if you control eight "
                                             "artifacts with the same name, you win the game.",
                              "type_line": "Enchantment — Aura", "cmc": 4},
    # Forge names this adventure card by its creature face; Spellbook by both.
    "James, Wandering Dad": creature("Vigilance", 5, "4", "Human Scientist"),
    # Self-loss text: a counterspell, not a finisher (v1 scored it 8).
    "Pact of Negation": {"oracle_text": "Counter target spell.\nAt the beginning of your next "
                                        "upkeep, pay {3}{U}{U}. If you don't, you lose the "
                                        "game.", "type_line": "Instant", "cmc": 0},
    # Saboteur text: card advantage, not a finisher (v1 scored it 8).
    "Ragavan Toy": creature("Whenever this creature deals combat damage to a player, "
                            "exile the top card of that player's library.", 1, "2", "Monkey"),
    # Opponent-loss and poison text stay finishers in version 2.
    "Door Toy": {"oracle_text": "{T}: Target player loses the game.", "type_line": "Artifact",
                 "cmc": 5},
    "Poison Toy": creature("Toxic 1 (A player with ten or more poison counters loses the "
                           "game.)", 2, "1", "Phyrexian"),
    "Island": {"oracle_text": "({T}: Add {U}.)", "type_line": "Basic Land — Island", "cmc": 0},
    # --- the Magda deck -----------------------------------------------------
    "Magda, Brazen Outlaw": {"oracle_text": "Other Dwarves you control get +1/+0.",
                             "type_line": "Legendary Creature — Dwarf Berserker", "cmc": 2,
                             "power": "2", "toughness": "1"},
    "Clock of Omens": {"oracle_text": "Tap two untapped artifacts you control: Untap target "
                                      "artifact.", "type_line": "Artifact", "cmc": 4},
    "Liquimetal Torque": {"oracle_text": "{T}: Add {C}.\n{T}: Target nonland permanent becomes "
                                         "an artifact until end of turn.",
                          "type_line": "Artifact", "cmc": 2},
    "Portal to Phyrexia": {"oracle_text": "When this artifact enters, each opponent sacrifices "
                                          "three creatures.", "type_line": "Artifact",
                           "cmc": 9},
    "Narset's Reversal": {"oracle_text": "Copy target instant or sorcery spell, then return it "
                                         "to its owner's hand.", "type_line": "Instant",
                          "cmc": 2},
    "Expansion // Explosion": {"oracle_text": "Copy target instant or sorcery spell.",
                               "type_line": "Instant // Instant", "cmc": 2, "layout": "split"},
    "Mountain": {"oracle_text": "({T}: Add {R}.)", "type_line": "Basic Land — Mountain",
                 "cmc": 0},
    # --- the Kess-like deck -------------------------------------------------
    "Kess, Dissident Mage": {"oracle_text": "Flying\nDuring each of your turns, you may cast an "
                                            "instant or sorcery spell from your graveyard.",
                             "type_line": "Legendary Creature — Human Wizard", "cmc": 4,
                             "power": "3", "toughness": "4"},
    "Reanimate": {"oracle_text": "Put target creature card from a graveyard onto the "
                                 "battlefield under your control.",
                  "type_line": "Sorcery", "cmc": 1},
    "Animate Dead": {"oracle_text": "Enchant creature card in a graveyard\nWhen this Aura "
                                    "enters, return enchanted creature card to the "
                                    "battlefield under your control.",
                     "type_line": "Enchantment — Aura", "cmc": 2},
    "Unburial Rites": {"oracle_text": "Return target creature card from your graveyard to the "
                                      "battlefield.\nFlashback {3}{W}",
                       "type_line": "Sorcery", "cmc": 4},
    "Archon of Cruelty": creature("Flying\nWhenever this creature enters or attacks, target "
                                  "opponent sacrifices a creature.", 8, "6", "Archon"),
    "Stitcher's Supplier": creature("When this creature enters or dies, mill three cards.", 1,
                                    "1", "Zombie"),
    "Blasphemous Act": {"oracle_text": "This spell costs {1} less to cast for each creature on "
                                       "the battlefield. It deals 13 damage to each creature.",
                        "type_line": "Sorcery", "cmc": 9},
    "Faithless Looting": {"oracle_text": "Draw two cards, then discard two cards.\n"
                                         "Flashback {2}{R}", "type_line": "Sorcery", "cmc": 1},
    "Brainstorm": {"oracle_text": "Draw three cards, then put two cards from your hand on top "
                                  "of your library.", "type_line": "Instant", "cmc": 1},
    "Entomb": {"oracle_text": "Search your library for a card, put that card into your "
                              "graveyard, then shuffle.", "type_line": "Instant", "cmc": 1},
    "Unearth Toy": creature("Unearth {2}{B}", 3, "3", "Zombie"),
    # Grants flashback to ANOTHER card: not a graveyard card itself.
    "Snapcaster Toy": creature("Flash\nWhen this creature enters, target instant or sorcery "
                               "card in your graveyard gains flashback until end of turn.", 2),
    "Swamp": {"oracle_text": "({T}: Add {B}.)", "type_line": "Basic Land — Swamp", "cmc": 0},
    # --- a deck that does not reanimate --------------------------------------
    "Plain Commander": {"oracle_text": "Vigilance", "type_line": "Legendary Creature — Soldier",
                        "cmc": 3, "power": "3", "toughness": "3"},
    # --- a commander that grants flashback (Lier-style) ------------------------
    "Lier Toy": {"oracle_text": "Instant and sorcery cards in your graveyard have flashback.",
                 "type_line": "Legendary Creature — Human Wizard", "cmc": 5,
                 "power": "2", "toughness": "4"},
    # --- an unconverted DFC spelling in the deck itself. Cached before the
    # cache stored layouts (no "layout" key), so only the index can place it.
    "Birgi, God of Storytelling // Harnfel, Horn of Bounty": {
        "oracle_text": "Whenever you cast your hundredth spell this game, you win the game.",
        "type_line": "Legendary Creature — God // Legendary Artifact", "cmc": 3,
        "power": "3", "toughness": "3"},
    # --- a transform card the cache knows the layout of (forge_namer step 2) ---
    "Delver of Secrets // Insectile Aberration": {
        "oracle_text": "At the beginning of your upkeep, look at the top card of your library.",
        "type_line": "Creature — Human Wizard // Creature — Human Insect", "cmc": 1,
        "power": "1", "toughness": "1", "layout": "transform"},
    # --- the Birgi deck: line pieces whose deck spelling is Spellbook's ------
    "Grinning Ignus": creature("{R}, Return this creature to its owner's hand: Add {C}{C}{R}. "
                               "Activate only as a sorcery.", 3, "2", "Elemental"),
    "Underworld Breach": {"oracle_text": "Each nonland card in your graveyard has escape. The "
                                         "escape cost is equal to the card's mana cost plus "
                                         "exile three other cards from your graveyard.\nAt the "
                                         "beginning of the end step, sacrifice this enchantment.",
                          "type_line": "Enchantment", "cmc": 2},
    "Burning Inquiry": {"oracle_text": "Each player draws three cards, then discards three "
                                       "cards at random.", "type_line": "Sorcery", "cmc": 1},
    # --- a synergy deck whose payoff is a transform card spelled "A // B" ------
    **{f"Token Toy {c}": creature("When this creature enters, create a 1/1 white Soldier "
                                  "creature token.", 2, "1", "Soldier") for c in "ABCDE"},
    "Anthem Front // Anthem Back": {"oracle_text": "Creatures you control get +1/+1.",
                                    "type_line": "Enchantment // Enchantment", "cmc": 3,
                                    "layout": "transform"},
    # --- look like reanimation, reanimate nothing (review 2026-09-27) ---------
    "Manifest Toy": creature("Whenever this creature enters or attacks, manifest dread. (Look "
                             "at the top two cards of your library. Put one onto the "
                             "battlefield face down as a 2/2 creature and the other into your "
                             "graveyard. Turn it face up any time for its mana cost if it's a "
                             "creature card.)", 4, "3", "Beast"),
    "Wave Toy": {"oracle_text": "Reveal the top X cards of your library. You may put any number "
                                "of permanent cards with mana value X or less from among them "
                                "onto the battlefield. Then put all cards revealed this way that "
                                "weren't put onto the battlefield into your graveyard.",
                 "type_line": "Sorcery", "cmc": 3},
    "Evoker Toy": creature("{G}, Discard a creature card: Return target land card from your "
                           "graveyard to the battlefield tapped.", 2, "1", "Elf Druid"),
    # --- capped reanimation, and the keywords added after review --------------
    "Reclaim Toy": {"oracle_text": "Return target permanent card with mana value 3 or less "
                                   "from your graveyard to the battlefield.",
                    "type_line": "Sorcery", "cmc": 3},
    "Harmonize Toy": {"oracle_text": "Search your library for a creature card with mana value X "
                                     "or less, put it onto the battlefield, then shuffle.\n"
                                     "Harmonize {X}{G}{G}{G}{G} (You may cast this card from "
                                     "your graveyard for its harmonize cost.)",
                      "type_line": "Sorcery", "cmc": 2},
    "Dredge Toy": creature("Flying\nDredge 3 (If you would draw a card, you may mill three "
                           "cards instead. If you do, return this card from your graveyard to "
                           "your hand.)", 3, "1", "Imp"),
    # --- a modal spell with a land back: an instant in the graveyard (Kess) ---
    "Stupor Toy // Springs Toy": {"oracle_text": "Return target spell or nonland permanent an "
                                                 "opponent controls to its owner's hand.",
                                  "type_line": "Instant // Land", "cmc": 3},
}

DECKS = {
    "hotfix_cedh": ("Tymna Toy", ["Thassa's Oracle", "Demonic Consultation", "Tainted Pact",
                                  "Hullbreaker Horror", "Sol Ring", "Mechanized Production",
                                  "James, Wandering Dad", "Pact of Negation", "Ragavan Toy",
                                  "Door Toy", "Poison Toy", "Island", "Island"]),
    "hotfix_magda": ("Magda, Brazen Outlaw", ["Clock of Omens", "Liquimetal Torque",
                                              "Portal to Phyrexia", "Narset's Reversal",
                                              "Expansion // Explosion", "Sol Ring",
                                              "Mountain"]),
    "hotfix_kess": ("Kess, Dissident Mage", ["Reanimate", "Animate Dead", "Unburial Rites",
                                             "Archon of Cruelty", "Hullbreaker Horror",
                                             "Stitcher's Supplier", "Sol Ring",
                                             "Blasphemous Act", "Faithless Looting",
                                             "Brainstorm", "Entomb", "Unearth Toy",
                                             "Snapcaster Toy", "Stupor Toy // Springs Toy",
                                             "Island", "Swamp"]),
    "hotfix_plain": ("Plain Commander", ["Archon of Cruelty", "Faithless Looting",
                                         "Brainstorm", "Sol Ring", "Swamp"]),
    "hotfix_lier": ("Lier Toy", ["Brainstorm", "Blasphemous Act", "Archon of Cruelty",
                                 "Island"]),
    "hotfix_unconverted": ("Plain Commander", [
        "Birgi, God of Storytelling // Harnfel, Horn of Bounty", "Sol Ring", "Island"]),
    "hotfix_birgi": ("Plain Commander", [
        "Birgi, God of Storytelling // Harnfel, Horn of Bounty", "Grinning Ignus",
        "Underworld Breach", "Burning Inquiry", "Mountain"]),
    "hotfix_tokens": ("Plain Commander", [
        *[f"Token Toy {c}" for c in "ABCDE"], "Anthem Front // Anthem Back", "Swamp"]),
    "hotfix_fakes": ("Plain Commander", ["Manifest Toy", "Wave Toy", "Evoker Toy",
                                         "Archon of Cruelty", "Hullbreaker Horror", "Swamp"]),
    "hotfix_capped": ("Plain Commander", ["Reclaim Toy", "Archon of Cruelty",
                                          "Thassa's Oracle", "Harmonize Toy", "Dredge Toy",
                                          "Sol Ring", "Swamp"]),
}


def line(cards_: list[str], produces: list[str]) -> dict:
    return {"cards": cards_, "produces": produces}


# Real Spellbook variants (engine/combo_cache.json), per synthetic deck.
ORACLE_CONSULT = line(["Demonic Consultation", "Thassa's Oracle"],
                      ["Exile your library", "Win the game"])
TAINTED_PACT = line(["Tainted Pact", "Thassa's Oracle"], ["Win the game"])
HULLBREAKER = line(["Hullbreaker Horror", "Sol Ring"],
                   ["Infinite colorless mana", "Infinite storm count"])
JAMES = line(["James, Wandering Dad // Follow Him", "Mechanized Production"], ["Win the game"])
MAGDA = line(["Magda, Brazen Outlaw", "Clock of Omens", "Liquimetal Torque"],
             ["Infinite artifact ETB", "Infinite artifact tokens",
              "Infinite tapped Treasure tokens",
              "Put all artifact cards and a subset of creature cards from your library onto "
              "the battlefield"])
EXPLOSION = line(["Narset's Reversal", "Expansion // Explosion"], ["Infinite magecraft triggers"])
BIRGI = "Birgi, God of Storytelling // Harnfel, Horn of Bounty"
BIRGI_IGNUS = line([BIRGI, "Grinning Ignus"],
                   ["Infinite creature ETB", "Infinite creature LTB", "Infinite storm count"])
BIRGI_BREACH = line([BIRGI, "Underworld Breach", "Burning Inquiry"],
                    ["Infinite draw triggers for all players", "Infinite self-mill",
                     "Near-infinite mill", "Near-infinite self-discard triggers",
                     "Near-infinite storm count"])

COMBOS = {
    "hotfix_cedh": [ORACLE_CONSULT, TAINTED_PACT, HULLBREAKER, JAMES],
    "hotfix_magda": [MAGDA, EXPLOSION],
    "hotfix_kess": [HULLBREAKER],
    "hotfix_birgi": [BIRGI_IGNUS, BIRGI_BREACH],
}


def fake_get_many(names, fetch=False):
    """Keyed like the real cache (by the name asked for); unknown names absent."""
    return {n: FACTS[n] for n in names if n in FACTS}


def fake_combos(path, fetch=False):
    included = COMBOS.get(Path(path).stem)
    if included is None:
        return {"identity": "", "included": [], "almost_included": []}
    return {"identity": "", "included": [dict(v, cards=list(v["cards"]),
                                              produces=list(v["produces"]))
                                         for v in included],
            "almost_included": []}


def fake_index() -> forge_index.ForgeIndex:
    """What Forge 2.0.13's index says about these names (layouts only)."""
    entries: dict[str, dict] = {}
    for n in FACTS:
        if " // " not in n:
            entries[n] = {"mode": None, "faces": [n], "types": FACTS[n]["type_line"]}
    entries["James, Wandering Dad"] = {"mode": "Adventure",
                                       "faces": ["James, Wandering Dad", "Follow Him"]}
    entries["Expansion // Explosion"] = {"mode": "Split", "faces": ["Expansion", "Explosion"]}
    entries["Delver of Secrets"] = {"mode": "DoubleFaced",
                                    "faces": ["Delver of Secrets", "Insectile Aberration"]}
    entries["Birgi, God of Storytelling"] = {"mode": "Modal",
                                             "faces": ["Birgi, God of Storytelling",
                                                       "Harnfel, Horn of Bounty"]}
    return forge_index.ForgeIndex(Path("."), {"forge_version": "test"}, entries, {})


def write_decks(d: Path) -> list[Path]:
    out = []
    for name, (cmdr, main) in DECKS.items():
        p = d / f"{name}.dck"
        body = ["[metadata]", f"Name={name}", "[Commander]", f"1 {cmdr}", "[Main]"]
        body += [f"1 {n}" for n in main]
        p.write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(p)
    return out


def synthetic(index=None) -> None:
    cards.get_many = fake_get_many
    combos.combos_for_dck = fake_combos
    forge_index.load_index = lambda version=None: index


def real() -> None:
    cards.get_many = _REAL_GET_MANY
    combos.combos_for_dck = _REAL_COMBOS
    forge_index.load_index = lambda version=None: None   # v1 never reads it


def reference_module() -> types.ModuleType | None:
    """deck_plan.py as it was at REF, or None when git or the commit is absent."""
    try:
        src = subprocess.run(["git", "-C", str(ENGINE), "show", f"{REF}:engine/deck_plan.py"],
                             capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if src.returncode != 0 or "def build_plan" not in src.stdout:
        return None
    mod = types.ModuleType("deck_plan_ref")
    mod.__file__ = str(ENGINE / "deck_plan.py")
    exec(compile(src.stdout, f"{REF}:engine/deck_plan.py", "exec"), mod.__dict__)
    return mod


def dumps(plans: dict) -> str:
    return json.dumps(plans, indent=2)       # exactly as run_sim writes it


def power(n: str) -> int:
    """deck_plan's _pow on the synthetic facts: a creature's printed power."""
    f = FACTS.get(n) or {}
    if "creature" not in (f.get("type_line") or "").lower():
        return 0
    try:
        return int(f.get("power") or 0)
    except (TypeError, ValueError):
        return 0


def canonical_threat(plans: dict) -> dict:
    """A deep copy of {"decks": {name: plan}} whose threat lists have every
    maximal run of equal (plan weight, power) sorted by name (see "Hash
    seed").

    Sound: version 1 sorts by (weight, power) and a tie group shares both, so
    it is contiguous and inside one run (the plan's weights map drops weight
    1, but equal internal weights still read equal there). Permuting it moves
    no run boundary, so two lists that differ only in tie order map to the
    same list. A card placed out of weight or power order changes the run
    sequence and still fails."""
    out = copy.deepcopy(plans)
    for plan in out["decks"].values():
        weight = plan.get("weights") or {}

        def key(n: str) -> tuple[int, int]:
            return weight.get(n, 0), power(n)

        runs: list[list[str]] = []
        for n in plan["threat"]:
            if runs and key(n) == key(runs[-1][-1]):
                runs[-1].append(n)
            else:
                runs.append([n])
        plan["threat"] = [n for run in runs for n in sorted(run)]
    return out


def golden_text(plans: dict) -> str:
    """The golden file's exact bytes for these version-1 plans."""
    return dumps(canonical_threat(plans)) + "\n"


def write_golden(tmp: Path) -> None:
    ref = reference_module()
    if ref is None:
        sys.exit(f"--write-golden needs git and commit {REF}")
    synthetic()
    payload = golden_text(ref.build_plans(write_decks(tmp)))
    with open(GOLDEN, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload)
    print(f"wrote {GOLDEN} from {REF}:engine/deck_plan.py")


def emit_v1(tmp: Path) -> None:
    """Child mode for the seed sweep: this process's golden text on stdout."""
    synthetic()
    sys.stdout.write(golden_text(deck_plan.build_plans(write_decks(tmp))))


def seed_sweep() -> list[str]:
    """The golden text built under each of SEEDS, one child process each."""
    outs = []
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        env.pop("MTG_PLAN_VERSION", None)
        env.pop("MTG_PLAN_FIX", None)
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--emit-v1"],
                              capture_output=True, env=env, timeout=120)
        assert proc.returncode == 0, (seed, proc.stderr.decode("utf-8", "replace")[-800:])
        outs.append(proc.stdout.decode("utf-8").replace("\r\n", "\n"))
    return outs


def by_cards(lines: list[dict]) -> list[list[str]]:
    return [ln["cards"] for ln in lines]


def main() -> None:
    saved = {k: os.environ.get(k) for k in ("MTG_DATA_DIR", "MTG_PLAN_VERSION",
                                            "MTG_PLAN_FIX", "MTG_PLAN_FEEDBACK_APPLY")}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        data = tmp / "data"
        data.mkdir()
        os.environ["MTG_DATA_DIR"] = str(data)       # plan_feedback.note_tags writes here
        os.environ.pop("MTG_PLAN_FEEDBACK_APPLY", None)
        os.environ.pop("MTG_PLAN_VERSION", None)
        os.environ.pop("MTG_PLAN_FIX", None)
        try:
            if "--write-golden" in sys.argv:
                write_golden(tmp)
                return
            if "--emit-v1" in sys.argv:
                emit_v1(tmp)
                return
            run(tmp)
        finally:
            real()
            forge_index.load_index = _REAL_LOAD_INDEX
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def run(tmp: Path) -> None:
    tracked = ENGINE / "plan_feedback.json"
    before = tracked.stat().st_mtime_ns if tracked.exists() else None
    try:
        checks(tmp)
    finally:
        after = tracked.stat().st_mtime_ns if tracked.exists() else None
        assert before == after, "the tracked engine/plan_feedback.json was written"


def checks(tmp: Path) -> None:
    decks = write_decks(tmp)
    path = {p.stem: p for p in decks}

    # ------------------------------------------------ 1. version 1 unchanged --
    synthetic()
    v1_plans = deck_plan.build_plans(decks)
    v1_text = dumps(v1_plans)
    assert GOLDEN.is_file(), f"missing {GOLDEN}: run with --write-golden"
    golden = GOLDEN.read_text(encoding="utf-8")
    assert golden_text(v1_plans) == golden, \
        "version-1 plans moved against the pre-hotfix golden file"
    # The golden is stored canonical, so canonicalising it again is a no-op.
    assert golden_text(json.loads(golden)) == golden
    for seed, text in zip(SEEDS, seed_sweep()):
        assert text == golden, f"version-1 plans under PYTHONHASHSEED={seed} moved against " \
                               f"the golden file: a field other than threat tie order " \
                               f"depends on the hash seed"
    assert dumps(deck_plan.build_plans(decks, plan_version=1)) == v1_text
    os.environ["MTG_PLAN_VERSION"] = "1"
    assert dumps(deck_plan.build_plans(decks)) == v1_text
    os.environ["MTG_PLAN_VERSION"] = ""
    assert dumps(deck_plan.build_plans(decks)) == v1_text
    os.environ.pop("MTG_PLAN_VERSION", None)
    _, lone = deck_plan.build_plan(path["hotfix_cedh"])
    assert lone == json.loads(v1_text)["decks"]["hotfix_cedh"], "build_plan defaults to v1"
    for plan in json.loads(v1_text)["decks"].values():
        assert not {"planVersion", "threatLines", "fix"} & set(plan), sorted(plan)
        assert set(plan["search"]) == {"targets", "context"}, plan["search"]
    print(f"  version 1 (default, flag unset, empty or 1) matches the pre-hotfix golden "
          f"(threat compared up to tie order, every other field byte for byte), here and "
          f"under PYTHONHASHSEED {', '.join(SEEDS)}: OK")

    ref = reference_module()
    bundled = sorted(glob.glob(str(ENGINE / "decks" / "*.dck")))
    if ref is None:
        print(f"  in-process comparison against {REF} SKIPPED: git or the commit is "
              f"unavailable (the synthetic golden above still holds)")
    else:
        # Same process, same hash seed: exact, tie order included.
        for kw in ({}, {"synergy": True}):
            want = dumps(ref.build_plans(decks, **kw))
            assert want == dumps(deck_plan.build_plans(decks, **kw)), kw
            assert want == dumps(deck_plan.build_plans(decks, plan_version=1, **kw)), kw
        assert dumps(ref.build_plans(decks)) == v1_text
        print(f"  version 1 byte-identical to {REF} on the {len(decks)} synthetic decks "
              f"(same process, tie order included, synergy off and on): OK")
        real()
        diffs = [p for p in bundled
                 if dumps(ref.build_plans([p])) != dumps(deck_plan.build_plans([p]))
                 or dumps(ref.build_plans([p], synergy=True))
                 != dumps(deck_plan.build_plans([p], synergy=True))]
        assert not diffs, f"version 1 moved on bundled decks: {diffs}"
        print(f"  version 1 byte-identical to {REF} on all {len(bundled)} bundled decks "
              f"(real caches, synergy off and on): OK")
        synthetic()

    # The flag: 2 builds version 2 through build_plans; garbage is refused.
    os.environ["MTG_PLAN_VERSION"] = "2"
    assert deck_plan.env_plan_version() == 2
    via_env = deck_plan.build_plans([path["hotfix_cedh"]])
    assert via_env["decks"]["hotfix_cedh"]["planVersion"] == 2
    for bad in ("3", "two", "1.0"):
        os.environ["MTG_PLAN_VERSION"] = bad
        try:
            deck_plan.build_plans([path["hotfix_cedh"]])
        except ValueError:
            pass
        else:
            raise AssertionError(f"MTG_PLAN_VERSION={bad!r} must be refused")
    os.environ.pop("MTG_PLAN_VERSION", None)
    try:
        deck_plan.build_plan(path["hotfix_cedh"], plan_version=3)
    except ValueError:
        pass
    else:
        raise AssertionError("plan_version=3 must be refused")
    print("  MTG_PLAN_VERSION=2 builds version 2; 3, 'two' and '1.0' are refused: OK")

    # MTG_PLAN_FIX: the per-flag arms. Only "fix" moves; every flag is written.
    all_on = dumps(deck_plan.build_plans(decks, plan_version=2))
    flags = list(deck_plan.V2_FIX)

    def fix_of(plans: dict) -> set[tuple[str, bool]]:
        return {tuple(sorted(p["fix"].items())) for p in plans["decks"].values()}

    def without_fix(plans: dict) -> str:
        return dumps({"decks": {n: {k: v for k, v in p.items() if k != "fix"}
                                for n, p in plans["decks"].items()}})

    for raw, on in (("all", set(flags)), ("none", set()), ("tutorReach", {"tutorReach"}),
                    (" graveyarddest , TUTORREACH ", {"graveyardDest", "tutorReach"})):
        os.environ["MTG_PLAN_FIX"] = raw
        got = deck_plan.build_plans(decks, plan_version=2)
        assert fix_of(got) == {tuple(sorted((k, k in on) for k in flags))}, (raw, fix_of(got))
        assert without_fix(got) == without_fix(json.loads(all_on)), raw
        # The same arm through the parameter, which wins over the env.
        os.environ["MTG_PLAN_FIX"] = "none"
        assert fix_of(deck_plan.build_plans(decks, plan_version=2, fix=raw)) == fix_of(got)
    os.environ["MTG_PLAN_FIX"] = "all"
    assert dumps(deck_plan.build_plans(decks, plan_version=2)) == all_on
    os.environ["MTG_PLAN_FIX"] = ""
    assert dumps(deck_plan.build_plans(decks, plan_version=2)) == all_on
    for bad in ("tutorreach,bogus", "yes", ","):
        os.environ["MTG_PLAN_FIX"] = bad
        try:
            deck_plan.build_plans(decks, plan_version=2)
        except ValueError:
            pass
        else:
            raise AssertionError(f"MTG_PLAN_FIX={bad!r} must be refused")
    # An arm with no version 2 would run 0.16.0 behaviour under its label.
    os.environ["MTG_PLAN_FIX"] = "tutorReach"
    for call in (lambda: deck_plan.build_plans(decks),
                 lambda: deck_plan.build_plans(decks, plan_version=1)):
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError("MTG_PLAN_FIX with a version-1 plan must be refused")
    os.environ.pop("MTG_PLAN_FIX", None)
    try:
        deck_plan.build_plan(path["hotfix_cedh"], fix="none")
    except ValueError:
        pass
    else:
        raise AssertionError("fix= with a version-1 plan must be refused")
    assert dumps(deck_plan.build_plans(decks)) == v1_text
    print("  MTG_PLAN_FIX picks the version-2 flag arm (all, none, a list; any case), "
          "moves nothing but 'fix', and is refused when bad or with version 1: OK")

    # ------------------------------------------------------- 2. version 2 --
    v1 = json.loads(v1_text)["decks"]
    v2 = deck_plan.build_plans(decks, plan_version=2)["decks"]
    for name, plan in v2.items():
        assert next(iter(plan)) == "planVersion" and plan["planVersion"] == 2, name
        assert plan["fix"] == {"tutorReach": True, "commanderTutorZone": True,
                               "noForcedChoices": True, "graveyardDest": True}, plan["fix"]
        assert list(plan["search"]) == ["targets", "context", "graveyardTargets"], name
        assert len(plan["threatLines"]) == len(v1[name]["lines"]), name
        # Opponent-facing: the threat list is version 1's.
        assert set(plan["threat"]) >= set(v1[name]["threat"]), name
    print("  version 2 carries planVersion 2, threatLines, graveyardTargets and all four "
          "fix flags: OK")

    c1, c2 = v1["hotfix_cedh"], v2["hotfix_cedh"]
    pilot = by_cards(c2["lines"])
    assert ["Demonic Consultation", "Thassa's Oracle"] in pilot, pilot
    assert ["Tainted Pact", "Thassa's Oracle"] in pilot, pilot
    assert c2["weights"]["Thassa's Oracle"] == 8 and c2["roles"]["Thassa's Oracle"] == "combo-piece"
    assert c2["search"]["targets"]["Demonic Consultation"] == 8
    print("  Thassa's Oracle + Demonic Consultation stays in plan.lines (value 8): OK")

    threat = by_cards(c2["threatLines"])
    assert ["Hullbreaker Horror", "Sol Ring"] not in pilot, pilot
    assert ["Hullbreaker Horror", "Sol Ring"] in threat, threat
    assert c1["weights"]["Sol Ring"] == 8 and c1["search"]["targets"]["Sol Ring"] == 8
    assert c2["weights"].get("Sol Ring", 1) < 8 and c2["roles"]["Sol Ring"] != "combo-piece"
    assert c2["search"]["targets"]["Sol Ring"] == 5, c2["search"]["targets"]   # ramp tier
    assert c2["search"]["context"]["Sol Ring"] == {"hint": "ramp", "beforeRound": 5}
    assert c2["weights"]["Hullbreaker Horror"] == 4, c2["weights"]            # protection
    assert c2["search"]["targets"]["Hullbreaker Horror"] == 6                 # cmc bomb
    # ...but the table still fears them: both stay in the threat list.
    assert {"Sol Ring", "Hullbreaker Horror"} <= set(c2["threat"]), c2["threat"]
    assert set(c2["threat"]) == set(c1["threat"]) | {"James, Wandering Dad"}, \
        (sorted(c1["threat"]), sorted(c2["threat"]))
    print("  Hullbreaker Horror + Sol Ring moves to threatLines only; its pieces fall to "
          "their role tier; the threat list still names them: OK")

    m1, m2 = v1["hotfix_magda"], v2["hotfix_magda"]
    magda = ["Magda, Brazen Outlaw", "Clock of Omens", "Liquimetal Torque"]
    assert magda in by_cards(m1["lines"]) and magda not in by_cards(m2["lines"])
    assert magda in by_cards(m2["threatLines"])
    assert m2["lines"] == [], m2["lines"]          # no win line until WS8 composes one
    assert m1["search"]["targets"]["Clock of Omens"] == 8
    assert m2["search"]["targets"].get("Clock of Omens", 1) < 8, m2["search"]["targets"]
    assert m2["search"]["targets"]["Portal to Phyrexia"] >= 6
    print("  Magda + Clock of Omens + Liquimetal Torque leaves plan.lines (documented, "
          "intended; WS8 restores it as an expert finisher): OK")

    # _FINISHER: self-loss and saboteur text out; opponent-loss and poison in.
    t1, t2 = c1["search"]["targets"], c2["search"]["targets"]
    assert t1["Pact of Negation"] == 8 and t2.get("Pact of Negation", 1) < 8, (t1, t2)
    assert t1["Ragavan Toy"] == 8 and t2.get("Ragavan Toy", 1) < 8, (t1, t2)
    assert t1["Door Toy"] == t2["Door Toy"] == 8
    assert t1["Poison Toy"] == t2["Poison Toy"] == 8
    print("  Pact of Negation and saboteur text are no longer finishers; 'target player "
          "loses the game' and poison still are: OK")

    # ------------------------------------------------- graveyard targets --
    k2 = v2["hotfix_kess"]
    gy = k2["search"]["graveyardTargets"]
    assert "Sol Ring" not in gy, gy
    assert gy["Archon of Cruelty"] == 8, gy          # reanimation target, mana value 8
    assert gy["Hullbreaker Horror"] == 7, gy         # reanimation target, mana value 7
    assert "Stitcher's Supplier" not in gy, gy       # a 1-drop is not worth reanimating
    assert gy["Blasphemous Act"] == 6, gy            # Kess casts it; its search value 6
    for n in ("Brainstorm", "Entomb", "Reanimate"):
        assert gy[n] == 3, (n, gy)                    # Kess casts it; floor 3
    assert gy["Faithless Looting"] == 3 and gy["Unburial Rites"] == 3, gy   # flashback
    assert gy["Unearth Toy"] == 3, gy                 # unearth
    assert "Animate Dead" not in gy, gy               # an enchantment Kess cannot cast
    assert "Snapcaster Toy" not in gy, gy             # grants flashback, has none itself
    # In the graveyard a modal card has only its front face: an instant Kess casts.
    assert gy["Stupor Toy // Springs Toy"] == 3, gy
    assert "Kess, Dissident Mage" not in gy and "Island" not in gy and "Swamp" not in gy
    assert all(1 <= val <= 9 for val in gy.values()), gy
    assert ["Hullbreaker Horror", "Sol Ring"] in by_cards(k2["threatLines"])
    assert k2["lines"] == []
    print("  Kess-like deck: reanimation targets and castable-from-graveyard spells get "
          "graveyardTargets; Sol Ring, lands, the commander and a 1-drop do not: OK")

    gy_plain = v2["hotfix_plain"]["search"]["graveyardTargets"]
    assert gy_plain == {"Faithless Looting": 3}, gy_plain
    print("  no reanimation and no Kess: only the flashback card is a graveyard target: OK")

    gy_lier = v2["hotfix_lier"]["search"]["graveyardTargets"]
    assert gy_lier == {"Brainstorm": 3, "Blasphemous Act": 6}, gy_lier
    print("  a commander that grants flashback lists the deck's instants and sorceries: OK")

    # Reanimation is read from the effect, with a graveyard as its SOURCE:
    # not from reminder text, a graveyard that is only a destination, or a cost.
    reach = deck_plan._reanimation_reach
    for text, want in (
            (FACTS["Reanimate"]["oracle_text"], deck_plan._NO_CAP),
            (FACTS["Unburial Rites"]["oracle_text"], deck_plan._NO_CAP),
            ("Enchant creature card in a graveyard\nWhen this Aura enters, if it's on the "
             "battlefield, it loses \"enchant creature card in a graveyard\" and gains \"enchant "
             "creature put onto the battlefield with this Aura.\" Return enchanted creature card "
             "to the battlefield under your control and attach this Aura to it.",
             deck_plan._NO_CAP),                                           # Animate Dead
            ("Each player exiles all creature cards from their graveyard, then sacrifices all "
             "creatures they control, then puts all cards they exiled this way onto the "
             "battlefield.", deck_plan._NO_CAP),                           # Living Death
            ("Choose two target creature cards in your graveyard. Sacrifice a creature. If you "
             "do, return the chosen cards to the battlefield tapped.", deck_plan._NO_CAP),
            ("{2}{B}, Sacrifice a creature: Return target creature card from your graveyard to "
             "the battlefield.", deck_plan._NO_CAP),                       # cost, then effect
            ("Search your library and/or graveyard for a creature card with mana value X or "
             "less and put it onto the battlefield.", deck_plan._NO_CAP),  # X is no cap
            (FACTS["Reclaim Toy"]["oracle_text"], 3),
            (FACTS["Manifest Toy"]["oracle_text"], None),
            (FACTS["Wave Toy"]["oracle_text"], None),
            (FACTS["Evoker Toy"]["oracle_text"], None),
            (FACTS["Sol Ring"]["oracle_text"], None)):
        assert reach(text) == want, (text[:60], reach(text), want)
    gy_fakes = v2["hotfix_fakes"]["search"]["graveyardTargets"]
    assert gy_fakes == {}, gy_fakes
    gy_capped = v2["hotfix_capped"]["search"]["graveyardTargets"]
    assert gy_capped == {"Thassa's Oracle": 8, "Harmonize Toy": 3, "Dredge Toy": 3}, gy_capped
    print("  manifest dread, a graveyard destination and a discard cost are not "
          "reanimation; a mana-value cap keeps bigger creatures out; harmonize and dredge "
          "count: OK")

    # ------------------------------------------------------ name mapping --
    # No index: the front face is a card in the deck, so the Spellbook spelling
    # maps to it; version 1 keeps Spellbook's spelling byte for byte.
    assert ["James, Wandering Dad // Follow Him", "Mechanized Production"] in by_cards(c1["lines"])
    assert c1["weights"].get("James, Wandering Dad", 1) < 8
    assert ["James, Wandering Dad", "Mechanized Production"] in pilot, pilot
    assert c2["weights"]["James, Wandering Dad"] == 8, c2["weights"]
    assert c2["search"]["targets"]["James, Wandering Dad"] == 8
    assert ["Narset's Reversal", "Expansion // Explosion"] in by_cards(m2["threatLines"])
    print("  no index: 'Front // Back' line names map to the deck's front face; a split "
          "card keeps 'A // B'; version 1 keeps Spellbook's spelling: OK")

    synthetic(index=fake_index())
    v2i = deck_plan.build_plans(decks, plan_version=2)["decks"]
    assert v2i["hotfix_cedh"]["lines"] == c2["lines"], v2i["hotfix_cedh"]["lines"]
    assert v2i["hotfix_magda"]["threatLines"] == m2["threatLines"]
    u2 = v2["hotfix_unconverted"]["search"]["targets"]
    u2i = v2i["hotfix_unconverted"]["search"]["targets"]
    birgi = "Birgi, God of Storytelling // Harnfel, Horn of Bounty"
    assert birgi in u2, u2                  # no index, no cached layout: left as pasted...
    assert u2i == {"Birgi, God of Storytelling": 8, "Sol Ring": 5}, u2i   # ...the index maps it
    assert v1["hotfix_unconverted"]["search"]["targets"] == u2       # v1 key as pasted
    # Every deck-keyed field is mapped too: no trace of the pasted spelling.
    un = v2i["hotfix_unconverted"]
    assert "Harnfel" not in json.dumps(un), json.dumps(un)[:400]
    assert un["roles"]["Birgi, God of Storytelling"], un["roles"]
    assert "Harnfel" in json.dumps(v1["hotfix_unconverted"])       # v1 untouched
    assert dumps(deck_plan.build_plans(decks)) == v1_text, "the index must not touch v1"
    print("  with the Forge index: the same line names, and a pasted DFC target key "
          "becomes Forge's front-face name; version 1 still untouched: OK")

    # A line piece the deck itself spells the Spellbook way. The index maps the
    # line to Forge's name, so version 2 maps the deck card too before asking
    # whether it is a piece; otherwise the deck's own win piece loses its 8 and
    # an engine piece drops out of the threat list version 1 had it in.
    front = "Birgi, God of Storytelling"
    b1, b2, b2i = v1["hotfix_birgi"], v2["hotfix_birgi"], v2i["hotfix_birgi"]
    assert b1["weights"][BIRGI] == 8 and b1["roles"][BIRGI] == "combo-piece", b1["weights"]
    assert by_cards(b2i["lines"]) == [[front, "Underworld Breach", "Burning Inquiry"]], \
        b2i["lines"]
    assert [front, "Grinning Ignus"] in by_cards(b2i["threatLines"]), b2i["threatLines"]
    assert b2i["weights"][front] == 8 and b2i["roles"][front] == "combo-piece", b2i["weights"]
    assert b2i["search"]["targets"][front] == 8, b2i["search"]["targets"]
    assert b2i["weights"].get("Grinning Ignus", 1) < 8, b2i["weights"]   # engine-only piece
    assert {front, "Grinning Ignus", "Underworld Breach", "Burning Inquiry"} \
        <= set(b2i["threat"]), b2i["threat"]
    assert "Harnfel" not in json.dumps(b2i)
    # No index and no cached layout: the deck's own spelling is used throughout.
    assert b2["weights"][BIRGI] == 8 and BIRGI in b2["threat"], b2["weights"]
    assert by_cards(b2["lines"]) == [[BIRGI, "Underworld Breach", "Burning Inquiry"]]
    print("  a line piece the deck spells 'Front // Back' still counts in version 2 when "
          "the index renames the line: it keeps its 8 and its threat entry: OK")

    synthetic()
    namer = deck_plan.forge_namer(["Sol Ring"])
    # Step 2: the card cache's Scryfall layout, for a card not in this deck.
    assert namer("Delver of Secrets // Insectile Aberration") == "Delver of Secrets"
    assert namer("Expansion // Explosion") == "Expansion // Explosion"    # split layout
    assert namer("Unknown Front // Unknown Back") == "Unknown Front // Unknown Back"
    assert namer("Sol Ring") == "Sol Ring"
    print("  forge_namer fallbacks: cache layout maps a transform card, keeps a split card, "
          "leaves an unknown name alone: OK")

    # Synergy lines (opt-in) are archetype engines: threat lines, never pilot lines.
    syn = deck_plan.build_plans([path["hotfix_plain"]], synergy=True, plan_version=2)
    sp = syn["decks"]["hotfix_plain"]
    assert sp["lines"] == [] and all(ln.get("source") == "synergy" for ln in sp["threatLines"])
    # ...and name their pieces the Forge way, like Spellbook lines.
    anthem = "Anthem Front // Anthem Back"
    tk1 = deck_plan.build_plans([path["hotfix_tokens"]], synergy=True)["decks"]["hotfix_tokens"]
    tk2 = deck_plan.build_plans([path["hotfix_tokens"]], synergy=True,
                                plan_version=2)["decks"]["hotfix_tokens"]
    assert any(anthem in ln["cards"] for ln in tk1["lines"]), tk1["lines"]   # v1: as pasted
    assert tk2["lines"] == [], tk2["lines"]
    assert any("Anthem Front" in ln["cards"] for ln in tk2["threatLines"]), tk2["threatLines"]
    assert anthem not in json.dumps(tk2), tk2["threatLines"]
    print("  version 2 synergy lines go to threatLines only, in Forge's spelling: OK")

    print("plan hotfix: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
