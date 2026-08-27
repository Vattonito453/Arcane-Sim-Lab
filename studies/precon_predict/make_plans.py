#!/usr/bin/env python3
"""Build a plans file for a set of decks with personality overrides.

Overrides are how a behavioural parameter gets FITTED against real playgroup
outcomes instead of guessed. Refuses to write a degraded plan, because a cold
card-fact cache silently produces an agent with most of its policy missing.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "engine"))
from deck_plan import build_plans  # noqa: E402


def build(deck_files, out_path, overrides=None, min_cov=0.9):
    plans = build_plans([str(d) for d in deck_files])
    bad = [f"{n} cov={p.get('factsCoverage',0):.2f}"
           for n, p in plans["decks"].items() if p.get("factsCoverage", 0) < min_cov]
    if bad:
        sys.exit("degraded plan data: " + "; ".join(bad))
    if overrides:
        for p in plans["decks"].values():
            p.setdefault("personality", {}).update(overrides)
    Path(out_path).write_text(json.dumps(plans, indent=1), encoding="utf-8")
    return plans


if __name__ == "__main__":
    ov = json.loads(sys.argv[1])
    out = sys.argv[2]
    build(sys.argv[3:], out, ov)
    print("wrote", out)
