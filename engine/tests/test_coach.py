#!/usr/bin/env python3
"""coach.py schema/cache tests with a stubbed provider (zero tokens).

Proves: the degraded no-key path, the rejected-run path (unrotated), schema
validation with one retry then fail closed, fact enforcement (win rate and
baseline come from the context, not the model), evidence-tag policing, and
that the second ask is a cache hit with no provider call.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

_data_dir = tempfile.mkdtemp(prefix="mtgcoach-")
os.environ["MTG_DATA_DIR"] = _data_dir
os.environ.pop("MTG_LLM_API_KEY", None)
# cards.py resolves its cache under MTG_DATA_DIR; seed the temp dir with the
# committed warm cache so archetype classification stays deterministic.
import shutil  # noqa: E402

shutil.copy(ENGINE / "card_cache.json", Path(_data_dir) / "card_cache.json")

import coach  # noqa: E402

FIXTURE = str(ENGINE / "tests" / "fixtures" / "sim_sample.json")
DECK = str(ENGINE / "decks" / "kilo_helm_final.dck")


def check(cond: bool, msg: str) -> None:
    if not cond:
        sys.exit(f"FAIL: {msg}")


class StubProvider:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    def __call__(self, system: str, user: str, **kw) -> str:
        self.calls += 1
        return self.responses[min(self.calls, len(self.responses)) - 1]


GOOD = json.dumps({
    "verdict": {"headline": "The engine runs; the pod outpaces it",
                "prose": "Kilo's counters engine fired every game. Read the "
                         "0% against the 12% engine baseline, not 25%."},
    "support_chain": [{"link": "Commander ignition", "status": "running",
                       "measured": "T17 med", "reading": "on plan"}],
    "matchups": [{"pod": "Wilhelt Zombies B3", "win_rate": 0.5,
                  "note": "the pressure deck here"}],
    "changes": [{"action": "cut", "card": "Walking Ballista",
                 "reason": "1 event a game in this file",
                 "evidence": "sim-evidence"}],
    "play_guide": ["Sequence counter producers before proliferate."],
})


def main() -> None:
    # 1. No key -> degraded, no crash, no network.
    r = coach.report(FIXTURE, DECK)
    check(r["ok"] is False and r["reason"] == "no LLM configured",
          f"degraded path: {r.get('reason')}")

    os.environ["MTG_LLM_API_KEY"] = "stub"

    # 2. Unrotated runs are rejected before any tokens are spent.
    unrotated = json.loads(Path(FIXTURE).read_text())
    unrotated["meta"]["source"] = "live"
    tmp = Path(os.environ["MTG_DATA_DIR"]) / "unrotated.json"
    tmp.write_text(json.dumps(unrotated))
    stub = StubProvider([GOOD])
    coach.llm.complete = stub
    r = coach.report(str(tmp), DECK)
    check(r["ok"] is False and "seat-rotated" in r["reason"],
          f"unrotated gate: {r.get('reason')}")
    check(stub.calls == 0, "unrotated run must not spend tokens")

    # 3. Bad evidence tag -> one retry, then fail closed; nothing cached.
    bad = GOOD.replace("sim-evidence", "consensus")
    stub = StubProvider([bad])
    coach.llm.complete = stub
    r = coach.report(FIXTURE, DECK)
    check(r["ok"] is False and "evidence" in r["reason"],
          f"evidence gate: {r.get('reason')}")
    check(stub.calls == 2, f"expected one retry (2 calls), got {stub.calls}")
    check(coach.cached_report(FIXTURE, DECK) is None, "failure must not cache")

    # 4. A cut for a card not in the deck is rejected.
    notin = GOOD.replace("Walking Ballista", "Black Lotus")
    stub = StubProvider([notin])
    coach.llm.complete = stub
    r = coach.report(FIXTURE, DECK)
    check(r["ok"] is False and "not in the deck" in r["reason"],
          f"cut gate: {r.get('reason')}")

    # 5. Valid output passes; the displayed numbers are context facts.
    stub = StubProvider([GOOD])
    coach.llm.complete = stub
    r = coach.report(FIXTURE, DECK)
    check(r["ok"] is True, f"valid output should pass: {r.get('reason')}")
    check(r["verdict"]["win_rate"] == 0.0, "win_rate must come from the run")
    check(r["verdict"]["baseline"] == 0.12, "baseline must come from archetype")
    check(r["verdict"]["sim_is_floor"] is False, "floor flag from archetype")
    check(r["games"] == 2, "games must be the payload count")
    check(r["meta"]["deck_hash"], "meta.deck_hash missing")
    first_generated = r["meta"]["generated"]

    # 6. Second ask is a cache hit: no provider call, identical timestamp.
    r2 = coach.report(FIXTURE, DECK)
    check(r2["cached"] is True, "second ask must come from cache")
    check(r2["meta"]["generated"] == first_generated,
          "cache hit must return the identical generated timestamp")
    check(stub.calls == 1, f"cache hit must not call the provider ({stub.calls})")

    print("test_coach: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
