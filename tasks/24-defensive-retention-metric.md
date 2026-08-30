# 24 — Make defensive retention mean something in a four player pod

**Why:** the scorecard has a defence metric that cannot currently be read as
one. `keptEnough` is the share of attacks where the attacker held back a
creature whose toughness beats `backBiggest`, and the shim computes
`backBiggest` as the biggest power across **every other seat's** untapped
creatures (`RubricObserver.java`, the "what can swing back next turn" loop).

In a four player game that is a table wide maximum. One opponent resolving a
7/7 puts the bar out of reach for all three other seats at once, so the figure
collapses for reasons that have nothing to do with how any of them played.
Measured on a native 0.13.0 run, all four decks landed between 9% and 29%:

| Deck | keptEnough | commitment |
|---|---|---|
| Ur-Dragon B3 | 8.7% | 94.7% |
| Ant-Man | 18.2% | 75.0% |
| Skrat's Revenge | 28.6% | 48.5% |
| Atraxa Counters B3 | 11.1% | 71.6% |

Four decks with very different commitment ratios converging on the same low
band is the signature of a shared denominator, not of four decks independently
forgetting to block.

The copy has already been corrected to describe what is actually measured
("held a blocker that survives the table's biggest attacker"), so nothing
currently lies. But the metric still cannot answer the question the dimension
list asks, which is whether the agent splits its attacks sensibly or alpha
strikes into a crack back.

**Size:** small on the shim, small on the engine. No UI work beyond a label.

## What to change

- **Shim.** Alongside `backBiggest`, emit `backBiggestPerSeat` (the max power
  per opposing seat, so the engine can pick a threat model) or, more simply,
  `backBiggestSingle`: the largest power on the single most threatening
  opposing board. One seat attacks you at a time; surviving the whole table is
  not the standard a human plays to.
- **Engine.** Recompute `keptEnough` against the new field, keep the old one
  under its current name so archived runs still parse, and gate the new read on
  its own presence the way `blocking` already gates on `freeOpportunities`.
- **Do not** silently redefine `keptEnough` in place. Runs already on disk
  carry the old field; a redefinition makes two incomparable numbers share a
  name, which is the failure mode `readapt.py` exists to avoid.

## Acceptance criteria

The shared definition of done in `tasks/README.md`, plus:

1. `engine/tests/test_scorecard.py` pins the new rate against a fixture where a
   seat holds a 4/4 while one opponent shows a 6/6 and another a 2/2: the
   table wide reading is "not enough", the per seat reading is "enough against
   the seat that could actually attack".
2. Re-adapting an archived run does not change its old `keptEnough`.
3. A run recorded before the shim change reports the new read as absent, not as
   zero, and the UI says "not recorded" rather than drawing a bar.
4. The measured spread across a four deck pod is no longer a flat band; if it
   still is after the change, say so in the doc rather than shipping a metric
   that looks informative and is not.

## Not in scope

Changing how the agent actually attacks. This task makes the behaviour
measurable; whether to hold more back is a separate question and should not be
tuned against a metric until that metric is trustworthy.
