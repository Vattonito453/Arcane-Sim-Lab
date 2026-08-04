# Precon correlation study — plan

**Status: pilot complete 2026-08-04 (512 games). Full run NOT started, and
should not start until two instrument defects are fixed.** Results, gate
outcomes and the recommendation: [`PILOT_RESULTS.md`](PILOT_RESULTS.md).

**Question.** Does the humanized Sim Lab agent predict *human* Commander win
rates better than stock Forge AI does?

This is the predictive-validity claim, and it is a different claim from the
behavioural-resemblance numbers in `engine/SIM_CALIBRATION.md`. Resemblance
says the agent mulligans and splits attacks like a human. Predictive validity
says the resulting win rates track reality. Only the second one justifies
coaching, and the repo has never tested it.

**Pre-registration.** §5 fixes the analysis before any sim runs. Do not change
it after seeing results; if it must change, record the change and the reason
here, dated, and report both analyses.

---

## 1. Ground truth

`ground_truth.json` — Playgroup.gg's precon tier list, captured 2026-08-03:
**66 precons, 10,982 tracked human games** with stock decklists. Integrity
check passes (66 decks, games sum to the claimed 10,982).

Why this dataset: stock precons are a **fixed, known 100 cards**, so the deck
we simulate is the same object the humans played. No other public MTG dataset
has that property at this scale.

### The ground truth is noisier than its presentation suggests

From `design.py`, over all 66 precons:

| | value |
|---|---|
| Observed SD of published win rates | 5.60 pp |
| Mean per-deck sampling SE | 4.10 pp |
| **Implied true signal SD** | **3.81 pp** |
| **Reliability (signal / observed variance)** | **0.463** |

So **roughly half the variance in the published tier list is sampling noise.**
Several tier boundaries are finer than the error bars around individual decks
(Blame Game sits in S-tier on 40 games, SE ≈ 7.6 pp). This is not a criticism
of their method, which documents its own thresholds; it is a hard ceiling on
any correlation we can measure against it. Even a *perfect* predictor caps at
r ≈ 0.68 on the full cohort.

**Handle with care in public.** "Your tier list is ~54% noise" is a true
statement and a hostile way to open a partnership conversation. Frame findings
as a joint measurement limit, and share results with them before publishing.

### Other confounds (recorded in `ground_truth.json`)

- Opponent field is uncontrolled. "Stock" constrains the *tracked* deck only;
  opponents may be upgraded or custom decks, and the field may differ per deck.
- Self-selected tracking population.
- Pod-size normalisation is linear to a 25% baseline, not a strength adjustment.

---

## 2. Decklists: use the ones Forge already ships

Forge bundles **172 Commander precons** as native `.dck` under
`res/quest/commanderprecons/`. `build_manifest.py` resolves **66/66** of the
ground-truth precons to a bundled file (two need aliases: Forge writes
"The Host of Mordor" and "Mind Flayarrrs").

This settles the hardest practical problem for free:

- Nothing is scraped from Playgroup, so we take none of their content.
- Native `.dck`, so no conversion and no parse risk. Verified format on
  `Grand Larceny [OTC] [2024].dck`: `[metadata]` / `[Commander]` / `[Main]` /
  `[Sideboard]`, 1 commander + 99 main, every card set-qualified.
- One canonical printing per precon.

**Not vendored.** CLAUDE.md forbids vendoring Forge, and it is unnecessary: the
sim runs where Forge is installed, so the runner resolves `forge_file` under
`$FORGE_DIR/res/quest/commanderprecons/` at run time. Only `manifest.json`
(our mapping plus the ground-truth join) is committed.

**Residual risk:** a bundled `.dck` proves Forge *has* the cards, not that
every card is fully scripted. Partial implementations would silently distort a
deck's win rate. §6 tests this before the full run.

---

## 3. Simulation design

Per test precon: a **4-player pod** of the test precon plus **three fixed
control opponents**, **seat-rotated** (`SIM_CALIBRATION.md` rule 1;
`rotations = 4`). `run_sim.py --games N --rotate` splits N across 4 rotations
and cycles seat order, so the test deck occupies each seat equally.

- **Controls come from outside the 66**, so no deck plays itself and no control
  is also a measured subject. Settled: the three mono-coloured **Commander
  2014** precons spanning distinct archetypes, all present in Forge's bundle
  and all from one design era with a consistent intended power level:

  | Control | Colour | Archetype |
  |---|---|---|
  | `Built from Scratch [C14] [2014].dck` | R | artifacts / value |
  | `Guided by Nature [C14] [2014].dck` | G | elves / creature aggro |
  | `Sworn to Darkness [C14] [2014].dck` | B | demons / midrange removal |

  Blue's C14 entry (`Peer Through Time`) is deliberately excluded: Forge's AI
  is weakest at control, so including one would inject the engine's known
  worst case into the baseline.

- **A fixed gauntlet is deliberate.** It makes the opponent field the
  controlled variable, which is what a correlation needs. Our win rate is
  therefore "vs these three," not "vs the field" — a difference in level that
  rank correlation tolerates and absolute comparison would not.

- **Identical pods and seat orders across arms**, so the headline comparison is
  **paired** — materially more powerful than comparing two independently
  estimated correlations.

### Arms: use the shim for both, so only the policy varies

`run_sim.py` exposes three pilots, and the naive choice of `--agent forge` for
the control would confound two changes at once (stock AI *and* stdout scraping
instead of the shim's typed `GameLog`). Correct arms:

| Arm | Flag | Pilot | Harness |
|---|---|---|---|
| `shim_stock` | `--agent shim` | stock `PlayerControllerAi` | shim |
| `agent_v3` | `--humanize` | plan agents, agent v3 | shim |
| `forge_cli` | `--agent forge` | stock `PlayerControllerAi` | Forge sim CLI |

`shim_stock` vs `agent_v3` is the experiment: same harness, only the decision
policy differs. `forge_cli` is a pilot-only third arm to confirm the harness
itself does not shift win rates; drop it for the full run if it agrees with
`shim_stock`.

---

## 3a. Blocking finding from the smoke test: timeouts are counted as wins

A 4-game rotated humanized run on the control pod at the **default
`--clock 120`** produced this:

| game | turns | ms | `timedOut` | credited |
|---|---|---|---|---|
| 1 | 77 | 126,007 | **true** | Sworn to Darkness wins |
| 2 | 50 | 120,163 | **true** | Built from Scratch wins |
| 3 | 71 | 60,139 | false | Sworn to Darkness wins |
| 4 | 74 | 54,021 | false | Built from Scratch wins |

Summary reported `4 games | draws: 0`. **Half the games were resolved by the
clock and every one was credited as a legitimate win.**

Mechanism, traced through the code:

1. `run_sim.py` defaults `--clock 120` and passes it as the shim's `--timeout`.
2. `SimShim.runOneGame()` catches `TimeoutException`, sets `timedOut = true`,
   and calls `game.setGameOver(GameEndReason.Draw)`.
3. Forge nonetheless resolves an outcome with a winning lobby player, so the
   emitted record is `draw: false`, `winner: <someone>`, `timedOut: true`.
4. `engine/shim_log_adapter.py` never reads `timedOut`, so it does not reach
   the result JSON, and `_summarize_by_deck` counts these as ordinary wins.

**Consequences for this study.** A timeout winner is close to arbitrary, and
timeout *rate* will differ between arms because the humanized agent plays
longer, more complex games. Left unhandled this confounds the whole comparison.
Required changes to the protocol:

- Raise `--clock` so games finish naturally (value set from the measurement in
  §3b), and
- record timeout rate per run as a reported covariate, and
- **exclude timeout games from win rates** in the analysis, reporting how many
  were dropped per arm.

**Consequences beyond this study.** The VM's measured per-game times average
~110 s against the same 120 s default (`engine/SIM_PERFORMANCE.md`), so a
meaningful share of production games likely hit the cap. That puts the
win-rate lines in `engine/SIM_CALIBRATION.md` (agent v1/v2/v3) in doubt; the
behavioural metrics there are unaffected, since they come from agent telemetry.
It also offers a simpler explanation for that doc's observation that the agent
"compressed the win-rate spread": quasi-arbitrary timeout winners push win
rates toward uniform. Tracked as separate product work, not fixed here.

## 3b. Measured cost on the local Mac

Smoke test, 12-core / 24 GB Mac, humanized arm, 4 games rotated:
**6 min 18 s wall for 4 games including 4 JVM launches ≈ 95 s per game**, at
only ~138% CPU. A Forge game is largely single-threaded, so **parallelism is
the lever, not per-core speed**. With a 4 GB heap per JVM, 24 GB of RAM allows
about 5 concurrent games (fewer if heap stays at the 4 GB default).

**The tail is stalls, not long games.** A `--clock 1200` probe on the same pod:

| turns | seconds | `timedOut` | turns/sec | credited winner |
|---|---|---|---|---|
| 79 | 79.7 | false | 0.99 | Sworn to Darkness |
| 54 | 28.8 | false | 1.88 | Sworn to Darkness |
| **25** | **1200.4** | **true** | **0.02** | **Grand Larceny** |
| 54 | 118.2 | false | 0.46 | Guided by Nature |

Game 3 reached only **25 turns in 20 minutes** while game 1 played 79 turns in
80 seconds.

### Corrected against a 76-game sample

The single probe above suggested a 20-90x gap and a distinct pathological
cluster. A 76-game sample from the interrupted first pilot pass (clock 600)
says something more moderate, and two earlier claims here were overstated:

| | value |
|---|---|
| games | 76 |
| **timed out at 600 s** | **8 (10.5%)** |
| natural completions | 68 |
| median game | 108.9 s |
| mean game | 185.8 s |
| longest **natural** completion | **592 s** |
| natural completions over 300 s | 9 of 68 |
| turns/sec, timed-out games | 0.062 - 0.112 |
| turns/sec, natural games | 0.138 - 1.883 (median 0.675) |
| wall time spent in timed-out games | 61 of 235 min (**26%** of time for 8% of games) |

**Correction 1 — the separation is real but narrow, not 20-90x.** Timed-out
games span 0.062-0.112 turns/sec and natural ones 0.138-1.883, so the two sets
do not overlap on this sample and a threshold near **0.125 turns/sec** separates
them cleanly. But the boundary gap is about 1.2x, not 20x. The 0.02 turns/sec
probe game was the extreme, not the type.

**Correction 2 — "pathological, not grindy" is not established.** Timed-out
games are censored at the clock by construction, so their turns/sec is
mechanically depressed and cannot distinguish "genuinely stuck" from "merely
slow." The 1200 s probe game (25 turns in 1200 s) is clearly pathological; the
600 s population is probably a mix. Excluding them from win rates is correct
either way, because an unfinished game has no winner — but calling all of them
stalls overstates what the data shows.

**Clock decision: 900 s.** Dropping to 300 s looked attractive (timeouts consume
26% of wall time) but **would clip 9 of 68 naturally-completing games**,
including one that finished legitimately at 592 s. And 600 s is too close to
that 592 s observation to trust at scale. A separate session independently
measured 900 s as the right default and changed `run_sim.py` to match
(commit 3c30052), so the study uses 900 s for consistency with the repo.

## 3c. Concurrency hazard: the shim changed underneath the first two passes

Another session fixed this same bug while this study was being built. Timeline:

| when | what |
|---|---|
| 14:31 | pilot pass 1 starts (clock 600, 4 workers) |
| **14:49:48** | **shim jar rebuilt** — commit 77e4ddb, "Force a draw on timeout instead of trusting Forge's outcome object" |
| ~15:45 | pass 1 stopped; pass 2 starts (clock 600, 10 workers) |
| later | repo commit 3c30052 surfaces timeout rate and raises the default clock to 900 s; `shim_log_adapter.py` gains `timedOut` passthrough |

Consequences:

- **Pass 1's 76-game sample straddles the rebuild**, so its games are a mix of
  old-shim (timeout credited a winner) and new-shim (timeout forced to a draw)
  behaviour. The *timing* analysis in §3b is unaffected — turns and milliseconds
  are measured the same either way — but that sample must never be pooled with
  later passes for anything outcome-related. Archived as `pilot_pass1_sample/`.
- **Pass 2 ran entirely post-rebuild** and is internally consistent, but at the
  now-superseded 600 s clock. Archived as `pilot_clock600_partial/`.
- The adapter fix does not change this study's numbers, because `run_study.py`
  deliberately computes win rates from the shim's raw `rec:"result"` records
  rather than the adapter's summary.

**Mitigation now in place.** `run_study.py` copies the shim jar to
`pinned/simlab-forge-shim.jar` on first run, passes it to every worker via
`SIMLAB_SHIM_JAR`, and records `shim_sha256_16` on every result row. Another
session rebuilding the shared jar can no longer change the arms mid-study, and
provenance is checkable per row. CLAUDE.md already warns that concurrent
sessions edit this tree; this is that warning cashing out.

**Any pooled analysis must filter on `clock` and `shim_sha256_16`.**

## 3d. Design concern found in the first cell: the control gauntlet is too weak

The first completed cell (Planeswalker Party, agent arm, clock 600) returned a
**62.1% win rate** against a 25% baseline — clean 29 of 32 games, 3 timeouts
which the fixed shim correctly recorded as draws.

62% is not obviously wrong: Planeswalker Party is a 2023 Commander Masters
precon and the controls are three **2014** precons. Twelve years of power creep
is a large effect, and the human ground truth has this deck as the strongest of
the 66 at 40.87%. But it exposes a design flaw: **if strong modern precons all
win 55-75% against C14 controls, the top of the range saturates** and
discrimination among the better decks is lost to a ceiling effect, which
attenuates the correlation exactly where the signal should be clearest.

The C14 choice optimised for mature Forge card coverage and a consistent design
era, and ignored cross-era power level. Better controls, for the full run:
precons that Playgroup **tracks but has no stock win-rate data for**, so they
are outside the 66 by construction while being contemporary with the cohort.
Candidates present in Forge's bundle: `Riveteers Rampage [NCC] [2022]`,
`Divine Convocation [MOC] [2023]`, `Draconic Dissent [CLB] [2022]`,
`Painbow [DMC] [2022]`, `Tinker Time [MOC] [2023]`.

Decide from the pilot's spread: if the pilot's sim win rates saturate near the
top, switch controls before the full run. The pilot still answers its own
questions either way, since it spans the full 11.96-40.87% ground-truth range.

Three consequences:

1. **A longer clock does not rescue them.** Game 3 was not close to finishing.
   Raising the clock only wastes more wall-clock per stall. The right handling
   is detection and exclusion, which is what `timedOut` already provides — it
   simply must be honoured instead of credited (§3a).
2. **The right clock is generous relative to *normal* games, not to stalls.**
   At 0.5-2 turns/sec a real game finishes well inside 300 s. The pilot uses
   600 s, which is ample; 300 s would halve the cost of each stall. Revisit
   after the pilot reports its stall rate.
3. **Stalls credit an essentially random deck, and the bias is not benign.**
   Game 3 handed the win to Grand Larceny — the *worst* deck in the ground
   truth at 13.20%. That is the concrete mechanism behind the win-rate spread
   compression noted at `SIM_CALIBRATION.md:80`: stall-resolved wins are
   quasi-uniform, so they pull every deck toward the 25% baseline regardless of
   real strength. It is a compression artifact, not evidence about humanization.

**Added analysis (does not disturb the running pilot).** `turns/sec` is a clean
stall detector and catches partial stalls that finish under the clock, which the
`timedOut` flag alone misses. The per-game raw records persist in
`runs/shim_raw_*.jsonl`, so this is derived in a separate analysis pass rather
than by changing `run_study.py` mid-run. Report per arm: timeout rate, stall
rate by turns/sec threshold, and win rates with and without stalls excluded.

**Parallelism is safe via per-worker Forge profiles.** `forge_profile_deck_dir()`
honours `FORGE_USER_DIR`, so giving each worker its own profile removes the
`stage_decks()` race on the otherwise-shared deck dir. `run_study.py --workers N`
does this. Verified: 4 concurrent workers each held ~100% of a core with no
contention.

**Memory headroom is larger than assumed.** With `--heap 3g`, measured RSS per
worker was only **~0.8 GB** (43% of system memory free with 4 workers plus a
stray probe). The 24 GB / heap-size calculation was far too conservative — the
real limit is core count, not RAM. **Raise `--workers` toward 8-10 for the full
run**, which should bring the 42-deck cohort to roughly 15-20 h wall.

---

## 4. Cost model

Measured on the production VM (`engine/SIM_PERFORMANCE.md`, 2026-08-02):
~110 s per game steady-state, ~40 s per JVM launch, 4 launches per rotated pod.

Per precon per arm at G games: `G × 110 s + 4 × 40 s`.

| Cohort | Decks | Games/deck | Hours, one arm | Hours, both |
|---|---|---|---|---|
| All 66 | 66 | 64 | 132 | **264** |
| 2024-and-earlier | 42 | 64 | 84 | **168** |
| All 66 | 66 | 32 | 68 | 135 |
| Feasibility pilot (§6) | 8 | 32 | 8 | **16** |

---

## 5. Pre-registered analysis

**Primary outcome.** Δr = r(agent) − r(stock), where r is the Spearman rank
correlation between simulated and human win rates across the cohort.
Directional hypothesis: Δr > 0.

**Inference.** Paired bootstrap over precons (10,000 resamples), resampling
decks and recomputing both arms' correlations on the same resample. Report the
Δr point estimate with a 95% percentile interval. Δr > 0 with an interval
excluding 0 is the result; anything else is reported as null.

**Secondary outcomes**, all reported whatever they show:

1. Pearson r per arm, weighted by human sample size (`1/SE²`).
2. Spearman r per arm restricted to `human_games >= 150` (32 decks) as a
   robustness check on ground-truth noise.
3. Tier-direction accuracy: fraction of decks each arm places on the correct
   side of the 25% baseline.
4. Calibration slope of sim win rate on human win rate per arm. A slope far
   from 1 means the sim compresses or exaggerates spread even when ranking
   correctly — directly relevant to `SIM_CALIBRATION.md`'s archetype baselines.
5. Attenuation-corrected r per arm, using the reliability figures in §1, stated
   explicitly as a corrected estimate rather than a measurement.

**Power.** With human reliability 0.463, an assumed latent r of 0.70, and 64
sim games per deck, expected observed r ≈ 0.27 on the full cohort against a
p<.05 critical |r| of 0.242 (n=66); ≈ 0.33 against 0.304 on the 42-deck
cohort. These margins are thin, which is why the paired Δr, not the per-arm r,
is the primary outcome.

**Honest failure modes, declared in advance.**

- If both arms correlate near zero, the finding is that *Forge-family AI does
  not predict human precon win rates at all*, and coaching built on sim win
  rates needs re-framing. That result gets published too. It is more valuable
  to know than not.
- If the agent correlates *worse* than stock, humanization improved
  resemblance while degrading predictive validity, and the moat argument in
  `MARKET_SCAN.md` §8 is wrong.

---

## 6. Feasibility pilot — do this first (~16 VM hours)

Eight precons, 32 games, both arms. Purpose is *not* correlation (n is far too
small); it is to de-risk the full run:

1. **Pipeline.** Forge `.dck` → rotated pod → win rate, end to end, both arms.
2. **Card-script coverage.** Include two 2026 precons (e.g. Doom Prevails
   [MSC], Blight Curse [ECC]) and grep the logs for card-script errors,
   unimplemented-ability warnings, and stalled games. This is the risk in §2.
3. **Do the extremes separate at all?** Include the top and bottom of the
   ground truth: Planeswalker Party (40.87%), Tricky Terrain (32.07%),
   Grand Larceny (13.20%), Deadly Disguise (11.96%), Mutant Menace (15.12%).
   If a 29 pp human spread produces no sim spread under either pilot, the full
   study is not worth 168 hours and this cost 16.
4. **Confirm the timing model** against `SIM_PERFORMANCE.md`'s estimates, and
   re-measure rotated-pod overhead on a warm container — an open item in that
   doc anyway.

Gate: proceed to the full run only if (2) is clean and (3) shows any separation.

---

## 7. Open decisions

1. ~~**Compute.**~~ Settled 2026-08-03: **the local Mac** (12 cores, 24 GB,
   Java 17, Forge 2.0.13 installed at `~/forge`, shim jar present at
   `~/Desktop/Personal/simlab-forge-shim/simlab-forge-shim.jar`, which is the
   first path `run_sim.py` searches). Free, ~6x the VM's CPU, no production
   impact.
2. **Per-game clock.** Blocked on the §3b measurement. The 120 s default is
   demonstrably too short.
3. **Cohort scope.** 42 decks (2024 and earlier) or all 66. Decide after the
   pilot's card-coverage check; if the 2026 sets are clean, take all 66 for the
   extra statistical power. All 66 are present in Forge's bundle and verified
   on disk.
4. **Parallel isolation.** Needed before the full run (§3b).

## 7a. Current state

**PILOT COMPLETE 2026-08-04 — 16/16 cells, 512 games. Results and the
recommendation are in [`PILOT_RESULTS.md`](PILOT_RESULTS.md).**

Headline: the pre-registered primary outcome is **null and leans against the
agent** (Δr = −0.063, 95% CI [−1.249, +1.068]). Two instrument defects must be
fixed before any full run: the 900 s clock censors the agent arm 2.6x more than
stock, and the C14 control gauntlet is too weak. Do not launch the full run yet.

The historical notes below were written mid-run and are superseded by
`PILOT_RESULTS.md` where they disagree.

<details>
<summary>Mid-run notes (2026-08-03, superseded)</summary>

**Pilot half complete: 8 of 16 cells durable in `runs/results.jsonl`.**
Parameters: 8 decks x 2 arms, 32 games, `--clock 900`, `--workers 10`,
pinned shim `sha256 7d15e42b16301276`.

Resume with the identical command; completed cells are skipped automatically:

```
python3 studies/precon_correlation/run_study.py --pilot --games 32 --clock 900 --workers 8 --heap 3g
```

Done: stock arm on Planeswalker Party, Tricky Terrain, Explorers of the Deep,
Doom Prevails, Blight Curse; agent arm on Explorers, Doom Prevails, Blight
Curse.

Outstanding: agent arm on Planeswalker Party and Tricky Terrain (the two
highest-value cells, see below), plus both arms on Mutant Menace, Grand
Larceny, Deadly Disguise.

### Findings so far

1. **Card coverage is clean.** 0 stderr flags on every cell, including both
   2026-set decks (Doom Prevails / Marvel, Blight Curse / Lorwyn Eclipsed). The
   full 66-deck cohort stays viable; no need to fall back to the 42-deck
   pre-2025 set.
2. **Timeout rate is arm-dependent and this is a real confound.** Stock 6/96
   (6.2%), agent 17/96 (17.7%) on matched decks and matched n: 11.5 pp
   difference against a 4.6 pp SE, about 2.5 SE. The agent plays longer games
   (mean 349-489 s vs 325-346 s), so it is censored more. Set the full-run clock
   from the **agent arm's** length distribution, targeting under ~2-3% censoring
   in both arms, and report censoring per arm alongside any correlation.
3. **Stock Forge win rates track archetype pilotability, not deck strength**
   (n=5, provisional). Gaps vs human: Planeswalker Party -1.6 pp,
   Tricky Terrain +10.2, Blight Curse +21.5, Explorers +28.1,
   Doom Prevails +32.3. The two big inflators are plain creature decks
   (merfolk tribal, villain creatures); the three that do not inflate need
   long-horizon or nonstandard play (planeswalkers, Omo lands/counters,
   curses). Stock Spearman is **-0.36 at n=5** — not interpretable at that n,
   but the direction is a warning, driven by range compression (sim spread
   14 pp vs human 22.4 pp) plus inversion at the top.
4. **Control gauntlet is too weak in level.** Everything except Planeswalker
   Party sims well above the 25% baseline. Offset alone is harmless for a
   rank-based outcome; combined with finding 3 it is not. See §3d for the
   contemporary-control replacement candidates.

5. **The agent arm compresses win rates MORE than stock, and on the four
   paired decks it is slightly worse calibrated.** This is the first evidence
   bearing directly on the moat thesis and it does not support it.

   | precon | human | stock (gap) | agent (gap) | agent |
   |---|---|---|---|---|
   | Planeswalker Party | 40.87% | 39.3% (-1.6) | 52.2% (+11.3) | worse |
   | Explorers of the Deep | 25.25% | 53.3% (+28.1) | 52.0% (+26.8) | ~same |
   | Doom Prevails | 21.06% | 53.3% (+32.3) | 42.9% (+21.8) | better |
   | Blight Curse | 18.49% | 40.0% (+21.5) | 50.0% (+31.5) | worse |

   Mean absolute gap: **stock 20.9 pp, agent 22.9 pp.** Sim spread across decks:
   **stock 14.0 pp (39.3-53.3), agent 9.3 pp (42.9-52.2)** against a human
   spread of 22.4 pp.

   Planeswalker Party is the important one. It is the archetype stock Forge
   pilots worst, so it was the best test of whether humanization helps where it
   should help most — and the agent moved it from nearly perfectly calibrated
   (-1.6 pp) to +11.3 pp inflated.

   **Alternative hypothesis this raises, and it is a serious one for the
   product:** humanization may make games *more even* — more blocking, more
   interaction, fewer blowouts — which compresses win rates toward the 25%
   baseline and therefore *reduces* discriminating power. A deck-analysis tool
   needs the opposite. If that holds up, "more human-like" and "more useful for
   ranking decks" are in tension, and `MARKET_SCAN.md` §8's argument that the
   agent is the moat needs rewriting rather than defending. It would also mean
   the win-rate compression in `SIM_CALIBRATION.md:80` is partly real and
   partly the timeout artifact, not purely either.

   **Do not over-read this yet.** Four paired decks, and the Planeswalker Party
   agent cell has the worst data quality in the study: **9 of 32 games timed
   out (28.1%)**, so its 52.2% rests on 23 clean games and the censoring
   confound (finding 2) is at its most severe on precisely the cell that
   matters most. Arm-level censoring is now stock 16/160 (10.0%) vs agent
   26/128 (20.3%). Resolving the clock is a precondition for trusting this
   comparison at all.

### Corrections from the 464-game sample (supersede §3b)

§3b was written from 76 games at `--clock 600`. With 464 games at `--clock 900`
two of its conclusions do not survive. `analyze.py` reproduces all of this.

**Correction A - the turns/sec stall detector does not work.** §3b claimed clean
separation with a threshold near 0.125 turns/sec. At larger n the sets overlap
heavily:

| | natural completions | censored |
|---|---|---|
| stock | min 0.041, median 0.260 | max 0.119 |
| agent | min 0.045, median 0.243 | max 0.087 |

Natural games run as slow as 0.041 turns/sec, well below the *fastest* censored
game. There is no threshold that separates them. The apparent separation at
n=76 was an artifact of the shorter clock. **Any plan to detect stalls by
turns/sec should be dropped**, including the suggestion in the spawned
re-measurement task, which pre-dates this data.

**Correction B - 900 s is marginal, not generous, and censoring is mostly real
long games rather than stalls.** Natural completions reach p95 717-745 s,
p99 837-839 s, and max 890 s against a 900 s clock. Games are finishing right up
against the wall, so a meaningful share of censored games would have completed
legitimately given more time.

That reframes the censoring problem and makes it worse. Excluding censored games
is not "excluding invalid games" — it is **excluding a biased subset, namely the
long ones** — and the agent produces more long games, so it loses more real
data. Measured: stock 20/250 censored (8.0%), agent 45/214 (21.0%).

**Recommended full-run clock: 1260 s** (agent p99 x 1.5). Set from the agent
arm because it has the longer games; this is what makes censoring comparable
across arms. This raises full-run cost and that is the correct trade.

### Interesting signal: the agent makes its bias more archetype-uniform

Post-hoc, small n (stock 7 decks, agent 4), so a hint and not a finding — but
it is the most promising thing in the pilot and it is not the comparison I had
been making.

| arm | creature decks | non-creature | difference |
|---|---|---|---|
| shim_stock | +30.2 pp | +12.2 pp | **17.9 pp** |
| agent_v3 | +24.3 pp | +21.4 pp | **2.9 pp** |

The agent does **not** reduce the overall level bias (still +21 to +24 pp) and
its mean absolute gap is slightly worse than stock (22.8 vs 20.9 pp). What it
appears to do is make the bias far more *uniform across archetypes*, collapsing
the creature/non-creature spread from 17.9 pp to 2.9 pp.

That distinction matters more than the headline gap: **a uniform offset can be
calibrated away, an archetype-dependent one cannot.** If this holds on the full
cohort it is a better argument for the agent than "its win rates are closer to
human," because it is what makes a correction layer possible at all. It also
reframes what to measure: archetype-uniformity of residuals, not raw proximity.

Calibration slopes are far below 1 in both arms (stock 0.357, agent 0.223), so
both compress heavily and the agent compresses more.

### Post-hoc analysis added after seeing the pilot (NOT pre-registered)

Recorded here as post-hoc, dated 2026-08-03, and kept out of §5's
pre-registered set so it cannot be mistaken for a prediction:

- **Archetype-residual analysis.** Tag each precon by archetype and test
  whether the sim-minus-human residual is systematically archetype-driven.
  If it is, the study yields *measured* per-archetype correction factors,
  which could replace the hand-tuned archetype baselines in
  `SIM_CALIBRATION.md` with empirical ones. This may be more valuable to the
  product than the headline correlation, and it is a stronger reason to run
  the full cohort even if raw correlation is poor.
- **Range-compression / calibration-slope check** at the cohort level, for the
  same reason.

### Next actions, in order

1. Finish the 8 outstanding pilot cells (resume command above).
2. Decide controls from the completed pilot spread (§3d rule).
3. Set the full-run clock from the agent arm's game-length distribution.
4. Write per-rotation results instead of per-cell. Cells are 32 games and
   nothing is durable until a whole cell finishes, which cost hours across two
   interruptions today and makes the tail pack badly.
5. Use `--workers 6-8`, not 10. Measured: 4 workers gave 1.27 games/min and 10
   gave 1.59 — 2.5x the workers for 1.25x the throughput, because the 12 cores
   are not homogeneous.

</details>

## 8. Files

| File | Role |
|---|---|
| `ground_truth.json` | Playgroup's 66 precons, win rates, sample sizes, confounds |
| `design.py` | Power analysis, cohort selection, cost model |
| `build_manifest.py` | Resolves precons to Forge's bundled `.dck` files |
| `manifest.json` | Generated join: precon → forge_file + ground truth |
| `.forge_precon_listing.json` | Cached Forge bundle listing (172 files) |
