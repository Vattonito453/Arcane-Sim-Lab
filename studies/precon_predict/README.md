# Predicting real playgroup win rates

**The product question.** Not "is our agent stronger than Forge" — that is
measured dead (`studies/agent_viability`, 313 games, best configuration lands
at stock parity). The question a deck-analysis tool has to answer is:
**given this decklist, how will it actually perform for a human playgroup?**

Nobody sells that answer today. Forge gives a win rate; it is the wrong number.

## Ground truth

`studies/precon_correlation/manifest.json`, sourced from playgroup.gg
(captured 2026-08-03):

- **66 Commander precons**
- **10,982 real human games**
- win rates **12.0% – 40.9%**, sd 5.6pp
- mean **24.22%**, games-weighted **23.98%**

That mean is the design tell. Against a 25% four-player null, it says the
humans played **precons against each other**, four to a pod.

## Two defects in the earlier attempt, both fixed here

The prior correlation study reported a null (Δr = −0.063) and concluded the
agent buys no predictive validity. It had two problems:

1. **Wrong opponents.** Each precon was sat against three fixed Commander 2014
   controls. Its own `STUDY_PLAN.md` §3d flags them as too weak, and every
   deck inflated by +6 to +32 pp against human results. This study puts cohort
   decks in pods with each other, matching how the ground truth was generated.
   Early evidence that it works: the mean sim-minus-human residual is now
   about −1 pp instead of +20 to +32 pp.
2. **A switched-off agent.** Those runs built plans from a cold card-fact
   cache (29–53% coverage on these decks), so weights, threat and keeps were
   mostly empty. `run_cohort.py` and `make_plans.py` refuse to run on degraded
   plan data.

Matching the generating process is also **4× cheaper**: a game scores four
decks, not one.

## Design

66 decks, R rounds. Each round is seeded, shuffles the cohort and cuts 16 pods
of four (two decks sit out, a different two each round). Each pod plays four
invocations with the deck order rotated one seat, so every deck sits in every
seat equally often and Forge's seat bias cancels. Clock 1200 s. Resumable, and
`tally.py` reads partial results so a long run can be analysed as it goes.

## Findings so far

**1. Forge under-blocks, measured.** `blockrate.py` parses COMBAT log lines
(Forge phrases a block as "assigned X to block Y", *not* "blocked Y with X" —
the obvious regex silently reports 0%):

| arm | block rate | decisions |
|---|---|---|
| stock Forge, cEDH decks | **14.7%** | 2,128 |
| stock Forge, precons | **20.8%** | in flight |

So roughly **80% of attacking creatures are never blocked**. This
independently reproduces the 14% recorded in `CLAUDE.md` at scale. It is the
mechanism behind the sim over-rating decks that win by attacking, and it
generates a falsifiable prediction: aggression should correlate POSITIVELY
with the sim-minus-human residual. Early data (7 games/deck, far too noisy to
quote as a result) has the predicted sign on every attack-flavoured feature:
creatures +0.37, evasion +0.23, aggression +0.18.

**2. Decklist statistics alone cannot predict human win rate.** Leave-one-out
over 14 features, against a "guess the mean" baseline of 4.25 pp MAE:

| model | MAE | LOO rho |
|---|---|---|
| guess the mean | 4.25 pp | — |
| best single feature (`creatures`) | 4.17 pp | +0.28 |
| best pair (`creatures`+`avg_cmc`) | **4.08 pp** | +0.36 |
| all 14 features | 4.65 pp | +0.21 |

Marginal at best, and most feature sets are *worse* than the baseline. **You
cannot get this from the list — you have to play the games.** That is what
makes simulation irreplaceable here rather than a convenience, and it is why
the expensive part of the product is the moat rather than the cost.

## How stock Forge diverges from human play

Blocking was the obvious axis and it is not the only one. Measured by walking
the typed log of 256 stock games in sequence (`divergence.py`), reconstructing
whose turn it is and which step each action falls in:

| # | divergence | measured on 256 stock games |
|---|---|---|
| 1 | **Under-blocks** | **17.6%** of attacking creatures blocked (2,048 of 11,657). ~82% get through |
| 2 | **Single-target attacks** | 98% of attack declarations hit exactly one opponent |
| 3 | **Wastes instants** | only **19.2%** of instants are cast on an opponent's turn; the rest go on the caster's own turn, throwing away the entire point of instant speed |
| 4 | **Plays solitaire** | **2.4%** of ALL spells are cast on someone else's turn. 89% of casts happen in a main phase. A human interacts constantly |
| 5 | **No threat focus** | sim over-disperses **1.52×** (true sd 8.45pp vs human 5.56pp): nothing punishes the leader |
| 6 | **Never mulligans** | keeps 7 in ~97% of hands (CLAUDE.md; stock seats emit no mulligan telemetry, so not re-measured) |
| 7 | **Cannot convert a combo** | measured separately in `studies/agent_viability` |
| 8 | **No politics or deals** | unmeasurable from logs, and probably not modellable |

### Which of these actually distort the ranking?

A behavioural difference only matters for prediction if it changes which deck
wins. Comparing what the sim rewards against what humans reward:

| feature | corr with **sim** | corr with **human** | disagreement |
|---|---|---|---|
| creatures | +0.157 | **−0.378** | **0.535** |
| evasion | +0.172 | −0.187 | 0.359 |
| aggression | +0.253 | −0.070 | 0.323 |
| total_power | +0.218 | −0.037 | 0.255 |
| removal | +0.157 | −0.069 | 0.226 |
| counters | −0.169 | −0.070 | 0.099 |
| avg_cmc | +0.151 | +0.205 | 0.054 (agree) |
| draw | −0.161 | −0.121 | 0.040 (agree) |

**The combat axis is the whole error.** Everything attack-flavoured disagrees
by 0.25–0.54 correlation units; curve and card draw agree. Divergences 1, 2
and 5 all push that same way, which is why they are the ones the agent arm
turns on.

The instant-timing and off-turn findings (3 and 4) are large behaviourally but
show only weak ranking distortion **in this cohort**, because precons carry
little interaction (density 0.06–0.28). Expect them to matter much more for
constructed or cEDH decks, where holding up removal is most of the game. That
is a real limit on how far a precon-trained correction generalises.

### Still unmeasured

Removal target choice, crack-back awareness, sequencing quality and mulligan
quality on stock seats all need either board-state reconstruction or telemetry
stock Forge does not emit. They are not claimed either way here.

## Why this is a wedge

The two halves are both ours and neither is easy to copy: **the compute** (a
66-deck cohort is ~770 games and hours of CPU) and **the calibration data**
(10,982 human games mapped to decks). A competitor with Forge alone gets a
number that is off by 20–30 points and does not know it.

`engine/predict.py` applies the fitted correction, reports an interval from
out-of-sample error rather than a fitted standard error, and returns the
per-feature contributions so the product can say *why* the number moved.

## Reproduce

```bash
python engine/deck_plan.py <decks> --fetch          # warm, or the gate refuses
python studies/precon_predict/run_cohort.py --rounds 6 --games 2 --workers 14
python studies/precon_predict/tally.py runs_stock
python studies/precon_predict/analyze.py --arm runs_stock
python studies/precon_predict/blockrate.py "studies/**/*.jsonl"
```


---

# VERDICT (2026-08-26, both arms complete, 1,534 games)

## The model works, is significant, and replicates

Predicting a precon's real playgroup win rate from a stock-Forge simulation
plus two decklist statistics:

| | MAE | rank corr |
|---|---|---|
| guess the mean | 4.249 pp | — |
| decklist stats only | 4.063 pp | +0.360 |
| **survival + creatures + avg_cmc** | **3.946 pp** | **+0.477** |

Significance, by permutation test (shuffle the human win rates, refit the
whole leave-one-out pipeline, 2,000 times):

- **P(rank corr this high by chance) < 0.0005**
- **P(MAE this low by chance) = 0.002**

And it holds up out of sample. Fitted on the 2026-08-03 capture and scored
against the independently refreshed 2026-08-26 capture: **r +0.495, rho
+0.499, MAE 3.582 pp against a 3.967 baseline** -- better out of sample than
in.

Context for the ceiling: the ground truth is only ~46% reliable, so no
predictor can exceed r = 0.674. At ~0.48-0.50 the model is at roughly 72% of
what is achievable against these numbers.

**Earlier drafts of this file called the result "not statistically
significant". That was wrong, and it was a wrong TEST rather than a wrong
number.** A bootstrap on the MAE difference against a baseline is very low
powered here -- the entire reducible MAE range is 1.19 pp -- so it could not
resolve a real effect. The permutation test is the right instrument and it is
decisive.

## The agent did NOT beat stock at prediction, and did not lose to it either

On decided games (see below for why that qualifier is load-bearing):

| metric | stock | agent |
|---|---|---|
| corr(sim, human) | +0.221 | +0.202 |
| rank corr | +0.255 | +0.233 |
| corr(creatures, sim) | +0.153 | **+0.059** |
| reliability (own p) | 0.688 | 0.645 |
| true sd | 9.58 pp | 10.13 pp |

The two are equivalent predictors. The human-fidelity work did measurably
reduce the aggro bias (+0.153 -> +0.059 against a human value of -0.378),
which is the one mechanism claim that survives.

## Three claims retracted, all mine

1. **"The agent is worse at prediction."** False. It looked worse because
   34.1% of agent games were killed by the 1200 s wall clock against 9.7% of
   stock games, which deflated every agent win rate to a 16.2% cohort mean
   against a 25% null. On decided games the two arms are a coin flip.
   The censoring is not benign: agent timed-out games have FEWER turns than
   its finished ones (43.0 vs 53.0), so the agent is dying to the clock
   mid-game because it deliberates more per turn, and the censoring rate
   correlates +0.239 with `creatures` -- the very feature the mechanism claim
   was about.
2. **"Over-dispersion fixed, 1.52x -> 1.08x."** False. That used a fixed
   p=0.25 binomial noise term against an arm whose actual mean was 16.2%,
   which inflates only that arm's noise by 1.38x. With each deck's own p the
   agent is slightly MORE dispersed than stock, not less.
3. **"Reliability collapsed 0.65 -> 0.48, destroying deck-strength signal."**
   Same artifact. Own-p reliability is 0.688 vs 0.645 -- barely moved -- so
   the "compression destroyed the signal" explanation was never needed.

`decided.py` now computes every arm-to-arm number on finished games with
each deck's own p, so this class of error cannot recur silently.

## What still needs doing

- **Re-run the agent arm at a longer clock.** At 34% censoring it is not on
  the same measurement scale as stock, and no arm comparison from it is
  fully trustworthy even after restricting to decided games.
- The ~284-decks-for-significance figure quoted earlier is a 50%-power
  number and understates the requirement by roughly 2x.

---

# Synergy lines + attack hold-back: VALIDATION FAILED, do not ship

`runs_synergy/` (shim 0.7.0, 226 games, 2 rounds) tested the two engine
changes before pushing them to prod, as asked.

## The machinery works

| event | agent arm (no synergy) | synergy arm |
|---|---|---|
| `combo_cast` | 0 | **247** |
| `combo_hold` | 0 | 45 |
| `hold_back` | n/a | 74,247 |
| block rate | 25.8% | 26.2% |

Synergy lines gave 61 of 66 precons a pursuable win condition where Commander
Spellbook returns nothing, and the agent does now pursue it.

## But prediction got worse, and hold-back is badly over-tuned

Decided games only:

| | STOCK | AGENT | SYNERGY |
|---|---|---|---|
| corr(sim, human) | **0.221** | 0.196 | 0.151 |
| rank corr | **0.255** | 0.225 | 0.142 |
| LOO model rho | **0.477** | 0.398 | 0.284 |
| reliability | 0.688 | 0.629 | 0.499 |

**Do not ship either change on this evidence.** Two honest caveats on how
strong that conclusion is: the synergy arm has only 11 decided games per deck
against stock's 43, and it lost 34.5% of its games to the wall clock, so it
is both undersampled and censored. It is not a clean refutation. But it is
certainly not the validation the changes needed.

**`hold_back` fired 329 times per game.** That is the smoking gun.
`holdBackPerThreat=1.0` keeps one body per incoming untapped enemy creature,
capped by `holdBackRatio=0.5`. In a go-wide precon meta the opponents'
untapped creature count is large every single turn, so the cap binds and the
agent keeps HALF ITS BOARD home on essentially every combat. No human plays
that way, and it plausibly explains both the extra stalling (34.5% timeouts,
median 53 turns) and the loss of signal.

## What to do next

1. Retune hold-back an order of magnitude down -- roughly one blocker per
   three or four incoming threats (`holdBackPerThreat` ~0.25-0.33) and a
   `holdBackRatio` nearer 0.25 -- then re-measure. The current setting is not
   a test of the idea, it is a test of a caricature of the idea.
2. Re-run with the shim 0.8.0 **turn cap** (`--max-turns 80`, clock demoted to
   a hang detector) so the arm is not 34% censored on deliberation speed.
3. Only then decide whether synergy lines earn their place, separately from
   hold-back -- this arm changed both at once and cannot separate them.

---

# Agent 0.15.0 arm (2026-09-08): the hold works, and prediction gets worse

`runs_agent_015/`: the same 66-deck, 6-round, 768-game design as the two
2026-08-26 arms, all four seats on the plan agent, same personality overrides
as `runs_agent` (`plans_agent_015.json`), so the only agent differences are
what shipped since: 0.14.0 attack targeting and finisher discipline, and the
0.15.0 instant-speed hold (`holdInstants` 1.0, `holdInstantUntilRound` 10).
Run on the 16-core Windows box, 14 workers, shim jar at commit 220160b.
Task 21's fourth acceptance criterion is what it was run for.

Two operational notes. `run_cohort.py` now passes `--max-turns 120` (the two
earlier arms had no cap); it never fired, because the censored games are
in-turn stalls, not long games. And the clock: a first attempt at 3600 s was
abandoned after its undecided games came back at 23 to 64 turns with every
player alive, i.e. the agent spending two to three minutes per turn on token
boards (Sliver Swarm, Squirreled Away, Animated Army), which a longer clock
only prolongs. The run was resumed at 1200 s; 20 of 384 cells (5%) kept the
3600 s clock, so a game they decided between 20 and 60 minutes would have
been censored in the rest of the arm.

## Behaviour: the hold does what it says

`divergence.py`, all games:

| | stock | earlier agent | 0.15.0 |
|---|---|---|---|
| instants cast on an opponent's turn | 19.7% | 21.7% | **34.1%** |
| all spells cast off-turn | 2.6% | 2.7% | **3.8%** |
| attackers blocked | 17.7% | 25.8% | 24.4% |
| games killed by the clock | 9.7% | 34.1% | 30.5% |
| median game | 48 player-turns | 49 | 48 |

8,128 holds and 1,785 windows. Of the windows, 754 were an opponent's turn and
682 were `pastCutoff`: with a median game of 12 rounds, the round-10 cutoff
releases the hold for most of the late game. Censoring is unchanged in kind
(deliberation speed, not game length) and its per-deck rate no longer tracks
creatures (+0.058, against +0.239 in the earlier arm).

## Prediction: the criterion fails

`decided.py runs_stock runs_agent runs_agent_015`, decided games only, each
deck's own p:

| | stock | earlier agent | 0.15.0 |
|---|---|---|---|
| decided games per deck | 43 | 30 | 32.5 |
| corr(sim, human) | +0.221 | +0.202 | **+0.113** |
| rank corr | +0.255 | +0.233 | +0.140 |
| corr(creatures, sim) | +0.153 | +0.059 | **+0.217** |
| corr(interaction, sim) | +0.108 | +0.080 | **+0.238** |
| corr(interaction, human) | -0.047 | -0.053 | -0.047 |
| reliability (own p) | 0.688 | 0.645 | 0.657 |
| LOO model rho (sim + creatures + avg_cmc) | +0.477 | +0.398 | +0.360 |

The criterion was that `corr(interaction, sim)` moves toward the human value.
It moved the other way, from +0.08 to +0.24 against a human -0.05. Bootstrap
over decks (4,000 resamples, paired): the change against the earlier agent
arm is +0.185, 95% CI [-0.044, +0.404], P(no increase) 0.053; against stock
+0.140, CI [-0.048, +0.313]. Directionally firm at 66 decks, one SE short of
conventional significance, and the same direction on every read after round
two. `corr(sim, human)` fell by 0.08 to 0.11 with CIs that include zero.

Mechanism, from the per-deck shifts: a deck's change in decided win rate from
the earlier agent arm correlates +0.223 with its interaction density and
+0.159 with its creature count. Blood Rites (interaction 0.18) went 48% to
62% while humans win 18% with it; Abzan Armor (0.22) 29% to 45% against a
human 20%; Silverquill Influence 31% to 50% against 21%. Holding removal for
an opponent's turn makes removal-dense precons win more in the sim, and
human precon tables do not reward removal density. The aggro-bias reduction
the earlier arm bought (creatures +0.153 to +0.059) did not survive either;
0.14.0's open-target re-aim is the likely cause, but this arm cannot separate
0.14.0 from 0.15.0.

## What this does and does not say

- The hold is behaviourally right and mechanically sound; three of task 21's
  four criteria pass (off-turn shares up, no win-rate drop in
  `studies/agent_viability`).
- On PRECONS it makes the sim a slightly worse predictor of human results. The
  README's earlier caution stands: precons carry little interaction (density
  0.06 to 0.28) and human precon tables punish creatures, not removal, so this
  cohort is the wrong place to expect the hold to help prediction. Whether it
  helps on constructed or cEDH decks is unmeasured.
- Keeping the dial on is a product decision, not a measurement one: realism
  and a stronger agent on one side, a prediction model fitted on the stock
  arm that now sees agent-produced win rates with a different bias on the
  other. If the dial stays on, refit `engine/models/precon_predict.json` on
  this arm before trusting the playgroup prediction, and re-measure.
