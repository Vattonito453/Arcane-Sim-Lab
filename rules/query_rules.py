"""Query the parsed MTG rules knowledge base (rules/kb/).

Usage:
  python query_rules.py 502.1            # exact rule number -> rule + its subrules
  python query_rules.py station          # mechanic name -> full keyword entry
  python query_rules.py "combat damage"  # free text -> top-scored rule chunks

Zero dependencies; keyword scoring over chunks.jsonl. Swap search() for an
embedding lookup later without changing callers.
"""

import json
import re
import sys
from pathlib import Path

KB = Path(__file__).parent / "kb"
RULE_NUM_RE = re.compile(r"^\d{3}(\.\d+[a-z]?)?$")
WORD_RE = re.compile(r"[a-z0-9']+")

STOPWORDS = {"the", "a", "an", "of", "to", "in", "is", "and", "or", "that", "this", "it", "its"}


def load_chunks():
    with (KB / "chunks.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def lookup_rule(query):
    rules = json.loads((KB / "all_rules.json").read_text(encoding="utf-8"))
    hits = {n: r for n, r in rules.items() if n == query or n.startswith(query + ".") or
            (RULE_NUM_RE.match(query) and "." in query and n.startswith(query))}
    return hits


def lookup_mechanic(query):
    m = json.loads((KB / "mechanics.json").read_text(encoding="utf-8"))
    q = query.lower()
    for group in ("keyword_abilities", "keyword_actions"):
        for entry in m[group]:
            if entry["name"].lower() == q:
                return entry
    return None


def lookup_glossary(query):
    g = json.loads((KB / "glossary.json").read_text(encoding="utf-8"))
    q = query.lower()
    return {t: d for t, d in g.items() if q in t.lower()}


def tokens(text):
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS]


def search(query, k=5):
    q_tokens = set(tokens(query))
    q_phrase = query.lower()
    scored = []
    for chunk in load_chunks():
        text = chunk["text"].lower()
        t = set(tokens(text))
        overlap = len(q_tokens & t)
        if not overlap:
            continue
        score = overlap / len(q_tokens) + (2.0 if q_phrase in text else 0.0)
        scored.append((score, chunk))
    scored.sort(key=lambda s: -s[0])
    return [c for _, c in scored[:k]]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    query = " ".join(sys.argv[1:]).strip()

    if RULE_NUM_RE.match(query):
        hits = lookup_rule(query)
        if hits:
            for num, r in hits.items():
                print(f"{num}. {r['text']}")
                for ex in r["examples"]:
                    print(f"    Example: {ex}")
            return

    mech = lookup_mechanic(query)
    if mech:
        print(f"{mech['name']} (rule {mech['rule']})")
        for r in mech["rules"]:
            print(f"  {r['rule']} {r['text']}")
        return

    gloss = lookup_glossary(query)
    if gloss and len(query) > 3:
        for term, d in gloss.items():
            print(f"{term}: {d['definition']}")
        if len(gloss) <= 3:
            return
        print()

    for chunk in search(query):
        label = chunk.get("rule") or chunk.get("term")
        print(f"[{label}] {chunk['text'][:250]}")
        print()


if __name__ == "__main__":
    main()
