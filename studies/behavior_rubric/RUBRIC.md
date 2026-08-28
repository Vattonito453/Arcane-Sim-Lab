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
  free value. Stock block rate depends on the deck population: 14.7% on cEDH
  (2,128 decisions), 17.6% on 256 all-stock games (11,657). Quote the one that
  matches the population under test.
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

## The neutral observer (built, shim 0.9.0)

Block and attack quality need power/toughness AT THE MOMENT of the decision,
which the text log does not carry. The agent already emitted this for itself
(`added_block value=0..3`), but stock emits nothing, so the two were not
comparable: every behavioural number we had came from our own pilot's
telemetry on one side and from video coding on the other.

`RubricObserver` (in the shim) reads the LIVE combat off Forge's event bus and
scores every seat identically regardless of pilot. It is a pure read and never
touches a decision. It is mechanism, not strategy, so it respects the GPL
boundary. Score its output with `studies/behavior_rubric/observer.py`.

Two hooks:

- `GameEventAttackersDeclared` — bodies committed vs untapped bodies kept
  home, spread across defenders, and what the rest of the table could swing
  back (`backBiggest`).
- the first combat damage step — blocks made, each on the same 0-3 scale the
  controller uses (3 kills and survives, 2 trade, 1 wall, 0 chump), plus the
  blocks that were available and declined.

Blocks are scored at the damage step rather than on `GameEventBlockersDeclared`
because Forge posts that event per declaring player: a seat that blocks nothing
emits nothing, and "declined to block" is exactly the behaviour under
measurement. The damage step is reached on every combat regardless.

Two traps the implementation encodes:

- The declined-block counters use **greedy assignment, biggest threat first**.
  A body can only block once, so scoring each unblocked attacker against the
  whole pool independently over-counts what was left on the table.
- `legalMissed` counts any legal block declined, and exists as the check that
  `CombatUtil.canBlock` is actually answering at this phase. Without it a
  broken predicate would zero the profitability counters in a way
  indistinguishable from genuinely having no option. Verified non-zero.

**Measure the blocking axis on precons, not cEDH.** The cEDH pods that carry
human traces barely block at all: one game produced 11 available blockers
across 30 block records, because those decks run almost no creatures, and the
declined blocks that did occur were 0/1 bodies facing bigger attackers. The
axis has no discriminating power there. cEDH pods stay the right place for the
interaction axis.

## First result from the observer

See `ARMS_RESULTS.md`. 128 games, 4 arms, mixed pods, paired within game.

The agent blocks materially better than stock on identical boards: it engages
25.5% of attackers to stock 15.1% (paired +0.075, p = 0.028), lets through
41.6% of blockable attackers to stock 60.4% (-0.193, p = 0.012), and takes
6.90 damage per combat to stock 10.84 (-4.67, p = 0.010). Restricting to
decided games strengthens all three.

The observer puts stock in the same range as the earlier text-log
measurements, which is reassuring but is **not** a clean replication. Those
numbers are not one number: 14.7% is cEDH decks over 2,128 decisions, 17.6% is
256 all-stock games over 11,657, and 20.8% is precons marked in flight. They
also come from parsing COMBAT log text rather than reading the event bus, and
the observer runs in MIXED pods, so its stock seats face boards that two plan
seats helped shape. Compare a precon figure to a precon figure, and do not
treat any of this as the observer validating itself.

None of the three dials tested (blockiness 0.6, hold-back 0.3/0.25, synergy
lines) improved the edge at n = 32 per arm.
