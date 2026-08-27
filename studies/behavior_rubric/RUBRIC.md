# Play-quality rubric: is this pilot playing Magic, or following rules?

Researched 2026-08-26. 76 candidate criteria across mulligans, attacking,
blocking and interaction, each defined as something countable from a game log.
Sources are strategy writing (Reid Duke, Sperling, Card Kingdom, Commander's
Herald, EDHREC) plus the Comprehensive Rules and hypergeometric baselines.

## The correction this forced

I previously told Vincent that **blocking cannot be measured** because video
captions never narrate blocks. That conflated two different things:

- **Can we measure it?** Blocking is **19 of 19 criteria measurable from
  PUBLIC information** — declared attackers, declared blockers, and power and
  toughness at the moment of the block. Attacking is 19 of 19 as well.
- **Can we compare it to humans?** No, not from this video corpus.

Those are different questions, and the answer to the second does not block the
first. Which gives the rubric two kinds of axis:

**NORMATIVE axes** score a pilot against what strong play says is correct.
They need only the sim, and they are how blocking, attacking and mulligans get
graded. "A block where your creature survives AND kills the attacker is free
value, so a strong pilot takes ~all of them" is a standard, not a human
average.

**COMPARATIVE axes** put human, stock and agent side by side on the same
decklists. Only axes measurable in all three qualify: win round, win method,
disruption rate, off-turn interaction share, commander deploy turn.

## Feasibility by topic

| topic | criteria | public-only | comparable to humans? |
|---|---|---|---|
| Blocking | 19 | **19** | no (never narrated) |
| Attacking | 19 | **19** | partial (key_line only) |
| Interaction | 19 | 14 | yes (7 games have interaction_events) |
| Mulligans | 19 | 5 | **no** (traces: "not recoverable; edited out") |

Mulligans are the weakest case: 14 of 19 criteria need to see the hand, and
the human side is edited out of every video. Mulligan quality is therefore
**sim-only and normative**, scored against Reid Duke's keep test and the
deck's own hypergeometric floor rather than against people.

## The starting set (highest signal, all public, all implementable)

**Blocking — normative**
- `free_block_capture_rate`: of attackers where a blocker both SURVIVES and
  KILLS, the share actually blocked. Strong play takes nearly all; this is
  free value. Stock Forge blocks only 17.6% of attackers overall.
- `no_gain_block_rate`: blocks where the blocker dies, the attacker lives and
  nothing is gained. Should be ~0.
- `lethal_prevention_block_rate`: facing lethal unblocked damage, the share of
  combats where a block is made. Should be ~1.0.

**Attacking — normative**
- `attacker_commitment_ratio`: attackers declared / eligible untapped
  creatures. Stock is near 1.0 (attacks with everything).
- `retained_defense_adequacy`: untapped creatures left after attacking,
  against what opponents can swing back.
- `per_turn_attack_split_rate`: distinct defenders named per attack. Stock is
  98% single-target.

**Interaction — comparative and normative**
- `off_turn_interaction_rate`: share of disruption cast on an opponent's turn.
  Measured: stock on cEDH decks is **66.3%**, which is respectable.
- `threat_class_allocation`: is interaction spent on win attempts and engines,
  or on whatever was convenient?
- `board_wipe_firing_conditions`: how many of four public conditions held when
  a wipe was cast.

**Mulligans — normative, sim-only**
- `mull_rate` against the deck's hypergeometric floor F (share of opening
  sevens outside a 2-5 land window: 0.183 at 38 lands, 0.361 at 28). A
  correct pilot exceeds F, because land count is only one of three ship
  reasons. Stock Forge keeps ~97% of opening hands, i.e. **below the floor**.
- `mull_depth_distribution`.

## What has to be built

Block and attack quality need power/toughness AT THE MOMENT of the decision,
which the text log does not carry. The agent already emits this for itself
(`added_block value=0..3`), but stock emits nothing, so the two are not
comparable today.

The fix is a **neutral rubric observer in the shim** that scores every
combat for every seat from game state, regardless of which pilot is driving.
That makes stock and agent measurable on identical terms, and it is
mechanism, not strategy, so it respects the boundary.
