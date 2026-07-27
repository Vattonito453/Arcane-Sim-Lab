# MTG Training Data — RAG Package for AI Studio

Everything in this package is retrieval-ready grounding data for an MTG AI assistant.
Two corpora, designed to be used TOGETHER:

## 1. `training_chunks.jsonl` — real-game knowledge (307 chunks)

One JSON object per line, flattened from five real 4-player Commander games
(seven complete games total — one video contains two, one game spans two episodes):

```json
{
  "id": "game_003-e015",
  "type": "rules_moment",              // game_overview | game_event | rules_moment | summary_*
  "game": "game_003",
  "source_video": "https://www.youtube.com/watch?v=...",
  "video_t": "51:31",                  // timestamp — every claim is re-checkable
  "text": "Event: rules_teaching. Ben plays Dryad Arbor under Void Winnower...",
  "rule_refs": ["305.9", "112.1"],     // join keys into rules_kb/all_rules.json
  "validation": "CORRECT",             // CORRECT | CORRECT_CATCH | RULES_ERROR | PARTIAL_ERROR | FLAG
  "player": "Ben",
  "confidence": "high"                 // high | medium | low (ASR-derived data)
}
```

Counts: 151 game events, 95 validated rules moments, 55 summary chunks, 6 game overviews.
134 chunks carry `rule_refs`; 94 carry validation labels.

**The validation labels are the gold**: `RULES_ERROR` chunks are cases where real players
got a rule wrong and the correct answer is in the rules corpus — ideal eval questions for
the assistant ("players said commander damage is 20 — what's correct?" → 903.10a says 21).

## 2. `rules_kb/` — official rules corpus (June 2026 Comprehensive Rules)

| File | Contents |
|---|---|
| `chunks.jsonl` | 3,887 retrieval chunks: `{id, type, rule|term, section_title, text}` — embed these |
| `all_rules.json` | all 3,152 numbered rules keyed by number — exact lookup / citation resolution |
| `mechanics.json` | 262 keyword abilities & actions with all subrules |
| `glossary.json` | 735 terms with rule cross-references |
| `turn_structure.json` | phases/steps in order with attached rules — drive turn UIs from this |
| `stack_and_priority.json` | casting, priority, stack, resolution rules grouped |

## How to wire the RAG (recommended)

1. Embed `rules_kb/chunks.jsonl` and `training_chunks.jsonl` into ONE vector store,
   keeping the `type` field as metadata (rules vs real-game example).
2. On a user question: retrieve top-k from both corpora.
3. Generation prompt: answer ONLY from retrieved text; cite rule numbers inline; when a
   training chunk is retrieved, use it as a real-play example ("at a real table this came
   up when..."). NEVER answer rules from model memory — rule numbers shift between
   Comprehensive Rules editions (this corpus is June 2026; e.g. first-turn-draw moved
   from 103.7 to 103.8).
4. Resolve every cited number against `all_rules.json` before display; link citations to
   the full rule text.
5. Use `validation: RULES_ERROR` chunks as the regression/eval set for the assistant.

## Also included

- `game_00X/game_log.json` — full structured logs (source of truth for the chunks)
- `game_001/transcript_raw.txt`, `transcript_ep2_raw.txt` — timestamped raw transcripts
- `game_00X/validation_report.md` — per-game rules audit (game_001)
- `ai_vs_human_analysis.md` — how AI play differs from human play, quantified
- `game_005` meta includes published decklists + a 20-game simulation cross-check

## Deliberately NOT included

The game-state/simulation engine (Forge integration, deck conversion, job queue, HTTP
API) lives in the main project repo — a separate concern from this grounding corpus.
Integrate it later as its own module when the app needs live simulation.
