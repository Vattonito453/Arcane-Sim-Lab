#!/usr/bin/env python3
"""The plan_feedback nudge is off unless MTG_PLAN_FEEDBACK_APPLY=1 (WS0 task 5).

deck_plan.build_plan used to let plan_feedback.apply_to_plan move search
targets whenever the store held enough games, so the plan a deck ran
depended on whatever the store happened to contain, and the nudge had never
been validated (repair plan RC4). It is now gated, default off.

The gate is checked where it matters, on the bytes the shim receives: with a
synthetic store that WOULD nudge, the plans JSON (serialised exactly as
run_sim writes it) must be byte-identical to the one built with no store at
all. With the flag at 1 the same store must move the plan, which proves the
store really would have nudged and the equality above is not vacuous.

Synthetic card facts, a temp MTG_DATA_DIR per scenario: no cache, no network,
no Forge, and the tracked engine/plan_feedback.json is never touched.

Run: py engine/tests/test_plan_feedback_gate.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cards  # noqa: E402
import deck_plan  # noqa: E402
import plan_feedback  # noqa: E402

FLAG = "MTG_PLAN_FEEDBACK_APPLY"
DECK = "gate_toy"
FACTS = {
    "Commander Cat": {"oracle_text": "Flying", "type_line": "Legendary Creature — Cat", "cmc": 3},
    # A board payoff at cmc 8: a search target with the "finisher" hint, which
    # is exactly what a combat-majority observation nudges up.
    "Overrun Ape": {"oracle_text": "Creatures you control get +3/+3 until end of turn.",
                    "type_line": "Creature — Ape", "cmc": 8},
    "Win Button": {"oracle_text": "You win the game.", "type_line": "Enchantment", "cmc": 5},
    "Mana Rock": {"oracle_text": "{T}: Add {C}{C}.", "type_line": "Artifact", "cmc": 1},
    "Plain Bear": {"oracle_text": "", "type_line": "Creature — Bear", "cmc": 2},
    "Some Mountain": {"oracle_text": "{T}: Add {R}.", "type_line": "Basic Land — Mountain",
                      "cmc": 0},
}

# Well past MIN_DECK_GAMES, every win by combat: observed_for() returns a
# per-deck observation and apply_to_plan() tilts finisher targets up.
STORE = {"decks": {DECK: {"games": 3 * plan_feedback.MIN_DECK_GAMES, "wins": 12,
                          "methods": {"combat damage / life loss": 12},
                          "win_rounds": [7, 8, 9]}},
         "_runs": ["synthetic"]}


def write_dck(d: Path) -> Path:
    p = d / f"{DECK}.dck"
    body = ["[metadata]", f"Name={DECK}", "[Commander]", "1 Commander Cat", "[Main]"]
    body += [f"1 {n}" for n in FACTS if n != "Commander Cat"]
    p.write_text("\n".join(body), encoding="utf-8")
    return p


def build(flag: str | None, store: dict | None) -> tuple[str, dict]:
    """Plans JSON as run_sim writes it, in a fresh data dir; also the parsed plan."""
    saved = {k: os.environ.get(k) for k in (FLAG, "MTG_DATA_DIR")}
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "data"
        data.mkdir()
        if store is not None:
            (data / "plan_feedback.json").write_text(json.dumps(store), encoding="utf-8")
        os.environ["MTG_DATA_DIR"] = str(data)
        if flag is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = flag
        try:
            plans = deck_plan.build_plans([write_dck(Path(td))])
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return json.dumps(plans, indent=2), plans["decks"][DECK]


def main() -> None:
    deck_plan.cards.get_many = lambda names, fetch=False: {cards.key(n): f
                                                           for n, f in FACTS.items()}
    deck_plan.combos.combos_for_dck = lambda p, fetch=False: {}  # no Spellbook lines
    tracked = Path(__file__).resolve().parent.parent / "plan_feedback.json"
    tracked_before = tracked.read_bytes() if tracked.exists() else None

    baseline, base_plan = build(None, None)
    base_target = base_plan["search"]["targets"].get("Overrun Ape")
    assert base_target is not None and \
        base_plan["search"]["context"]["Overrun Ape"]["hint"] == "finisher", base_plan["search"]
    assert "observed" not in base_plan
    print("  baseline (no store, flag unset) builds: OK")

    for flag in (None, "0"):
        got, _ = build(flag, STORE)
        assert got == baseline, f"flag={flag!r}: a would-nudge store changed the plan bytes"
    print("  would-nudge store, flag unset and flag 0: plan JSON byte-identical: OK")

    # Only the exact value "1" turns it on, like the other MTG_* switches.
    for flag in ("", "true", "yes", "01"):
        got, _ = build(flag, STORE)
        assert got == baseline, f"flag={flag!r} must not enable the nudge"
    print("  any value other than '1' leaves it off: OK")

    on, on_plan = build("1", STORE)
    assert on != baseline, "flag 1 with a would-nudge store must change the plan"
    assert on_plan["search"]["targets"]["Overrun Ape"] == \
        min(9, base_target + plan_feedback.MAX_NUDGE), on_plan["search"]["targets"]
    assert on_plan["observed"]["basis"] == "deck", on_plan.get("observed")
    # Nothing but the finisher target and the observation moved.
    stripped = dict(on_plan)
    stripped.pop("observed")
    stripped["search"] = json.loads(json.dumps(on_plan["search"]))
    stripped["search"]["targets"]["Overrun Ape"] = base_target
    assert stripped == base_plan, "the nudge must touch only search targets"
    print("  flag 1 applies the nudge (sanity: the store really would nudge): OK")

    tracked_after = tracked.read_bytes() if tracked.exists() else None
    assert tracked_after == tracked_before, "the test must not write the tracked store"
    print("  tracked engine/plan_feedback.json untouched: OK")

    print("plan_feedback gate: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
