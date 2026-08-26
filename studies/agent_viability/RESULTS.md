# Can our agent beat stock Forge? — results

**Status: COMPLETE 2026-08-25. 3 arms, 313 games, one plan seat vs three
stock Forge seats on combo-live cEDH pods.**

## Why this study exists

Three prior studies concluded the agent is "no better than stock Forge."
Every one of them measured an agent that was **switched off**:

- The 8 Forge precons behind the 1536-game head-to-head have **zero combo
  lines**, and had 29-53% card-fact coverage at the time. With no lines,
  `lineOfSight()` returns null on its first branch, which disables combo
  pursuit, line-piece cast priority, tutor casting, greed and combo-mode
  tutor steering together. What stays live is blocking, attack splitting,
  the counterspell veto and kingmaker re-aim — every survivor defensive.
- That predicts the one signal that reproduced across both 768-game
  designs: the plan arms survived longer and won the same.

The cEDH pods in `studies/human_ceiling` warm to 3-29 lines per deck at
0.95-1.00 coverage, so the machinery is live there. `run_pilot.py` refuses
to run on degraded plan data, so the crippled agent cannot be measured by
accident again.

## Design

One plan seat against three stock Forge seats, in the same pod, plan seat
rotated through all four positions so Forge's seat bias cancels. Null is
**25%**: if the agent is no better than stock, it wins its share.

Pods: `n7WpsqsZtdQ` (treasure/toolbox) and `2iA_Jt0d6sM` (elves/big mana).
Clock 900 s, shim 0.5.0.

## Results

| arm | what changed | decided | plan-seat win share | 95% CI |
|---|---|---|---|---|
| `default` | ships today | 57 | **15.8%** ± 4.8 | [6.3, 25.3] |
| `winmax` | self-handicaps off | 116 | **21.6%** ± 3.8 | [14.1, 29.0] |
| `nocombo` | win-max, and combo pursuit off too | 117 | **24.8%** ± 4.0 | [17.0, 32.6] |

`winmax` sets `greed 1.0` (never hold the winning piece), `triggerMiss 0`
(never decline a beneficial trigger), `splitAttacks 0` (focus damage rather
than spreading it), `politics 0` (do not raise the counterspell bar because
someone else has mana). `nocombo` is win-max with `lines` dropped, so the
agent keeps plan weights, mulligan policy, threat index and Stage 2 tutor
targeting but never diverts into assembling a combo.

## What it says

**The agent scores highest when it does least.** 15.8 → 21.6 → 24.8, and
24.8% is the 25% null to within a rounding error. Every step that removes
our behavior moves the number up, and the best configuration is the one
closest to stock Forge.

Read the significance honestly: no single pairwise difference clears two
standard errors (`nocombo` − `winmax` = +3.2 ± 5.5; `nocombo` − `default` =
+9.0 ± 6.3), and all three intervals overlap. What carries the weight is
the **monotone ordering across three arms plus 1536 games of prior null**,
not any one comparison.

Two conclusions, at different confidence:

1. **The self-imposed handicaps cost real win rate and buy nothing**
   (~6 pp). They exist to make the agent look human by playing worse, and
   the correlation study already found humanization buys no predictive
   validity. They are pure cost. Defaults changed in `deck_plan.py`.
2. **Combo pursuit is a half-built bridge.** Assembling a line costs mana
   and cards; the payoff never arrives, because the agent cannot convert an
   assembled line into a win (`CLAUDE.md` already documents
   assembled-but-not-converted as the expected reading). You pay the cost
   and never collect. Dropping it scores +3.2 pp — suggestive, not proven,
   but it is the only mechanism consistent with every observation we have:
   Portal fetched and never used, lines assembled and never converted,
   14 greed holds in 8 games, storm decks that never win in sim.

## What this does NOT say

It does not say the agent is worthless. It says the *agent-as-stronger-
player* thesis is dead **as currently built**, which is a different claim
from "cannot be built".

It also leaves the product's real question untested. This study asks
"is our agent stronger?" A deck-analysis tool actually needs "does our sim
predict how this deck performs for a human?" The correlation study that
asked that was run on precons with the same crippled agent, so **predictive
validity has never been measured with a live agent either.**

## What follows

- **Done: change the shipped dials.** ~6 pp for a data-only change.
- **Decide on combo pursuit: finish it or stop paying for it.** Conversion
  is the one investment with a mechanism that plausibly beats stock —
  humans win these pods at round 5 *by converting*, and Commander Spellbook
  already publishes what each line produces, so the execution steps can
  cross the boundary as data with the shim as interpreter. Until then,
  pursuit costs games.
- **Re-run the correlation study with a live agent** before concluding
  anything about predictive validity.

## Reproduce

```bash
python engine/deck_plan.py <pod decks> --fetch      # warm, or the gate refuses
python studies/agent_viability/run_pilot.py --arm default  --games-per-cell 16 --workers 12
python studies/agent_viability/run_pilot.py --arm winmax   --games-per-cell 16 --workers 12
python studies/agent_viability/run_pilot.py --arm nocombo  --games-per-cell 16 --workers 12
```
