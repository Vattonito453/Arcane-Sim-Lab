# Arms ablation: does the agent block better than stock, and did the dials help?

**Yes to the first, no to the second**, and the second run is why I trust the
first.

Two independent runs of 128 games each (4 arms x 8 precon pods x 4 seat
rotations). Mixed pods: two plan seats and two stock seats per pod,
alternating, so both pilots play the same board, shuffle and opponents in the
same game and the comparison is paired within a game. Turn cap 90, wall clock
900 s. Scored by the shim's neutral observer (`RubricObserver`), which reads
live combat off Forge's event bus and therefore scores every seat identically
regardless of pilot.

```
python studies/behavior_rubric/run_arms.py --pods 8 --workers 10
python studies/behavior_rubric/observer.py studies/behavior_rubric/runs_arms
python studies/behavior_rubric/compare.py  studies/behavior_rubric/runs_arms
```

## Why there are two runs, and what that changed

The first run (`runs_arms_v1/`) had two biased attack metrics, so it was rerun
after fixing them. The block-side code is byte-identical between the runs,
which turned the second run into an accidental replication test. It failed for
some claims and passed for others, and that is the most useful thing this
study produced.

Per-arm significance **did not replicate**. The base arm went from engage
+0.075 (p = 0.028) and declined -0.193 (p = 0.012) in run 1 to +0.031
(p = 0.225) and -0.093 (p = 0.187) in run 2, on identical block-side code.
Games are not deterministic and run-to-run variance at n = 32 is larger than
those p-values implied. **Any single-arm p-value here is noise-dominated**; 6
metrics x 4 arms is 24 tests per run.

What replicated is the pooled effect and, more convincingly, the sign.

## Headline: the agent captures profitable blocks that stock leaves on the table

Pooled across all four arms (the dials do not affect these, see below), paired
within game, two-sided sign-flip permutation.

| metric | run 2 (clean) | run 1 (independent) |
|---|---|---|
| **freeCap** — of kill-and-survive blocks on offer, share taken | **+0.227**, p = 0.0023, 36 up / 2 down | **+0.171**, p = 0.025, 37 up / 5 down |
| **safeCap** — of survive-the-block chances, share taken | **+0.205**, p = 0.0001, 57 up / 7 down | **+0.157**, p = 0.017, 46 up / 7 down |
| **declined** — blockable attackers let through | **-0.154**, p < 0.0001 | **-0.138**, p = 0.0002 |
| **engage** — attackers blocked / faced | **+0.060**, p = 0.0002 | **+0.036**, p = 0.019 |

36 of 38 games favouring the agent on free-block capture, replicated at 37 of
42, is a far stronger statement than any p-value in this document.

Absolute rates, 128 games, 2,769 vs 2,736 attackers faced:

| | plan | stock |
|---|---|---|
| free block capture | **96.3%** | 76.0% |
| safe block capture | **95.0%** | 74.9% |
| engage | 21.3% | 17.5% |
| declined | 39.1% | 51.8% |
| chump share of blocks made | 52.8% | 60.4% |
| damage taken per combat | 8.03 | 8.41 |

The agent takes nearly every free block; stock misses about a quarter of them.
That is the concrete sense in which the agent "understands" combat better, and
it is the first like-for-like evidence that any part of the agent outplays
stock.

## Retracted: the damage claim

Run 1's base arm showed the agent taking 4.67 less damage per combat
(p = 0.010) and I wrote that up as a headline. **It does not replicate.**
Pooled, run 1 gives -1.60 (p = 0.094) and run 2 gives **+0.58 (p = 0.94)** —
opposite sign, both null. Absolute damage per combat is 8.03 vs 8.41, i.e.
effectively equal.

Blocking better does not translate into taking less damage, because the blocks
the agent adds are mostly profitable trades rather than damage prevention, and
a blocked attacker that dies still had its damage absorbed by a creature.

## Null: all three dials

Arm minus base on the paired difference, two-sample permutation, n = 32 vs 32.
**Nothing is significant; every p > 0.14.**

| arm | change | freeCap delta | declined delta |
|---|---|---|---|
| `blocky` | blockiness 0.24 -> 0.6 | -0.229 (p = 0.16) | -0.095 (p = 0.29) |
| `hold` | holdBackPerThreat 0.3, ratio 0.25 | -0.060 (p = 0.98) | -0.020 (p = 0.84) |
| `synergy` | derived 2-card engines in plan data | -0.038 (p = 0.88) | -0.133 (p = 0.15) |

Also null on both runs: `chumpShare`, `commit`, `keptEnough`.

Read this as **no detectable effect at n = 32 per arm**, not as "the dials are
harmful". The study can exclude a large effect, not a small one.

## Corrections to documented numbers

- **"Stock is near 1.0 (attacks with everything)"** is wrong. Measured against
  the sound denominator (bodies that could legally have attacked, via
  `CombatUtil.canAttack`), stock commits **71.6%** and keeps a body home in
  56.3% of its attacks. The agent is statistically indistinguishable at 68.1%
  (paired -0.006, p = 0.76). Caveat: mixed pods, so stock faces boards two
  plan seats helped shape.
- The earlier commitment figure of 62.3% was **biased** and should not be
  quoted. It divided by every untapped body, including summoning-sick
  creatures and creatures with defender. Measured here, only **74.1%** of
  "kept home" bodies could have attacked at all, so that denominator was
  inflated by a quarter.
- Stock's engage rate of **17.5%** on precons sits next to the previously
  recorded 17.6% on 256 all-stock precon games. Encouraging, but not a clean
  replication: that figure parses COMBAT log text rather than reading the
  event bus, and these stock seats sit in mixed pods.

## Limitations

- **No human column.** The observer scores Forge seats. Human blocking still
  comes from video coding and is not measured on these terms.
- **Gang blocks are scored per blocker.** Three creatures ganging to kill one
  attacker each score individually, so collective kills are undercounted. The
  controller uses the same scale, so the comparison is consistent, but the
  absolute quality mix is pessimistic for both pilots.
- **`lifeTaken` is a proxy.** It sums unblocked attacker power and ignores
  trample, deathtouch, prevention and damage aimed at planeswalkers.
- **Censoring.** 900 s kills: run 2 finished all 128, run 1 lost 32 to the
  clock. Censoring is symmetric between pilots because both sit in every pod.
  A token-copy board wedges Forge inside one stack resolution (every token
  entering play forces a static-ability recheck across all permanents), so the
  turn cap cannot fire and only the clock ends it. Stack sampling put one such
  JVM at 1220 s of CPU in `GameAction.checkStaticAbilities` under
  `TokenEffectBase.makeTokenTable`, with no shim frame involved. That is a
  Forge performance characteristic and it also bounds the product's worst-case
  sim time.
- **n = 32 per arm is underpowered** for the arm comparison. The pooled
  agent-vs-stock question has n ~ 127 and replicates; the arm question does
  not have the power to resolve small effects.

## What this changes

- Ship the blocking work at **`base` defaults** (hold-back off, blockiness
  0.24). It is validated and replicated.
- `holdBackRatio` / `holdBackPerThreat` stay **off**. `blockiness` stays
  **0.24**. Neither retune helped.
- Synergy lines need a **dedicated, larger run**, not a bundled arm.
- **Blocking is no longer the gap.** The agent already captures 96.3% of free
  blocks. The remaining headroom is chump-block policy (both pilots chump over
  half their blocks) and interaction timing (`tasks/21`), not more combat
  tuning.
