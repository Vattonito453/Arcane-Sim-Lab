#!/usr/bin/env python3
"""Deck features for the sim-to-human correction model.

Everything here is computable from a decklist alone -- no human data, no sim
run -- because at inference time that is all a user gives us. Features are
chosen to capture WHERE FORGE'S AI IS WRONG, not to describe the deck for its
own sake:

  aggression   Forge's AI blocks ~14% of the time (CLAUDE.md, measured) and
               focuses all attackers on one defender. A human blocks far more.
               So a deck that wins by attacking should be systematically
               OVERRATED by Forge relative to a human table.
  interaction  Removal and counterspells need timing and target choice. Stock
               AI holds them badly, so interaction-dense decks should be
               UNDERRATED.
  complexity   High curve, combo lines, tutors: the more a deck needs a plan,
               the worse an AI pilots it.

Each hypothesis has a sign we can check against the residual, which is how we
tell a real mechanism from a curve fit.

Stdlib only, so the fitted model can ship inside engine/ with no new deps.
"""
from __future__ import annotations

import json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "engine"))
import cards, deck_plan  # noqa: E402

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


def main():
    here = Path(__file__).resolve().parent
    cohort = json.loads((here / "cohort.json").read_text(encoding="utf-8"))
    rows = []
    for d in cohort:
        r = deck_features(d["file"])
        # Key on the MANIFEST name, which is what the tally uses. The .dck
        # metadata name differs (it carries set and year), and a silent
        # mismatch drops every deck from the join.
        r["deck_name"] = r["name"]
        r["name"] = d["name"]
        r["human"] = d["human"]
        r["human_n"] = d["n"]
        rows.append(r)
    (here / "features.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    cov = sorted(r["coverage"] for r in rows)
    print(f"features for {len(rows)} decks; coverage min {cov[0]:.2f} "
          f"median {cov[len(cov)//2]:.2f}")
    for k in ("aggression", "interaction", "complexity", "avg_cmc", "creatures"):
        vals = sorted(r[k] for r in rows)
        print(f"  {k:12} min {vals[0]:>7.2f}  median {vals[len(vals)//2]:>7.2f}  "
              f"max {vals[-1]:>7.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
