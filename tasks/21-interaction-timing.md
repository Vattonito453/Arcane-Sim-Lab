# 21 — Interaction timing: spend answers when a plan is being executed

**Status: specced, not built.** Backlogged from the prediction study
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
