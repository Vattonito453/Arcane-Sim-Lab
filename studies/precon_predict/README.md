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
