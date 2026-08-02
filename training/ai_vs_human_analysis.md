# AI vs Human Play — Behavioral Analysis

Comparison of Forge AI behavior (20-game sim of the game_005 pod, `sim_20260723_101044`)
against documented human behavior across the five extracted games. Useful as grounding
context for any AI feature that evaluates or explains plays.

## Human-like behaviors (validated against training data)

| Behavior | Sim evidence | Human evidence |
|---|---|---|
| Attack the healthiest player | 43% of 244 attacks target highest-life defender | game_004 "you're at the most life — that's fair"; game_002 Ben→Kathleen at 40 |
| Sound combat math | only 4 attackers died to blocks in 20 games | humans rarely made losing attacks |
| Deathtouch deterrence | 3 attacks into Glissa's controller vs 9 elsewhere | game_005 "first strike death touch — I'm not swinging at that" |

## Non-human tells

1. **Never splits attacks**: 244/244 combat turns focus one defender. Humans split
   constantly (game_001 "Shelinda at Jared, Duskshell at Weston"; game_003 Teysa dual attack).
   Artifact of Forge's AiAttackController (single-defender selection).
2. **Block rate 14%** (34 blocks vs 214 declines). Human games feature routine blocks,
   chumps, double-blocks (game_004 double-block + Golgari Charm and assign-lethal puzzles).
   Partially confounded by unblockable/protection attackers; still race-mode.
3. **No politics or memory**: zero retaliation, deals, threats, or kingmaking avoidance —
   the layer that decided every human game (game_005's winner was removal-revenge driven).
4. **Slow commander deployment for synergy decks**: Raggadragga AI median player-turn 8
   (human: ~turn 4); Siona median 13, uncast in 3/20 games (human: ~turn 5).

## Implications

- Sim win rates are valid for **deck power** (human-validated: Wildsear won both realities).
- AI game lines are NOT play recommendations; never present them as "what a good player does."
- Voltron/aura decks: treat sim win rate as a floor.
- If a human-like agent is ever built (custom PlayerController), the fix list in priority
  order: attack splitting, block valuation, politics/grudge memory, commander-first sequencing —
  each testable against the five human games in this folder.
