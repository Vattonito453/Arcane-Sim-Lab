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

import hashlib
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
        # How the deck sits against the calibration set: (above the model's
        # mean, below it). The sentence is chosen by the deck's POSITION and
        # the direction by the contribution's sign, so it is right for a
        # feature of either weight sign. The old table keyed the sentence on
        # the contribution's sign alone, which is only right for a negative
        # weight: avg_cmc weighs +0.968, so a cheap deck (negative
        # contribution) was explained as "is expensive" (repair plan WS11
        # task 12). No mechanism is claimed; only what the fitted relation
        # says about decks like this one.
        DESCRIBE = {
            "creatures": ("is creature-dense", "runs few creatures"),
            "avg_cmc": ("has a higher curve than most", "has a lower curve than most"),
            "aggression": ("leans on combat more than most",
                           "leans on combat less than most"),
            "interaction": ("carries more removal and counterspells than most",
                            "runs light on interaction"),
            "complexity": ("is more complex to pilot than most", "plays straightforwardly"),
        }
        for k, v in drivers[:1]:
            if abs(v) < 0.5 or k not in DESCRIBE or k not in self.features:
                continue
            above = values[k] >= self.m["mu"][self.features.index(k)]
            desc = DESCRIBE[k][0 if above else 1]
            out.append(f"Adjusted {'up' if v > 0 else 'down'} because this deck {desc}: "
                       f"among the {self.m.get('n_decks') or 'calibration'} calibration "
                       f"decks, decks like that won {'more' if v > 0 else 'less'} often "
                       f"at human tables than the simulation alone suggests.")
        out.append(f"Typical error is about {p['typical_error_pp']:.1f} points, "
                   f"from leave-one-out testing on "
                   f"{p['basis']['trained_on_decks']} decks.")
        return out


def load_default():
    return Predictor.load()


# ---- pilot honesty (repair plan WS11 task 11, decision 19) ----------
# The model was fitted on stock Forge games; every production run is piloted
# by Sim Lab's plan agent. So every prediction carries the model's arm, the
# run's pilot, whether they match and a label, and a pilot whose latest rank
# check failed gets no prediction at all. The checks are committed records
# (rank_checks.json), written by a study's reader, never by hand-editing a
# threshold into code.

DEFAULT_RANK_CHECKS = MODEL_DIR / "rank_checks.json"


def model_pilot(model: dict) -> str:
    """The pilot id (engine/pilot.py) of the games a model was fitted on.

    `arm_pilot` is explicit on the shipped model; a model without it is read
    from its `arm` text, and only a stock arm is recognised that way."""
    explicit = model.get("arm_pilot")
    if explicit:
        return str(explicit)
    return "stock" if str(model.get("arm") or "").lower().startswith("stock") else "unknown"


def model_fingerprint(model: dict) -> str:
    """Which fitted model a rank check measured: a hash of the parameters
    that define its predictions, not of the file.

    A rank check measures one fitted function under one pilot. The refit
    after G3 is a different function, so a check of the old model must
    neither keep withholding the new one (decision 19: "suppressed until a
    refit") nor lend it a pass it never earned. An edit to the file's notes
    (arm_pilot, ground_truth, the LOO figures) changes nothing a check
    measured, so it must not change the identity either."""
    core = {k: model.get(k) for k in ("features", "weights", "mu", "sd", "intercept")}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load_rank_checks(path=None) -> list[dict] | None:
    """The committed rank-check records, in file order.

    Accepts {"checks": [...]} (the committed layout, which has room for a note)
    or a bare list. None when the file is missing or unreadable: the caller
    must then fail closed, because an absent record cannot show that a
    pilot's latest check did not fail."""
    p = Path(path or DEFAULT_RANK_CHECKS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    checks = data.get("checks") if isinstance(data, dict) else data
    if not isinstance(checks, list):
        return None
    return [c for c in checks if isinstance(c, dict)]


def latest_check(checks: list[dict], pilot_id: str, model: str | None = None) -> dict | None:
    """The most recent record for this pilot: latest date, and the later
    line in the file when two share a date (a re-check appends).

    With `model` (model_fingerprint of the served model), a record that names
    a different model is skipped: it checked another fitted function. A
    record that names no model still counts, so a failed record can never be
    silenced by leaving the field out; the reader always writes it."""
    best, best_key = None, None
    for i, c in enumerate(checks):
        if c.get("pilot") != pilot_id:
            continue
        if model is not None and c.get("model") not in (None, model):
            continue
        key = (str(c.get("date") or ""), i)
        if best_key is None or key > best_key:
            best, best_key = c, key
    return best


def _fmt_check(c: dict) -> str:
    """"2026-10-16: rank correlation 0.47 against a threshold of 0.40".

    The release id ("R1") stays in the record, not in the copy: it is an
    internal name a player cannot read (ui-review: no raw ids on screen)."""
    where = str(c.get("date") or "")
    try:
        figures = (f"rank correlation {float(c['value']):.2f} against a "
                   f"threshold of {float(c['threshold']):.2f}")
    except (KeyError, TypeError, ValueError):
        figures = "figures not recorded"
    return f"{where}: {figures}" if where else figures


def pilot_honesty(model: dict, pilot: dict, checks: list[dict] | None) -> dict:
    """Label, match and suppression for one run.

    pilot is engine/pilot.run_pilot(meta), or pilot.disclose(meta) (its
    superset, which the endpoint passes so this payload carries the run
    page's own pilot object); checks is load_rank_checks().
    Suppressed only when the latest check of THIS model for the run's pilot
    failed, or when the record itself is missing (fail closed). A pilot with
    no check keeps the label and says so; the model's own pilot needs no
    check."""
    arm_pilot = model_pilot(model)
    fingerprint = model_fingerprint(model)
    match = pilot.get("id") == arm_pilot
    fit_on = ("stock Forge games" if arm_pilot == "stock"
              else f"games from {model.get('arm') or 'another pilot'}")
    kind = pilot.get("kind")
    if match:
        label = (f"Fit on {fit_on}; this run used stock Forge too." if arm_pilot == "stock"
                 else f"Fit on {fit_on}, the same pilot as this run.")
    elif kind == "plan":
        label = f"Fit on {fit_on}; this run used Sim Lab's pilot."
    elif kind == "mixed":
        label = f"Fit on {fit_on}; this run mixed Sim Lab's pilot with stock Forge seats."
    elif kind == "stock":
        label = f"Fit on {fit_on}; this run used stock Forge."
    else:
        label = f"Fit on {fit_on}; this run does not record its pilot."

    suppressed, reason, by = False, None, None
    if match:
        rank = {"status": "model_arm",
                "text": "This run used the pilot the model was fitted on."}
    elif checks is None:
        rank = {"status": "unreadable",
                "text": "The rank-check record is missing from this deployment."}
        suppressed, by = True, "rank_record_missing"
        reason = ("The rank-check record is missing from this deployment, so there "
                  "is no way to confirm the model still ranks decks under this "
                  "run's pilot.")
    else:
        rec = latest_check(checks, str(pilot.get("id")), fingerprint)
        if rec is None:
            rank = {"status": "none",
                    "text": "No rank check has been run for this pilot yet."}
        elif rec.get("pass") is True:
            rank = {"status": "pass", "record": rec,
                    "text": f"Rank check passed for this pilot ({_fmt_check(rec)})."}
        else:
            rank = {"status": "fail", "record": rec,
                    "text": f"Rank check failed for this pilot ({_fmt_check(rec)})."}
            suppressed, by = True, "rank_check"
            reason = (f"The rank check for this pilot failed ({_fmt_check(rec)}), so the "
                      f"model no longer ranks decks reliably under it. The prediction "
                      f"is withheld for this pilot until the model is refit.")
    return {"model_arm": {"text": model.get("arm"), "pilot": arm_pilot,
                          "model": fingerprint},
            "pilot": pilot, "pilot_match": match, "label": label,
            "rank_check": rank, "suppressed": suppressed,
            "suppressed_by": by, "suppressed_reason": reason}


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
