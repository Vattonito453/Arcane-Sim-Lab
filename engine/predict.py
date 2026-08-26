#!/usr/bin/env python3
"""Turn a raw sim win rate into a predicted REAL-PLAYGROUP win rate.

Why this exists. Forge's win rate is not the number a player wants. Measured
on 66 Commander precons against 10,982 real games from playgroup.gg, stock
Forge spans 19-53% where humans span 12-41%, a calibration slope near 0.47:
it systematically inflates, and it inflates weak decks most. One measured
mechanism is combat. Forge blocks 14.7% of attacking creatures over 2128
decisions, so roughly 85% of attackers get through; a human table blocks far
more, which flatters any deck that wins by attacking.

So the sim is an input, not an answer. This module applies a correction fitted
against real human outcomes, and reports the uncertainty honestly rather than
printing a single confident number.

Stdlib only, so it runs inside the API container with no new dependencies.
The model file is small JSON: feature list, standardiser, ridge weights.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cards  # noqa: E402
import deck_plan  # noqa: E402

# ---- deck features -------------------------------------------------
# The SINGLE implementation. studies/precon_predict/features.py imports
# it from here, because a second copy would drift and produce
# train/serve skew that nothing would catch.

EVASION = re.compile(r"\bflying\b|\bmenace\b|\btrample\b|can't be blocked|"
                     r"\bshadow\b|\bfear\b|\bintimidate\b|\bskulk\b|\bhorsemanship\b", re.I)
REMOVAL = re.compile(r"destroy target|exile target|deals \d+ damage to target|"
                     r"target creature gets -|sacrifices? a creature", re.I)
COUNTER = re.compile(r"counter target", re.I)
WIPE = re.compile(r"destroy all|exile all|each creature|all creatures get -", re.I)
DRAW = re.compile(r"draw (a|two|three|\w+) cards?", re.I)
RAMP = re.compile(r"search your library for a .{0,20}land|add \{|add one mana|"
                  r"add two mana", re.I)
RECUR = re.compile(r"from your graveyard", re.I)


def deck_features(path) -> dict:
    name, cmd, main = deck_plan.read_dck(path)
    names = cmd + main
    facts = cards.get_many(names, fetch=False)
    f = {k: 0 for k in ("creatures", "lands", "artifacts", "enchantments",
                        "spells", "planeswalkers", "evasion", "removal",
                        "counters", "wipes", "draw", "ramp", "recursion")}
    cmcs, powers = [], []
    known = 0
    for n in names:
        d = facts.get(cards.key(n)) or facts.get(n) or {}
        if not d:
            continue
        known += 1
        text = d.get("oracle_text") or ""
        tl = d.get("type_line") or ""
        cmc = d.get("cmc") or 0
        is_land = "Land" in tl
        if is_land:
            f["lands"] += 1
        else:
            cmcs.append(cmc)
        if "Creature" in tl:
            f["creatures"] += 1
            p = d.get("power")
            try:
                powers.append(float(p))
            except (TypeError, ValueError):
                pass
            if EVASION.search(text):
                f["evasion"] += 1
        if "Artifact" in tl and not is_land:
            f["artifacts"] += 1
        if "Enchantment" in tl:
            f["enchantments"] += 1
        if "Planeswalker" in tl:
            f["planeswalkers"] += 1
        if "Instant" in tl or "Sorcery" in tl:
            f["spells"] += 1
        if REMOVAL.search(text):
            f["removal"] += 1
        if COUNTER.search(text):
            f["counters"] += 1
        if WIPE.search(text):
            f["wipes"] += 1
        if DRAW.search(text):
            f["draw"] += 1
        if RAMP.search(text):
            f["ramp"] += 1
        if RECUR.search(text):
            f["recursion"] += 1
    total = max(1, len(names))
    out = {
        "name": name,
        "coverage": round(known / total, 3),
        "avg_cmc": round(sum(cmcs) / max(1, len(cmcs)), 3),
        "avg_power": round(sum(powers) / max(1, len(powers)), 3),
        "total_power": sum(powers),
    }
    for k, v in f.items():
        out[k] = v
    # Hypothesis-bearing composites, per-99 so deck size cannot drive them.
    out["aggression"] = round((sum(powers) + 2 * f["evasion"]) / total, 4)
    out["interaction"] = round((f["removal"] + f["counters"] + f["wipes"]) / total, 4)
    out["complexity"] = round(
        (out["avg_cmc"] / 4.0) + (f["recursion"] + f["draw"]) / total, 4)
    return out


MODEL_DIR = Path(__file__).parent / "models"
DEFAULT_MODEL = MODEL_DIR / "precon_predict.json"


class Predictor:
    def __init__(self, model: dict):
        self.m = model
        self.features = model["features"]

    @classmethod
    def load(cls, path=None):
        p = Path(path or DEFAULT_MODEL)
        if not p.is_file():
            return None
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def predict(self, values: dict) -> dict:
        """values: {feature name -> number}, must include every model feature.

        Returns the expected human win rate, an interval built from the
        model's own out-of-sample error (not a fitted standard error, which
        would understate it), and the per-feature contributions so the UI can
        say WHY the number moved rather than just asserting it.
        """
        m = self.m
        missing = [f for f in self.features if f not in values]
        if missing:
            raise ValueError(f"missing features: {missing}")
        contrib, total = {}, m["intercept"]
        for i, f in enumerate(self.features):
            z = (values[f] - m["mu"][i]) / (m["sd"][i] or 1.0)
            c = m["weights"][i] * z
            contrib[f] = round(c, 3)
            total += c
        # A win rate cannot leave [0, 100], and a 4-player pod makes anything
        # outside roughly 5-60% implausible for a precon-class deck.
        expected = max(0.0, min(100.0, total))
        mae = m.get("loo", {}).get("mae", 4.0)
        return {
            "expected_win_rate": round(expected, 1),
            "low": round(max(0.0, expected - mae), 1),
            "high": round(min(100.0, expected + mae), 1),
            "typical_error_pp": round(mae, 2),
            "contributions": contrib,
            "basis": {
                "trained_on_decks": m.get("n_decks"),
                "human_games": m.get("human_games"),
                "arm": m.get("arm"),
                "loo_spearman": round(m.get("loo", {}).get("spearman", 0.0), 3),
            },
        }

    def explain(self, values: dict) -> list[str]:
        """Plain sentences a player can act on. Only the sim term and the
        largest correction are worth saying; the rest is noise to a user."""
        out = []
        p = self.predict(values)
        sim = values.get("sim")
        if sim is not None:
            gap = sim - p["expected_win_rate"]
            if abs(gap) >= 3:
                direction = "higher than" if gap > 0 else "lower than"
                out.append(
                    f"The raw simulation says {sim:.0f}%, which is "
                    f"{abs(gap):.0f} points {direction} what a real playgroup "
                    f"tends to produce for a deck like this.")
        drivers = sorted(((k, v) for k, v in p["contributions"].items() if k != "sim"),
                         key=lambda kv: -abs(kv[1]))
        REASON = {
            "aggression": ("wins through combat, and the sim's AI blocks far "
                           "less than a human does", "leans on combat less than most"),
            "interaction": ("carries a lot of removal and counterspells, which "
                            "an AI uses worse than a person", "runs light on interaction"),
            "avg_cmc": ("is expensive, and the AI stumbles on high curves",
                        "is cheap to cast"),
            "creatures": ("is creature-dense", "runs few creatures"),
            "complexity": ("needs a plan the AI does not follow",
                           "plays straightforwardly"),
        }
        for k, v in drivers[:1]:
            if abs(v) < 0.5 or k not in REASON:
                continue
            hi, lo = REASON[k]
            out.append(f"Adjusted {'down' if v < 0 else 'up'} because this deck "
                       f"{hi if v < 0 else lo}.")
        out.append(f"Typical error is about {p['typical_error_pp']:.1f} points, "
                   f"from leave-one-out testing on "
                   f"{p['basis']['trained_on_decks']} decks.")
        return out


def load_default():
    return Predictor.load()


if __name__ == "__main__":
    import sys
    p = Predictor.load()
    if p is None:
        sys.exit(f"no model at {DEFAULT_MODEL}; fit one with "
                 f"studies/precon_predict/analyze.py")
    vals = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(p.predict(vals), indent=1))
    for line in p.explain(vals):
        print(" -", line)
