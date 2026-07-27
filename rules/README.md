# MTG Rules Knowledge Base

Structured knowledge base built from the official **Magic: The Gathering Comprehensive Rules** (effective June 19, 2026), intended as the retrieval layer for rules-assisted features (turn order guidance, stack handling, mechanic lookups).

## Files

| File | What it is |
|---|---|
| `raw/MagicCompRules_20260619.txt` | The official source file from Wizards (do not edit) |
| `build_rules_kb.py` | Parser — regenerates everything in `kb/` from the raw file |
| `query_rules.py` | Zero-dependency lookup/search CLI (also usable as a module) |
| `kb/turn_structure.json` | Phases and steps **in turn order** — Beginning (Untap, Upkeep, Draw), Precombat Main, Combat (all 5 steps), Postcombat Main, Ending (End, Cleanup) — each with its full rules attached, plus section 703 (turn-based actions) |
| `kb/stack_and_priority.json` | Rules 117 (priority), 405 (the stack), 601/602/603/605 (casting spells, activating and triggered abilities, mana abilities), 608 (resolving) |
| `kb/mechanics.json` | Every keyword ability (702 — 193 entries incl. Haste, Station, Crew…) and keyword action (701 — 69 entries), each with all its subrules |
| `kb/glossary.json` | All 735 glossary terms (Vehicle, Poison Counter, Monarch, …) with `rule_refs` pointing back into `all_rules.json` |
| `kb/all_rules.json` | Flat map of all 3,152 numbered rules — resolve any `rule_refs` or "See rule X" reference against this |
| `kb/chunks.jsonl` | One retrieval-ready chunk per rule/glossary entry (3,887 chunks) with metadata — feed this to an embedding model / vector store for semantic RAG |

## Usage

```
python query_rules.py 502.1              # exact rule number (returns subrules too)
python query_rules.py station            # mechanic name -> full keyword entry
python query_rules.py "combat damage"    # free text -> top-scored chunks
```

For turn-order automation, don't search at all — walk `turn_structure.json` directly: `phases[]` is ordered, each phase has ordered `steps[]`, and every step carries its rules (e.g. the Untap step includes 502.4, "no player receives priority during the untap step").

## Upgrading to semantic RAG

`chunks.jsonl` is the embedding input. Each line: `{id, type, rule|term, section_title, text}`. Embed `text`, store the metadata, and retrieve by cosine similarity — then use the `rule`/`section` metadata to pull neighboring subrules from `all_rules.json` for context expansion. The structured files above remain the better path for anything deterministic (turn order, priority passes); save vector search for open-ended questions ("can I crew a vehicle at instant speed?").

## Rebuilding after a rules update

Wizards updates the CR with most set releases. Download the new TXT from
<https://magic.wizards.com/en/rules>, drop it in `raw/`, then:

```
python build_rules_kb.py raw/MagicCompRules_<date>.txt
```
