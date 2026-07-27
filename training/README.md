# MTG Commander Training Dataset

Real-game data extracted from YouTube Commander gameplay, structured turn-by-turn and validated against the rules KB in `../rules/kb/`. Purpose: ground the rules-engine RAG in actual play sequences (turn structure, priority, triggers, politics) and stress-test retrieval against real rules questions.

## Games

| Game | Source | Length | Status |
|---|---|---|---|
| `game_001/` | Roll and Conquer, "Commander Chaos Begins..." Ep 1 (IIE4VeO1Cgs) + "The Table Explodes..." Ep 2 (mqNCsse5f2I) | 54 + 60 min | Partial — concludes in Ep 3 ("The Victor is Chosen...", 1:26:45, not yet extracted) |
| `game_002/` | LoadingReadyRun, "LRRMtG — 4 Player Commander" (tjo4sJcK7Ik), broadcast 2017 | 2h05 (game ≈ 11:34–1:41:49) | **Complete** — winner: Ben (Phenax mill); includes a 21-commander-damage kill and a mill-out loss |
| `game_003/` | LoadingReadyRun, "Friday Night Paper Fight — 4 Player Commander" (HkSYycJ8KSU), broadcast 2019 | 2h31 (game ≈ 9:35–2:17:30) | **Complete** — winner: Ben (Wort conspire burn); densest rules content: Void Winnower rulings, lands-played-not-cast, commander/object identity, an on-camera color-identity violation catch |
| `game_004/` | LoadingReadyRun, "Friday Night Paper Fight — Commander Planechase" (zxqw4OxCQJo), broadcast 2018 | 3h58, **two complete games** | First VARIANT sample (Planechase, CR 901): planar die mechanics, 12+ planes' rules interactions, goad, persist, myriad-style token triggers — including two PARTIAL_ERROR rulings the KB corrects |
| `game_005/` | Mana Dorks, "Mana Dorks Is Back! Ep 1" (pmbYi4R8bS8), 2026 | 1h51 | **Complete** — winner: N3cro (Raggadragga, 24 commander damage one-shot). Firsts: full published decklists (Moxfield/Archidekt links in meta — convertible to .dck for Forge replay), digital virtual-tabletop play, poison counters, and a player *choosing* graveyard over command zone (903.9a is optional) |

## Files per game

- `transcript_raw.txt` / `transcript_ep2_raw.txt` — timestamped ASR captions (speaker-unlabeled). game_002 has no raw transcript stored (2h stream); its log carries timestamps for re-extraction.
- `game_log.json` / `game_log_ep2.json` — structured events: `{t, player, action, card, detail, rule_refs[], confidence, validation}`.
- `validation_report.md` — every table ruling checked against the KB via `query_rules.py`.

## Data conventions

- **confidence**: `high` = explicit in transcript; `medium` = inferred from context; `low` = ASR garbled, best guess. Card names are as-heard when uncertain.
- **rule_refs** resolve against `../rules/kb/all_rules.json` (CR effective 2026-06-19). Older videos cite shifted rule numbers — always resolve against the current KB (e.g. first-turn draw is 103.8, not 103.7).
- **validation** values: `CORRECT`, `CORRECT_CATCH` (players fixed their own error), `RULES_ERROR` (table got it wrong; KB has the right answer), `PARTIAL_ERROR`, `FLAG` (missed trigger / ambiguity for manual review).

## Headline validation results

The RAG resolved **every** rules question raised across ~4 hours of gameplay, including the ones players got wrong:

- game_001 E1: commander damage stated as 20 → **903.10a says 21** (RULES_ERROR)
- game_001 E2: discard timing "end of turn/upkeep" → **514.1 cleanup step** (RULES_ERROR); hexproof described as non-targeting-proof → **702.11/702.18** (PARTIAL_ERROR)
- game_002: textbook-correct state-based-action, copy-effect, devotion, and empty-library-loss rulings, all confirmed by the KB (704, 707.2, 104.3c)

Known KB gaps found: **none** — every keyword encountered (station, foretell, hideaway, proliferate, living weapon, devotion, modified) exists in `mechanics.json`/glossary.

## Extraction pipeline (repeatable)

1. Open the video's YouTube transcript panel and scrape the `transcript-segment-view-model` DOM nodes (any browser-automation tool works).
2. Reconstruct turns: track land drops, "draw for turn", combat declarations; attribute speakers from context (decks/commanders anchor identity).
3. Cite CR rules for each action; verify each ref with `python3 ../rules/query_rules.py <rule>`.
4. Log table mistakes as RULES_ERROR entries — these are the highest-value training samples (question → correct rule).

## Next steps

- Extract Ep 3 to complete game_001 (winner + endgame states).
- Add non-Commander formats (per plan) — schema already format-agnostic except `starting_life` / commander fields.
- Consider embedding `game_log` events alongside `chunks.jsonl` so retrieval can pull "real play example" context next to the rule text.
