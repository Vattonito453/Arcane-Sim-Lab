# 21 — Interaction timing: spend answers when a plan is being executed

**Status: Half 1 built (shim 0.15.0, 2026-09-07); Half 2 open.** Half 1
is `instantDiscipline` in the shim's `PlanPlayerController`, dials
`holdInstants` / `holdInstantUntilRound` in the plan personality (shipped by
`deck_plan.py`), documented in `engine/SIM_CALIBRATION.md`. The acceptance
numbers below are still owed: measure a 0.15.0 run with
`studies/precon_predict/divergence.py` and `studies/agent_viability` before
the dial is considered validated. Backlogged from the prediction study
(2026-08-26) alongside attack hold-back, which IS built (shim 0.7.0).

## The measured problem

Walking the typed log of 256 stock games and 332 agent games of the
66-precon cohort (`studies/precon_predict/divergence.py`):

| | stock | agent (human-fidelity dials) |
|---|---|---|
| instants cast on an OPPONENT's turn | 19.2% | 22.3% |
| ALL spells cast off-turn | 2.4% | 2.7% |
| casts in a main phase | 89% | 89% |

**The agent plays solitaire in turn order.** Roughly 78% of instants are
spent on its own turn, which throws away the entire point of instant speed,
and it takes almost no action while opponents act. Tuning did not move it,
because the existing dials (`politics`, `counterThreshold`) only ever VETO a
counterspell the stock AI already wanted to cast. Nothing HOLDS an instant
for a better window, and nothing recognises a moment worth answering.

## What strong players actually do (researched, not assumed)

- **Threat assessment is about WHEN, not just what.** "Slow timer" cards
  (engines, value accumulators) have to be answered early, because once they
  have generated value the tempo cost of removing them is no longer worth it.
  Cards that must be answered on the turn they resolve are entirely
  answerable *if you know your window*.
- **Counterspells and removal are not interchangeable.** Removal handles
  what already resolved; a counter handles the cast. Decks want both, because
  the answer you have is not always the answer the moment needs.
- **One answer cannot police a table.** One-for-one counterspells are a
  mediocre use of mana in Commander, so an answer must be spent on something
  that matters, not on the first legal target.
- **Hold, then narrow.** A player often declines to answer threat A because
  they fear threat B later in the same turn cycle; as the cycle plays out and
  possibilities are eliminated, they commit. Holding is an information play,
  not passivity.

Sources: [Commander's Herald, "The Counterspell Conundrum"](https://commandersherald.com/the-counterspell-conundrum-rethinking-removal/),
[EDHREC, "How to Stop Losing to Counterspell in Commander"](https://edhrec.com/articles/how-to-stop-losing-to-counterspell-in-commander),
[Draftsim, "How Many Counterspells Should You Really Play"](https://draftsim.com/edh-how-many-counterspells/).

## The knowledge model, stated explicitly

Vincent's framing: *a good player understands the opponent's win condition
and interrupts when they are executing it too well; players with broader card
knowledge get a large edge for exactly this reason.*

That is already how the shim models familiarity. `DeckPlan.threatIndex()`
merges EVERY seat's `threat` list and high weights into one table, i.e. the
**full-decklist familiarity level** named in `SIM_CALIBRATION.md`. So the
agent is modelling an experienced player who knows what the table is playing.
That is a defensible target for a strong-play simulation, but it is an
ASSUMPTION and should become a dial (`familiarity`: full / archetype / none)
rather than an unexamined default, because a precon pod is mostly strangers
who do not know each other's lists.

## Design

Two halves. Neither adds strategy to Java: the trigger table is plan data.

**Half 1 — stop wasting them (small, likely most of the win).** In
`chooseSpellAbilityToPlay`, when the stock choice is an instant-speed
interaction card, it is the agent's own main phase, and the stack is empty,
decline and keep it. This alone should move the off-turn share, because an
instant that was never dumped is still available when a window arrives.
Guard: never hold when the card is the deck's own win line, when mana would
be wasted anyway, or past a `holdInstantUntilRound` cutoff.

**Half 2 — recognise the moment.** Spend when an opponent is executing a
plan, using data we already ship:
- they cast a card in their own `lines` (their win line), or
- the card is in `threatIndex` above `counterThreshold`, or
- their board reaches their archetype's payoff condition (the `produces` tag
  on a synergy line), which is the board-wipe trigger rather than the
  counterspell one.

And the "hold, then narrow" rule: with only one answer available and more
than one opponent yet to act this turn cycle, raise the bar — which is what
`politics` already tries to express, and should be re-grounded on this
rather than on open mana alone.

## Acceptance

- off-turn spell share rises materially from 2.7% (this is the headline
  number the change exists to move)
- instants cast on an opponent's turn rises from 22.3%
- no drop in win rate against stock in `studies/agent_viability` (the
  interaction layer must not become another handicap)
- `corr(interaction, sim)` moves toward the human value: interaction-dense
  decks are currently under-rewarded by the sim relative to humans

---

## Addendum, measured 2026-08-30: what the veto is actually declining

`counter_fire` / `counter_veto` events across every archived shim log, split by
run so plan versions do not blur together.

**All runs pooled: fire 90, veto 193.** Median threat of a spell countered 8.0,
of one let resolve 3.0, so the model separates cleanly on the whole. It fires
on commanders and payoffs (Atraxa, Kilo, The Astonishing Ant-Man, Deranged
Hermit, Triumph of the Hordes, Guardian Project) and lets ramp and removal
resolve (Farseek, Arcane Signet, Kodama's Reach, Cultivate, Sol Ring, Path to
Exile, Swords to Plowshares). That is the right shape.

**But the pooled figure is not current behaviour.** The same list also showed
Craterhoof Behemoth, Chatterstorm and Deepglow Skate being let resolve, which
reads as a broken threat model. Restricting to runs carrying threat signature
v2 plans (0966af5d0640, 65f2f33345ee, f8d3537d66b1, 65b1c47e9535, 1ea944e1a9a4)
gives **fire 19, veto 21** and none of those three cards appear. The 2:1 veto
ratio and the scary card names are both artifacts of pre-v2 plans, where a big
creature was only a threat if its keep-weight said so. `_pow(n) >= 5` already
fixed that class. Do not re-file it as a bug.

**The lead that survives, at n = 21 vetoes.** What still gets let through on v2
plans skews noncreature and X-spell: Finale of Devastation, Saw in Half, Whir
of Invention, Branching Evolution, Skullclamp, Coretapper. That is structural
rather than coincidental: `threat_set` in `engine/deck_plan.py` is
`weights >= 7` OR `creature power >= 5` OR commander, so a noncreature payoff
has exactly one way in, and an X-spell has none (its printed cost is low and it
is not a creature on the stack). Anything missing from the index falls back to
`Math.min(4, cmc)` in `threatOfSpell`, which is capped BELOW the default
`counterThreshold` of 5, so an unindexed card can essentially never be
countered.

Twenty one vetoes across five runs is a lead, not a result. Before acting on
it, gather more v2 runs and check whether the noncreature skew holds; if it
does, the fix is a third `threat_set` rule for noncreature payoffs and X
finishers, which is deck plan DATA and stays on our side of the boundary.
