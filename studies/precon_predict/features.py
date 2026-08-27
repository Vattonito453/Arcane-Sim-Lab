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

# deck_features lives in engine/predict.py so training and serving cannot
# drift apart. This module only joins it to the cohort's human results.
from predict import deck_features  # noqa: E402


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
