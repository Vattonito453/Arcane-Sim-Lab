# 21 — Interaction timing: spend answers when a plan is being executed

**Status: Half 1 built (shim 0.15.0, 2026-09-07) and its acceptance
measured 2026-09-07 (see "Acceptance, measured" below); Half 2 open.** Half 1
is `instantDiscipline` in the shim's `PlanPlayerController`, dials
`holdInstants` / `holdInstantUntilRound` in the plan personality (shipped by
`deck_plan.py`), documented in `engine/SIM_CALIBRATION.md`. Backlogged from
the prediction study (2026-08-26) alongside attack hold-back, which IS built
(shim 0.7.0).

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

### Acceptance, measured 2026-09-07 (shim 0.15.0, 32-core Windows box)

Three arms, all on the same 0.15.0 jar so the only difference between the
first two is whether the seats run the plan agent.

| | stock control | humanized 0.15.0 | cohort baseline |
|---|---|---|---|
| instants cast on an opponent's turn | 20.0% (19/95) | **41.1%** (46/112) | 22.3% |
| all spells cast off-turn | 2.8% (20/713) | **5.7%** (48/840) | 2.7% |

Both arms: the four bundled decks (Atraxa, Drana, Nekusar, Kambal), 16 games
seat-rotated, `engine/run_sim.py` run ids `task21_v015` (stock) and
`task21_v015h` (humanized), measured with `studies/precon_predict/divergence.py`.
The stock control reproduces the cohort baseline, so the doubling is the
hold, not the pod. Two-proportion z: 3.25 (p 0.001) for instants, 2.79
(p 0.005) for all spells. Where the casts moved: stock fires most own-turn
instants at its first priority in the draw step (40 of 95); the agent cut
that to 26 and spent them in opponents' end steps and combat. 246 holds, 76
windows; every own-turn answer carried a reason (offTurn 39, pastCutoff 20,
inResponse 9, lethalOnBoard 4, handSize 2, savesAttacker 1, danger 1). No
draws, no crashes, no held answer discarded.

Win rate against stock, `studies/agent_viability/run_pilot.py --arm default`,
16 games per cell, 128 played, 115 decided: plan-seat win share **29.6%**
(34/115, 1 SE 4.3 pp, 95% CI 21.2 to 37.9), null 25%. The previous default
arm (2026-08-25) scored 15.8% (CI 6.3 to 25.3). No drop; the rise is 0.14.0
and 0.15.0 together, since no 0.14.0-only control was run. Output in
`studies/agent_viability/runs_015_default/`.

The first three criteria are met.

### Fourth criterion, measured 2026-09-08: FAILED on the precon cohort

`studies/precon_predict/runs_agent_015`, the full 66-deck, 768-game cohort
design with all seats on the 0.15.0 agent (same overrides as the 2026-08-26
agent arm; write-up in that study's README, "Agent 0.15.0 arm"). Decided
games only, via `decided.py runs_stock runs_agent runs_agent_015`:

| | stock | earlier agent | 0.15.0 |
|---|---|---|---|
| corr(interaction, sim) | +0.108 | +0.080 | **+0.238** |
| corr(interaction, human) | -0.047 | -0.053 | -0.047 |
| corr(sim, human) | +0.221 | +0.202 | +0.113 |
| corr(creatures, sim) | +0.153 | +0.059 | +0.217 |

The sim's reward for interaction density moved AWAY from the human value
(bootstrap change vs the earlier agent arm +0.185, 95% CI [-0.044, +0.404],
P(no increase) 0.053), and the sim became a weaker predictor of human
results. Per-deck: the win-rate shift from the earlier arm correlates +0.223
with interaction density; removal-dense precons that humans win 18 to 21%
with (Blood Rites, Abzan Armor, Silverquill Influence) gained 14 to 19 pp.
Holding removal makes removal decks win in the sim; human precon tables do
not reward removal density. The behaviour itself did carry over (34.1% of
instants off-turn against 19.7% stock and 21.7% earlier agent; 8,128 holds).

Caveats: 0.14.0 and 0.15.0 are bundled in this arm; the premise that
interaction-dense decks are under-rewarded by the sim was written before
the human correlation (-0.047) was computed, and on precons it is not true;
constructed and cEDH decks, where holding removal is most of the game, are
unmeasured. Keeping the dial on is therefore a product decision: realism and
agent strength against prediction fidelity on precons. If it stays on, refit
`engine/models/precon_predict.json` (currently fitted on the stock arm) on
this arm before trusting the playgroup prediction.

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
