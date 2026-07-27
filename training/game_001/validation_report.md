# Game 001 — Rules Validation Report

Game: Roll and Conquer, "Commander Chaos Begins..." (Episode 1 of 3)
Video: https://www.youtube.com/watch?v=IIE4VeO1Cgs
Validated against: `rules/kb/` (Comprehensive Rules, effective 2026-06-19), via `query_rules.py`

Every ruling made or discussed at the table was checked against the rules KB. Result: **10 verified-correct rulings, 2 rules errors, 3 items flagged for review**. The RAG successfully resolved every rules question raised in the video — including the two the table got wrong — which is a strong validation signal for the retrieval layer.

## Rules errors at the table (RAG catches these)

**E1 — Commander damage threshold stated as 20 (21:28).** Weston: "It's 20 damage through a commander." CR **903.10a**: "A player who's been dealt **21** or more combat damage by the same commander over the course of the game loses the game." The KB returns the correct rule as the top exact-match hit for `903.10`.

**E2 — Discard-to-hand-size timing (32:16–32:24).** Table: you discard "at the end of turn... or at the beginning of upkeep." CR **514.1**: excess cards are discarded as a turn-based action during the **cleanup step** of that player's own turn (see also **402.2**). The "overfill between turns" conclusion they reached is accidentally correct in effect, but the stated timing is wrong.

## Verified-correct rulings (rule → KB confirmation)

1. **Free first mulligan in multiplayer (3:18)** → 103.5c: first mulligan doesn't count in multiplayer games. Their "free mulligan for everyone" matches the CR exactly (not just a house rule).
2. **Everyone draws on turn 1 in 4-player (5:04, 5:48)** → 103.8c: "In all other multiplayer games, no player skips the draw step of their first turn." The Arena comparison ("if you go first you don't draw") only applies to two-player games (103.8a).
3. **Summoning sickness explanation (5:39) and enforcement (22:38)** → 302.6 / 508.1a. The table initially declared the freshly-cast Duskshell Crawler as an attacker, then correctly caught and reversed it.
4. **Commander tax +2 per prior cast (37:10–38:06)** → 903.8. "Three, then five, then seven" is exactly right.
5. **Equipment can't be voluntarily unattached (27:54)** → 301.5 / 301.5c. Correct: it stays until the creature leaves or the equipment is re-equipped.
6. **Attackers declared all at once; no adding later (42:21–42:38)** → 508.1a. Correct teaching moment for the new player.
7. **The stack / responding with instants (42:43–43:10)** → 601.3, 405. Simplified but accurate LIFO description.
8. **Trample damage assignment (45:13–46:06)** → 702.19, 702.19d, 510.1: assign lethal to blockers, excess to defending player; unblocked trampler deals all damage to player. Their explanation matches.
9. **Cultivate's land ≠ land drop (18:45)** → 305.2 (one land per turn applies only to playing lands, not putting them onto the battlefield via effects) + 701.23 (search).
10. **Foretell mechanics (38:30, 50:31–50:44)** → 702.143a–b: pay {2}, exile face down as a special action; cast after the current turn ends for the foretell cost. Their handling (including "it goes to the graveyard after resolving like a normal instant") is correct.
11. **Station mechanic (39:23–39:49, 51:39)** → 702.184a: tap another untapped creature, add charge counters equal to its power, sorcery-speed only. Also correct that a noncreature artifact can use tap abilities the turn it arrives (302.6 applies only to creatures).
12. **Non-basic lands with basic land types (26:00–26:17)** → 305.6-adjacent: a "Mountain Forest" dual counts as a Mountain for reveal requirements because it has the subtype. Correct.

## Flagged for review (ambiguous in ASR transcript)

**F1 — Turn-order anomaly in cycle 6.** The transcript places Bolt's Arcane Signet turn (43:34) before Alex's turn (44:43), which contradicts the established Alex→Jared→Bolt→Weston rotation. Likely a video edit/cut or speaker-attribution error in the unlabeled ASR captions.

**F2 — "Can I switch what land I tapped?" (39:57).** Answered "Yes, I do it all the time." Casually fine, but technically once a mana ability has resolved and information has been gained, retconning is not supported by the CR (mana abilities don't use the stack and can't be undone — 605.3). Low-stakes house leniency; worth encoding as a "house_rule_tolerance" case for the training model.

**F3 — Orzhov Basilica as turn-1 land (9:25).** Bounce land played with no other land to return. The ETB trigger resolves with no legal target/object. Legal play; flagged only because the table discussed it (29:41) without resolving what the trigger did.

## Rule-numbering corrections made during validation

Initial draft rule refs used older CR numbering; the KB (June 2026 CR) shifted several:

| Concept | Old ref (draft) | Correct ref in current KB |
|---|---|---|
| First-turn draw skip | 103.7 | **103.8** (103.7 is now Planechase) |
| Free multiplayer mulligan | 103.5d | **103.5c** |
| Proliferate | 701.27 | **701.34** |
| Investigate | 701.20 | **701.16** |
| Station | (new) | **702.184** |

This is itself a useful finding: any model trained on older rules citations must resolve rule numbers against the current `all_rules.json` rather than memorized numbering.

## Assessment of the RAG for this use case

- `turn_structure.json` correctly modeled every phase transition observed (untap→upkeep→draw→main→combat steps→end→cleanup). The video's loose "upkeep... draw" narration maps cleanly onto it.
- `mechanics.json` contained every keyword encountered: lifelink, trample, flying, first strike, haste, foretell, proliferate, investigate, station — including Station, which only exists in recent CRs. No gaps found.
- `stack_and_priority.json` covered the declare-attackers/stack teaching moment (508.1a, 405, 601.3).
- Free-text search (`query_rules.py "search your library"`) is weaker than exact-rule lookup — top hits were token/cycling rules rather than 701.23. For the training pipeline, prefer keyword/exact lookups or the planned embedding upgrade for open-ended queries.
