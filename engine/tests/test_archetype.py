#!/usr/bin/env python3
"""Archetype classification against the four fixture decks (task 01 Stage 2).

Runs cache-only (fetch=False): engine/card_cache.json is committed warm for
these decks, so the test is deterministic and offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from archetype import BASELINES, classify_dck  # noqa: E402

DECKS = ENGINE / "decks"


def check(cond: bool, msg: str) -> None:
    if not cond:
        sys.exit(f"FAIL: {msg}")


def main() -> None:
    kilo = classify_dck(DECKS / "kilo_helm_final.dck")
    check(kilo["class"] == "engine", f"Kilo should be engine, got {kilo}")
    check(kilo["baseline"] == 0.12, f"engine baseline should be 0.12, got {kilo}")
    check(kilo["baseline"] == BASELINES["engine"], "baseline not from BASELINES")
    check(bool(kilo["why"]), "why must be populated")

    wyleth = classify_dck(DECKS / "wyleth_voltron.dck")
    check(wyleth["class"] == "voltron", f"Wyleth should be voltron, got {wyleth}")
    check(wyleth["sim_is_floor"] is True, f"voltron must be sim_is_floor, got {wyleth}")

    wilhelt = classify_dck(DECKS / "wilhelt_zombies.dck")
    check(wilhelt["class"] == "creature", f"Wilhelt should be creature, got {wilhelt}")
    check(wilhelt["baseline"] == 0.38, f"creature baseline should be 0.38, got {wilhelt}")

    drana = classify_dck(DECKS / "drana_vampires.dck")
    check(drana["class"] == "creature", f"Drana should be creature, got {drana}")

    # A list the cache has never seen must come back unknown, not guessed.
    from archetype import classify
    mystery = classify([f"Totally Fabricated Card {i}" for i in range(30)])
    check(mystery["class"] == "unknown", f"uncached deck should be unknown, got {mystery}")

    print("test_archetype: ALL ASSERTIONS PASSED")
    for r in (kilo, wyleth, wilhelt, drana):
        print(f"  {r['deck']}: {r['class']} (baseline {r['baseline']}, "
              f"floor {r['sim_is_floor']})")


if __name__ == "__main__":
    main()
