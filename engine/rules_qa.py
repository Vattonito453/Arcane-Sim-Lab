#!/usr/bin/env python3
"""AI rules assistant: retrieval + one cached synthesis per distinct question.

Grounding discipline (frontend_handoff/API_SPEC.md "Rules RAG"): the model
answers ONLY from retrieved Comprehensive Rules excerpts and cites rule
numbers inline. Rule numbers shift between CR editions, so a
confidently-cited number from model memory is worse than "not covered" —
after generation, every rule-number token in the answer is checked against
the retrieved chunk set; an ungrounded citation drops the answer, retries
once, then fails closed. That check is the only reason to trust the output.

Cache honesty: this is a NORMALIZED-QUESTION HASH CACHE — exact match after
normalization (NFKC, casefold, whitespace collapse, edge punctuation strip),
no embedding similarity, no paraphrase matching. It delivers "$0 after the
first ask" for repeat phrasings and nothing more. Nothing lossier than that
normalization is applied, because two questions that differ by one word can
have opposite answers.

Retrieval scope: Engine.search() scores the 3,887 retrieval chunks (rules +
glossary); exact rule numbers detected in the question are additionally
looked up in the 3,152 numbered rules via Engine.rule(). search() truncates
chunk text to 400 characters; the prompt uses the truncated text and cites
by number, so the UI can load the full rule via GET /rule/{n}.

Answers are cached under MTG_DATA_DIR/rules_answers/{sha256(normalized)}.json.
A cache hit makes no network call. No MTG_LLM_API_KEY -> degraded response
with the retrieved hits, so the UI falls back to plain rules search.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import llm  # noqa: E402

KB_EDITION = "June 2026 CR"
NOT_COVERED_TOKEN = "[not-covered]"

# Every token in the answer that looks like a rule number is checked for
# grounding. Deliberately broad (a bare "100" matches): false positives make
# the model avoid loose numbers, false negatives would let hallucinated
# citations through.
_RULE_TOKEN = re.compile(r"\b\d{3}(?:\.\d+[a-z]?)?\b")

SYSTEM_PROMPT = (
    "You are a Magic: The Gathering judge. Answer ONLY from the rules "
    "excerpts provided by the user. Cite rule numbers inline, e.g. \"per "
    "903.10a\", and cite only numbers that appear in the excerpts — never "
    "write any other number in NNN or NNN.NNa form, and avoid bare "
    "three-digit numbers that are not citations. If the excerpts do not "
    f"cover the question, reply with the single token {NOT_COVERED_TOKEN} "
    "followed by one sentence saying the retrieved rules do not reach the "
    "question — do not answer from memory, because your training data may "
    "conflict with the current Comprehensive Rules. Keep answers to 2-5 "
    "sentences of plain prose, no headings or lists."
)


def _engine():
    """A lazily-built Engine for standalone use; the server passes its own."""
    global _ENGINE  # noqa: PLW0603 — module-level cache, stdlib only
    try:
        return _ENGINE
    except NameError:
        from mtg_engine import Engine
        _ENGINE = Engine()
        return _ENGINE


def _answers_dir() -> Path:
    base = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent)))
    return base / "rules_answers"


def normalize(question: str) -> str:
    """Cache-key normalization, exactly these steps and nothing lossier:

    1. Unicode NFKC normalization
    2. casefold()
    3. collapse internal whitespace runs to single spaces, strip ends
    4. strip leading and trailing punctuation characters

    No stemming, no stopword removal — "can I" and "can he" must not collide.
    """
    q = unicodedata.normalize("NFKC", question)
    q = q.casefold()
    q = re.sub(r"\s+", " ", q).strip()
    return q.strip(".,;:!?\"'`()[]{}<>")


def question_key(question: str) -> str:
    return hashlib.sha256(normalize(question).encode("utf-8")).hexdigest()


def retrieve(question: str, k: int = 8, engine=None) -> list[dict]:
    """Scored chunks from search, plus exact lookups for any rule number the
    question itself names (API_SPEC step 2). Zero tokens."""
    e = engine or _engine()
    hits = [dict(h, source="search") for h in e.search(question, k)]
    seen = {h.get("rule") for h in hits}
    for num in _RULE_TOKEN.findall(question):
        if "." not in num:
            continue  # a bare "100" in a question is rarely a rule reference
        looked = e.rule(num)
        for entry in looked.get("entries", []):
            if entry["rule"] in seen:
                continue
            seen.add(entry["rule"])
            hits.append({"id": f"rule-{entry['rule']}", "rule": entry["rule"],
                         "score": 0, "text": entry["text"], "source": "exact"})
    return hits


def _grounding(answer_text: str, hits: list[dict]) -> tuple[list[dict], set[str]]:
    """(citations present in hits, ungrounded tokens). Exact match on the
    retrieved rule ids — a subrule the model invents off a retrieved parent
    is still ungrounded."""
    hit_rules = {str(h.get("rule")) for h in hits if h.get("rule")}
    cited = set(_RULE_TOKEN.findall(answer_text))
    citations = []
    for c in sorted(cited):
        if c in hit_rules:
            text = next((h["text"] for h in hits if str(h.get("rule")) == c), "")
            citations.append({"rule": c, "text": text})
    return citations, cited - hit_rules


def _prompt_user(question: str, hits: list[dict]) -> str:
    excerpts = "\n\n".join(
        f"[{h.get('rule') or h.get('id')}] {h.get('text', '')}" for h in hits)
    return f"Question: {question}\n\nRules excerpts:\n{excerpts}"


def cached_answer(question: str) -> dict | None:
    """The stored answer for this question, or None. Never generates."""
    f = _answers_dir() / f"{question_key(question)}.json"
    if not f.is_file():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    data["cached"] = True
    return data


def answer(question: str, *, refresh: bool = False, engine=None) -> dict:
    """Cache-aware entry point. A hit makes no network call."""
    question = question.strip()
    norm = normalize(question)
    key = question_key(question)
    if not refresh:
        hit = cached_answer(question)
        if hit is not None:
            return hit

    hits = retrieve(question, engine=engine)
    base = {"ok": False, "question": question, "normalized": norm,
            "key": key, "hits": hits, "cached": False}
    if not llm.configured():
        return {**base, "reason": "no LLM configured"}

    user = _prompt_user(question, hits)
    last_ungrounded: set[str] = set()
    for attempt in range(2):
        try:
            text = llm.complete(SYSTEM_PROMPT, user).strip()
        except llm.LLMError as e:
            return {**base, "reason": f"generation failed: {e}"}
        covered = not text.startswith(NOT_COVERED_TOKEN)
        display = text[len(NOT_COVERED_TOKEN):].strip() if not covered else text
        citations, ungrounded = _grounding(display, hits)
        if display and not ungrounded:
            result = {
                "ok": True, "question": question, "normalized": norm,
                "key": key, "answer": display, "citations": citations,
                "hits": hits, "covered": covered, "cached": False,
                "meta": {"model": llm.default_model(),
                         "generated": datetime.now(timezone.utc).isoformat(),
                         "kb": KB_EDITION},
            }
            out = _answers_dir()
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{key}.json").write_text(
                json.dumps(result, indent=1), encoding="utf-8")
            return result
        last_ungrounded = ungrounded
        # One corrective retry: name the offending numbers explicitly.
        user = (_prompt_user(question, hits) +
                "\n\nYour previous answer cited rule numbers not present in "
                f"the excerpts ({', '.join(sorted(ungrounded)) or 'empty answer'}). "
                "Answer again citing only numbers from the excerpts, or reply "
                f"{NOT_COVERED_TOKEN} if they do not cover the question.")
    return {**base, "reason": "citations not grounded",
            "ungrounded": sorted(last_ungrounded)}


def main() -> None:
    q = " ".join(a for a in sys.argv[1:] if not a.startswith("-"))
    if not q:
        sys.exit("usage: python3 rules_qa.py <question>")
    print(json.dumps(answer(q, refresh="--refresh" in sys.argv), indent=2))


if __name__ == "__main__":
    main()
