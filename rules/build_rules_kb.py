"""Parse the MTG Comprehensive Rules text file into a structured knowledge base.

Outputs (in rules/kb/):
  all_rules.json         - every numbered rule, flat map keyed by rule number
  turn_structure.json    - phases/steps in turn order, each with its rules attached
  stack_and_priority.json- priority, the stack, casting/activating/resolving
  mechanics.json         - every keyword ability (702) and keyword action (701)
  glossary.json          - full glossary with extracted rule cross-references
  chunks.jsonl           - one retrieval-ready chunk per rule/glossary entry (for RAG)

Usage: python build_rules_kb.py [path-to-MagicCompRules.txt]
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
RAW_DEFAULT = HERE / "raw" / "MagicCompRules_20260619.txt"
OUT_DIR = HERE / "kb"

CHAPTER_RE = re.compile(r"^([1-9])\. (.+)$")
SECTION_RE = re.compile(r"^(\d{3})\. (.+)$")
RULE_RE = re.compile(r"^(\d{3}\.\d+)\. (.*)$")
SUBRULE_RE = re.compile(r"^(\d{3}\.\d+[a-z])\.? (.*)$")
SEE_RULE_RE = re.compile(r"rule (\d{3}(?:\.\d+[a-z]?)?)")


def nth_index(lines, value, n):
    count = 0
    for i, line in enumerate(lines):
        if line.strip() == value:
            count += 1
            if count == n:
                return i
    raise ValueError(f"Could not find occurrence {n} of {value!r}")


def parse(raw_path):
    text = raw_path.read_text(encoding="utf-8-sig")
    lines = [ln.rstrip() for ln in text.splitlines()]

    body_start = nth_index(lines, "1. Game Concepts", 2)
    glossary_start = nth_index(lines, "Glossary", 2)
    credits_start = nth_index(lines, "Credits", 2)

    # --- numbered rules -----------------------------------------------------
    rules = {}  # "502.1a" -> {text, section, ...}
    sections = {}  # "502" -> {title, chapter, chapter_title, rules: [nums]}
    chapter_num, chapter_title = None, None
    section_num, section_title = None, None
    last_rule = None

    for line in lines[body_start:glossary_start]:
        line = line.strip()
        if not line:
            continue
        m = CHAPTER_RE.match(line)
        if m:
            chapter_num, chapter_title = m.group(1), m.group(2)
            continue
        m = SECTION_RE.match(line)
        if m:
            section_num, section_title = m.group(1), m.group(2)
            sections[section_num] = {
                "title": section_title,
                "chapter": chapter_num,
                "chapter_title": chapter_title,
                "rules": [],
            }
            continue
        m = RULE_RE.match(line) or SUBRULE_RE.match(line)
        if m:
            num, body = m.group(1), m.group(2)
            rules[num] = {
                "text": body,
                "section": section_num,
                "section_title": section_title,
                "chapter": chapter_num,
                "chapter_title": chapter_title,
                "examples": [],
            }
            sections[section_num]["rules"].append(num)
            last_rule = num
            continue
        if line.startswith("Example:") and last_rule:
            rules[last_rule]["examples"].append(line[len("Example:"):].strip())

    # --- glossary -----------------------------------------------------------
    glossary = {}
    term, definition = None, []
    for line in lines[glossary_start + 1 : credits_start]:
        line = line.strip()
        if not line:
            if term and definition:
                body = " ".join(definition)
                glossary[term] = {
                    "definition": body,
                    "rule_refs": sorted(set(SEE_RULE_RE.findall(body))),
                }
            term, definition = None, []
            continue
        if term is None:
            term = line
        else:
            definition.append(line)
    if term and definition:
        body = " ".join(definition)
        glossary[term] = {
            "definition": body,
            "rule_refs": sorted(set(SEE_RULE_RE.findall(body))),
        }

    return rules, sections, glossary


def section_payload(sections, rules, num):
    sec = sections[num]
    return {
        "section": num,
        "title": sec["title"],
        "rules": [
            {"rule": r, "text": rules[r]["text"], "examples": rules[r]["examples"]}
            for r in sec["rules"]
        ],
    }


def build_turn_structure(sections, rules):
    def step(num, name):
        return {"step": name, **section_payload(sections, rules, num)}

    return {
        "source": "MTG Comprehensive Rules, section 5 (Turn Structure) + 703 (Turn-Based Actions)",
        "general": section_payload(sections, rules, "500"),
        "phases": [
            {
                "phase": "Beginning Phase",
                "order": 1,
                **section_payload(sections, rules, "501"),
                "steps": [
                    step("502", "Untap Step"),
                    step("503", "Upkeep Step"),
                    step("504", "Draw Step"),
                ],
            },
            {
                "phase": "Precombat Main Phase",
                "order": 2,
                **section_payload(sections, rules, "505"),
                "steps": [],
            },
            {
                "phase": "Combat Phase",
                "order": 3,
                **section_payload(sections, rules, "506"),
                "steps": [
                    step("507", "Beginning of Combat Step"),
                    step("508", "Declare Attackers Step"),
                    step("509", "Declare Blockers Step"),
                    step("510", "Combat Damage Step"),
                    step("511", "End of Combat Step"),
                ],
            },
            {
                "phase": "Postcombat Main Phase",
                "order": 4,
                "note": "Same rules as the precombat main phase; see section 505.",
                "section": "505",
                "steps": [],
            },
            {
                "phase": "Ending Phase",
                "order": 5,
                **section_payload(sections, rules, "512"),
                "steps": [
                    step("513", "End Step"),
                    step("514", "Cleanup Step"),
                ],
            },
        ],
        "turn_based_actions": section_payload(sections, rules, "703"),
    }


def build_stack(sections, rules):
    nums = ["117", "405", "601", "602", "603", "605", "608"]
    return {
        "source": "MTG Comprehensive Rules — priority, the stack, casting and resolving",
        "sections": [section_payload(sections, rules, n) for n in nums],
    }


def keyword_entries(sections, rules, section_num):
    """Split a 701/702-style section into one entry per named mechanic."""
    entries = []
    current = None
    for num in sections[section_num]["rules"]:
        parent = num.split(".")[0] + "." + num.split(".")[1].rstrip("abcdefghijklmnopqrstuvwxyz")
        is_parent = re.fullmatch(r"\d{3}\.\d+", num) is not None
        if is_parent:
            current = {
                "name": rules[num]["text"].rstrip("."),
                "rule": num,
                "rules": [],
            }
            entries.append(current)
        elif current and num.startswith(current["rule"]):
            current["rules"].append(
                {"rule": num, "text": rules[num]["text"], "examples": rules[num]["examples"]}
            )
    # First entry of each section is the "General"/intro rule, not a mechanic
    return [e for e in entries if e["name"].lower() != "general" and not e["name"].startswith("Most abilities")]


def build_mechanics(sections, rules, glossary):
    keywords = keyword_entries(sections, rules, "702")
    actions = keyword_entries(sections, rules, "701")
    ability_words = rules.get("207.2c", {}).get("text", "")
    return {
        "source": "MTG Comprehensive Rules — 702 (Keyword Abilities), 701 (Keyword Actions), 207.2c (Ability Words)",
        "keyword_abilities": keywords,
        "keyword_actions": actions,
        "ability_words_rule": {"rule": "207.2c", "text": ability_words},
        "note": "Non-keyword mechanics (Vehicle, poison, day/night, etc.) live in glossary.json; each glossary entry carries rule_refs pointing back into all_rules.json.",
    }


def build_chunks(rules, glossary):
    chunks = []
    for num, r in rules.items():
        text = f"{num} {r['text']}"
        if r["examples"]:
            text += " Example: " + " Example: ".join(r["examples"])
        chunks.append(
            {
                "id": f"cr-{num}",
                "type": "rule",
                "rule": num,
                "section": r["section"],
                "section_title": r["section_title"],
                "chapter_title": r["chapter_title"],
                "text": text,
            }
        )
    for term, g in glossary.items():
        chunks.append(
            {
                "id": "gloss-" + re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-"),
                "type": "glossary",
                "term": term,
                "rule_refs": g["rule_refs"],
                "text": f"{term}: {g['definition']}",
            }
        )
    return chunks


def main():
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW_DEFAULT
    rules, sections, glossary = parse(raw_path)
    OUT_DIR.mkdir(exist_ok=True)

    def dump(name, obj):
        path = OUT_DIR / name
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path.name}")

    dump("all_rules.json", rules)
    dump("turn_structure.json", build_turn_structure(sections, rules))
    dump("stack_and_priority.json", build_stack(sections, rules))
    dump("mechanics.json", build_mechanics(sections, rules, glossary))
    dump("glossary.json", glossary)

    chunks = build_chunks(rules, glossary)
    with (OUT_DIR / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote chunks.jsonl ({len(chunks)} chunks)")
    print(f"{len(rules)} rules, {len(sections)} sections, {len(glossary)} glossary terms")


if __name__ == "__main__":
    main()
