# Precon-8 rank check for R1: PASS

Read 2026-09-29 with `read_rank_check.py`, unchanged since the pre-registration commit (c63ef32, amendment 1 included, before any game of the run). The reading was taken once, after the run finished.

**Verdict, per PREREG.md: PASS.** Fed the R1 pilot's simulation, the playgroup model ranks the 66 precons at **rho = 0.510** (Spearman, predicted against human win rate), against the pre-registered threshold of 0.40. The record is appended to `engine/models/rank_checks.json` and ships with R1: production runs on the R1 pilot keep the label "Fit on stock Forge games; this run used Sim Lab's pilot." and add that the rank check passed.

## The run

| | |
|---|---|
| Pilot | `plan/0.17.0/v2` in every cell: shim 0.17.0 (jar `c2273bef...`, built from `b8894e1`, whose tree is identical to the `v0.17.0` tag production builds), version-2 plans with every fix flag, all four seats plan-piloted |
| Plans | one file for all 66 decks, SHA-256 prefix `3d6cfe78fb59` |
| Model | `cba8b3be2fd29455`, the fingerprint of the served `engine/models/precon_predict.json` |
| Bed | the 66-deck cohort in its existing pods, rounds 0 to 5, 384 cells |
| Games | **768 of 768**, 0 missing or short cells, 66 decks with at least 16 games |
| Settings | 900 s clock, 120-turn cap, `-Xmx3g`, **8 JVMs as pre-registered**, seeded per cell |
| Wall time | 9.5 hours (first cell 2026-09-28 14:56, last write 2026-09-29 00:26), under the 11 to 15 hour estimate because games averaged 348 s against the 392 s assumed |

Decidability rules (64 decks, 730 games, one pilot id) are all met.

## Result

| Metric | Value | Note |
|---|---|---|
| **Spearman(predicted, human)** | **0.510** | **gate: >= 0.40, PASS** |
| Pearson r | 0.503 | |
| MAE | 3.72 pp | documented LOO MAE 3.95, guess-the-mean 4.25 |
| Mean bias | +0.25 pp | |
| Permutation null (survival shuffled across decks) | mean 0.359, 95th percentile 0.467 | **P(null >= 0.510) = 0.0077** |
| Sim-noise replicates | mean 0.475, sd 0.037, 2.5th percentile 0.405 | |
| Decklist floor (survival held at its mean) | 0.407 | the simulation adds about +0.10 |
| Survival alone | 0.276 | |
| Against the 2026-08-26 capture | 0.480 | |
| With live deck features (the served path) | 0.479 | 14 decks' features differ from training (card-cache drift) |
| Decided-game win rate against human | 0.224 | survival remains the better signal, as at fit |
| Survival mean, sd | 31.9, 10.6 | fit: 30.2, 11.5 |
| Timed out | 10.7% of games | stock arm 9.7%, 0.15.0 arm 30.5% |
| Game length | mean 348 s, median 256 s | consistent with `TYPICAL_GAME_SECONDS = 240` |

For comparison, read with the same reader: the stock arm (the model's own pilot) scores 0.544 in sample and the 0.15.0 plan arm 0.508. The R1 pilot sits with them.

## What the pass does and does not show

The pre-registration stated the check's limit before the run: at 66 decks, a pilot whose simulation carries no deck information still passes 0.40 about a quarter of the time. This reading is not that case. The observed 0.510 is above the uninformative null's 95th percentile (0.467), with a permutation p-value of 0.0077, and above the decklist floor by about 0.10. So the R1 pilot's simulation carries real deck-ranking information into the model, at about the level stock Forge's did.

It does not show that the model is well calibrated per run. Production runs have 8 to 16 games per deck against 48 here, so a single run's survival, and its prediction, are noisier than the page's interval says. That limitation is unchanged and recorded in the PREREG.

## Protocol notes

1. **Parallelism.** The run used the pre-registered 8 JVMs. The prediction-label agent had suggested 12 to fit one night; that was not used, because the PREREG fixes 8 and CPU load can change the AI's decision timeouts.
2. **Jar.** The jar is the G0a-tested `b8894e1` build. Production builds from the `v0.17.0` tag on `33243d5`, the squash merge of the same tree, so the pilot is the same code. Only the jar's recorded build commit differs.
3. **No deviations** from the metric, threshold or decision rules. The one-game smoke (`OUT/smoke`) was never read.

## Carried forward

- **Card-cache drift:** 14 of 66 decks have live features that differ from the training features (served-path rho 0.479 against 0.510 on training features). This is for the refit after G3, where the reference features must be chosen.
- **Next rank check:** at the next pilot-changing release (R2, R2.1, R3). A refit needs its own check, because records are keyed to the model fingerprint.

## Reproduce

```bash
py studies/rank_check_r1/read_rank_check.py    # from a checkout at the pre-registration code; $RANK_CHECK_OUT holds the runs
```

Raw JSONL, plans and the full reading (`reading_runs.json`) stay under the scratch output folder, outside git.
