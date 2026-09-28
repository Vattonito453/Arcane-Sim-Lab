# Precon-8 rank check for R1: does the playgroup model still rank decks under the R1 pilot?

Written and committed **before any game of this study is played**, the one-game smoke included. `run_rank_check.py` refuses to play unless this file, itself and `read_rank_check.py` are committed and unchanged, so the reading cannot drift toward the data. Every cell records the pre-registration commit in its `.cell.json`.

Plan references: `tasks/25-repair-plan.md` WS11 task 11, section 3.0 (test beds, "Precon-8"), section 4.3 week 3 ("Precon-8 rank check for R1"), decision 19 in `tasks/README.md` (label from R1; a rank check at each pilot-changing release; suppress on a fail; refit after G3), decision 17 (precons are for calibration only; this is calibration). The model is `engine/models/precon_predict.json`; its fit and validation are in `studies/precon_predict/README.md`.

## The question

The shipped model predicts a precon's real playgroup win rate from `survival` (the share of games in which the deck's seat is still alive at the end, over every game it played, censored games included), `creatures` and `avg_cmc`. It was fitted on the stock Forge arm (`runs_stock`, 766 games). Every production run from R1 is piloted by Sim Lab's plan agent on shim 0.17.0 with version-2 plans. The run page now says "Fit on stock Forge games; this run used Sim Lab's pilot." This check decides whether, fed the R1 pilot's simulation, the model still ranks decks well enough to be shown at all.

## What "Precon-8" means here

The plan defines the bed only as "existing precon pods, as today, calibration only". This study fixes it as:

- **The existing precon cohort:** all 66 decks of `studies/precon_predict/cohort.json`, with the human win rates of the playgroup.gg capture of 2026-08-03 that the model was fitted against.
- **In the existing pods:** `run_cohort.pods_for_round(cohort, round)` for rounds 0 to 5 (seeded `Random(1000 + round)`): 16 pods of four per round, two decks sitting out, a different two each round. These are the same pods, in the same order, that the stock arm and the 0.15.0 arm played.
- **As today:** the stock arm's design exactly: each pod plays 4 seat rotations x 2 games per round, so **384 cells, 768 games, 48 games for the median deck** (every deck sits in every seat equally often within its pods).
- **"8"** is read as the 8 parallel JVMs the plan's wall times assume. It is not read as "8 pods": a rank check over 32 decks cannot resolve the threshold below (the permutation null alone has sd 0.068 at 66 decks), and it would not use the deck set the model's documented figures were measured on.

Matching the fit's design also matches the **sampling noise of the survival feature** (48 games per deck): the weight the model puts on survival was fitted at that noise level, and fewer games per deck would inflate survival's spread and so its effective weight in the ranking.

## The pilot (R1)

- Shim **0.17.0**, commit b8894e1, jar SHA-256 `c2273bef30d7cd9edb20d711f81bce01444470a91e9d15bbf23f2e3fd3081dfd` (the jar G0a tested and passed, `studies/hotfix_g0/RESULTS.md`). The runner refuses any other jar.
- **Version-2 plans with every fix flag** (`tutorReach`, `commanderTutorZone`, `noForcedChoices`, `graveyardDest`), built once for all 66 decks by `engine/deck_plan.build_plans(..., plan_version=2, fix="all")` at the repository commit the runner runs from (recorded per cell), no personality overrides (production builds plans the same way), `factsCoverage` at least 0.9 for every deck or the build refuses. `MTG_PLAN_FIX` must be unset or `all`, `MTG_PLAN_VERSION` unset or `2`, `MTG_PLAN_FEEDBACK_APPLY` not `1`.
- **All four seats** `plan:SimLabHuman`, as in production.
- The pilot id `engine/pilot.py` derives from the shim's meta records must be `plan/0.17.0/v2` in every cell; that id is what the record is keyed by and what `/results/{file}/prediction` matches production runs against.

## Settings

900 s per-game clock and 120-turn cap (production), `-Xmx3g` (as G0a and the cohort arms; production uses 4g, which changes no decision unless a JVM runs out of heap, and such a cell fails visibly), 8 JVMs. Forge's shuffles are seeded per cell with `--seed-forge 2026101600 + round*1000 + pod*10 + rotation`, and the seed is recorded per cell (whether one seed reproduces one deal exactly is the plan's seeding experiment; nothing here depends on it). Production does not seed, which changes the deals and not the pilot. A JVM that outlives `2 x (900 + 150) + 300 = 2,400 s` is killed as hung and its cell is left incomplete.

## The metric (primary, the only gate)

Derived from how the model is used on a run (`mtg_engine._read_result_prediction`):

- For each deck with at least 16 games: **predicted** = the `expected_win_rate` the shipped model serves (`engine/predict.py Predictor.predict`, clamped and rounded to 0.1 as the page shows it), fed
  - `survival` = 100 x (games in which the deck's seat has `alive: true` in the result record) / (all result records the deck played), **censored games included**, exactly the served computation and exactly how the fit's survival was computed (verified: the fit's `mu` 30.203 and `sd` 11.497 reproduce from all 766 stock games, censored included, to three decimals);
  - `creatures` and `avg_cmc` from the committed training features `studies/precon_predict/features.json`, so the check isolates the pilot and not card-cache drift (see limitations).
- **human** = the deck's `human` win rate in `cohort.json` (playgroup.gg, 2026-08-03).
- **rho** = Spearman rank correlation of predicted against human across those decks (`studies/precon_predict/model.py spearman`, average ranks for ties).

**PASS iff rho >= 0.40**, with rho rounded to three decimals.

### Why 0.40

Three independent readings of the model's documented figures land on the same number:

1. **The documented out-of-sample figure, less the sampling noise at this n.** The model's leave-one-out rank correlation is **0.477** (fresh 2026-08-26 capture: 0.499). The deck set and the human rates are fixed here, so the only noise in a re-run is the simulation's. Measured by resampling each deck's survival from its own binomial at 48 games per deck: sd **0.034** on the stock arm and **0.043** on the 0.15.0 plan arm. 0.477 - 2 x 0.04 = **0.40**: a pilot below that is outside what the documented model does, beyond sampling noise.
2. **The decklist floor.** The same shipped model with the simulation removed (survival held at its fitted mean) ranks these 66 decks at **0.407**. Below 0.40, feeding this pilot's simulation into the model ranks decks worse than not simulating at all, which is what "the rank correlation broke" means for a product whose case is that you have to play the games.
3. **Error rates at this n**, from the two arms already on disk (read with this study's reader, which reproduces the documented figures: stock decided-game rank correlation 0.255 and 0.15.0 0.140, as in the README):

| Case | Observed rho | Re-run distribution | P(outcome at 0.40) |
|---|---|---|---|
| Stock arm (the model's own pilot) | 0.544 | mean 0.516, sd 0.034 | fail: under 0.1% |
| 0.15.0 plan arm (the closest measured plan pilot: pre-0.16.0 attack re-ask loop, 1,200 s clock, personality overrides) | 0.508 | mean 0.485, sd 0.043 | fail: about 2.5% |
| A pilot whose survival carries no deck information (survival shuffled across decks, 4,000 permutations) | – | mean 0.353, sd 0.068, 95th percentile 0.465 | **pass: about 25%** |

The re-run distributions add binomial noise on top of already-noisy observed survival, so they are pessimistic (they understate a true re-run's mean).

**What this check can and cannot do, stated before the run.** It catches a pilot that breaks the model (false-alarm rate about 2.5% for a pilot like the 0.15.0 arm). It cannot reliably tell a working pilot from one whose simulation adds nothing to the decklist: an uninformative pilot passes about a quarter of the time, because at 66 decks the uninformative null reaches 0.465 at its 95th percentile. A stricter threshold would buy that power with frequent false suppression (at 0.465, a 0.15.0-like pilot fails about a third of the time). That is why the label never comes off: a pass adds "Rank check passed for this pilot" beside "Fit on stock Forge games; this run used Sim Lab's pilot.", it does not replace it. The permutation p-value is reported beside the verdict for that reason.

## Decidable, and what happens

The reading is **decided** only when at least 64 decks have at least 16 games, at least 95% of the 768 games are present (730), and every cell reports the same pilot id. A cell with fewer than 2 results is retried by re-running `run` (same seed, resumable); the reading waits for the run to finish and is never taken early.

- **PASS:** `read_rank_check.py --write-record` appends `{release: "R1", pilot: "plan/0.17.0/v2", pass: true, ...}` to `engine/models/rank_checks.json`; it ships with R1. Production runs on the R1 pilot keep the label and add the check's date and figures.
- **FAIL:** the same command appends the record with `pass: false`. From the deploy that carries it, `/results/{file}/prediction` withholds the figures on every run whose pilot is `plan/0.17.0/v2` and the page says why in plain words. **The prediction stays withheld for this pilot until the model is refit on clean arms after G3** (decision 19). A re-run of this check with new seeds cannot overturn a failed reading; the reader refuses a second R1 record for the same pilot.
- **NOT DECIDED:** no record is written, and production keeps the label with "No rank check has been run for this pilot yet." The run is resumed, not re-designed.

The record's fields: `release, date, pilot, jar_sha, plan_version, metric, value, threshold, pass, n_decks, games, study, prereg_commit`.

## Reported, not gated

Pearson r; MAE and mean bias against the documented LOO MAE 3.95 pp and guess-the-mean 4.25 pp (the page's interval is the LOO MAE, so a large bias means the interval understates the error even when the ranking holds); rho against the 2026-08-26 capture; rho of survival alone; the decklist floor; the permutation p-value; the sim-noise replicate distribution; rho with **live** deck features (the served path, see below); rank correlation of decided-game win rates; survival mean and sd against the fit's 30.2 and 11.5; the timed-out share; game seconds.

## Known limitations, recorded before the run

- **Card-cache drift (train/serve skew), found while writing this.** Recomputing `deck_features` live from the committed card cache today gives different `creatures` or `avg_cmc` for **14 of the 66 decks** than `features.json`, the values the model was fitted on (for example Lorehold Spirit 36 creatures live against 33 at fit). Production computes features live, so served predictions already differ from the fit's inputs. The primary metric holds features at their training values to isolate the pilot; the served-path rho with live features is reported (on the stock arm it is 0.518 against 0.544 with training features). The drift itself is out of this check's scope and is flagged for the refit.
- **Production runs have far fewer games per deck** (8 to 16) than this check or the fit (48), so a production run's survival is much noisier and carries more weight in its prediction than it did at fit. The page's interval (the LOO MAE) does not include that per-run sampling error. This check measures the pilot, not per-run precision.
- **In-sample optimism.** The model was fitted on these 66 decks, so the stock arm reads 0.544 here against 0.477 out of sample. The threshold is anchored on the documented out-of-sample figure, not on the in-sample one.
- **Censoring counts as survival.** A clock-killed game leaves several seats alive, and survival counts them, as the fit did. A pilot that times out more (the 0.15.0 arm: 30.5% against stock's 9.7%) shifts survival up (45.7 against 30.2) and biases every prediction up (+2.2 pp there) without necessarily breaking the ranking; that shows in the reported bias, not in the gate.
- **The plans are built from `deck_plan.py` at the commit the runner runs from.** If version-2 plan building changes before R1 ships in a way that changes plans, this check covers the tested plans only; the plans file's SHA-256 is in every cell record and in the reading.

## Commands

```bash
# after this file is committed; output under $RANK_CHECK_OUT (default: the scratch folder)
py studies/rank_check_r1/run_rank_check.py plans            # 66 version-2 plans, no games
py studies/rank_check_r1/run_rank_check.py smoke            # 1 game, never read
py studies/rank_check_r1/run_rank_check.py run --workers 8  # 384 cells, 768 games; resumable
py studies/rank_check_r1/read_rank_check.py                 # report
py studies/rank_check_r1/read_rank_check.py --write-record  # decided reading -> rank_checks.json
```

Expected wall time at 8 JVMs: 384 cells x (2 games + about 31 s of JVM start, measured on G0a) / 8. With the stock arm's game length at a 900 s cap (392 s mean) that is **about 11 hours**; with the 0.15.0 arm's (554 s mean at the cap) **about 15 hours**. 0.16.0 removed the attack re-ask loop that lengthened the 0.15.0 arm's games, so the R1 pilot is expected between the two. At 12 JVMs (G0a's setting, 36 GB of heap on the 64 GB box) the same run takes about 7 to 10 hours.
