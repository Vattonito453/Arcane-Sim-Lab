#!/usr/bin/env python3
"""rules_qa grounding + cache tests, all with a stubbed provider (zero tokens).

Proves: the degraded no-key path, normalization collapsing to one cache key,
the hallucinated-citation rejection path (retry once, then fail closed), and
that a grounded answer caches and a cache hit makes no provider call.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

# Isolate the cache and force the not-configured state before imports read env.
os.environ["MTG_DATA_DIR"] = tempfile.mkdtemp(prefix="mtgqa-")
os.environ.pop("MTG_LLM_API_KEY", None)

import llm  # noqa: E402
import rules_qa  # noqa: E402


def check(cond: bool, msg: str) -> None:
    if not cond:
        sys.exit(f"FAIL: {msg}")


class StubProvider:
    """Replaces llm.complete; counts calls and plays scripted responses."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    def __call__(self, system: str, user: str, **kw) -> str:
        self.calls += 1
        return self.responses[min(self.calls, len(self.responses)) - 1]


def main() -> None:
    q = "is 19 commander damage lethal"

    # 1. Degrades with no key: ok False, hits still populated, no crash.
    r = rules_qa.answer(q)
    check(r["ok"] is False, f"expected degraded response, got {r.get('ok')}")
    check(r["reason"] == "no LLM configured", f"reason: {r.get('reason')}")
    check(len(r["hits"]) > 0, "degraded response must still carry hits")

    # 2. Normalization collapses variants to one key.
    a = rules_qa.question_key("Is 19 commander damage lethal?")
    b = rules_qa.question_key("is  19 commander damage lethal")
    check(a == b, "normalized variants must share a cache key")
    check(rules_qa.normalize("  Is\tThis   Legal?! ") == "is this legal",
          f"normalize: {rules_qa.normalize('  Is  This   Legal?! ')!r}")

    # Pretend a key is configured from here on; the provider is stubbed.
    os.environ["MTG_LLM_API_KEY"] = "stub"

    # 3. A fabricated citation is rejected: one retry, then fail closed.
    stub = StubProvider(["Commander damage is lethal at 21, per 999.99z."])
    rules_qa.llm.complete = stub
    r = rules_qa.answer(q)
    check(r["ok"] is False, "hallucinated citation must fail closed")
    check(r["reason"] == "citations not grounded", f"reason: {r.get('reason')}")
    check("999.99z" in r.get("ungrounded", []), f"ungrounded: {r.get('ungrounded')}")
    check(stub.calls == 2, f"expected exactly one retry (2 calls), got {stub.calls}")
    check(rules_qa.cached_answer(q) is None, "a failed answer must not be cached")

    # 4. A grounded answer validates, caches, and every citation is in hits.
    hits = rules_qa.retrieve(q)
    real_rule = next(str(h["rule"]) for h in hits if h.get("rule"))
    stub = StubProvider([f"A player is defeated at 21 commander damage, per {real_rule}."])
    rules_qa.llm.complete = stub
    r = rules_qa.answer(q)
    check(r["ok"] is True, f"grounded answer should pass: {r}")
    hit_rules = {str(h.get("rule")) for h in r["hits"]}
    check(all(c["rule"] in hit_rules for c in r["citations"]),
          f"citation not grounded: {r['citations']}")
    check(r["covered"] is True and r["cached"] is False, "fresh answer flags")

    # 5. The repeat ask is a cache hit: no provider call, same key.
    r2 = rules_qa.answer("Is 19 COMMANDER damage lethal?!")
    check(r2["cached"] is True, "second ask must come from cache")
    check(r2["key"] == r["key"], "cache hit must share the key")
    check(stub.calls == 1, f"cache hit must not call the provider ({stub.calls})")

    # 6. The not-covered contract parses.
    stub = StubProvider([f"{rules_qa.NOT_COVERED_TOKEN} The excerpts do not reach this."])
    rules_qa.llm.complete = stub
    r = rules_qa.answer("what is the airspeed velocity of an unladen sparrow", refresh=True)
    check(r["ok"] is True and r["covered"] is False,
          f"not-covered answer should be ok with covered False: {r.get('covered')}")

    print("test_rules_qa: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
