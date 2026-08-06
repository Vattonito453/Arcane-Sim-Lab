# Engine strength head-to-head — results

Two runs, 1536 games. **Both null.** Jump to
[the heterogeneous-pod follow-up](#heterogeneous-pods--results-2026-08-06) and
[the combined estimate](#combined-across-both-designs) for the bottom line.

---

# Part 1 — mirror pods, 2026-08-06

8 precons x 768 games in 4-player **mirror** pods, one seat per arm, seat-rotated
as a balanced Latin square, `--clock 1260`, pinned shim
`sha256 c50a9cc2c51d4634`. 96/96 cells, 0 failures, 0 arm mismatches, 7.95 h wall
at 1.61 games/min on 16 workers. Reproduce with:

```
python3 studies/skill_headtohead/analyze_h2h.py
```

Design and pre-registration: [`PLAN.md`](PLAN.md). Read §3 (what this design can
and cannot claim) and §4 (censoring) before quoting anything here.

---

## Headline: null, on every comparison

**A − B = +2.52 pp** (win share, ships-today minus stock Forge), paired
bootstrap 95% CI **[−3.12, +8.05]**, P(Δ>0) = 0.801 over 10,000 resamples.

The pre-registered directional hypothesis was A − B > 0 — that the engine we
ship plays Magic better than stock Forge. **It is not supported.** All four arms
land within 2.7 pp of each other and of the 25% null:

| arm | | wins | share |
|---|---|---|---|
| A | plan + SimLabHuman (ships today) | 153 | 25.67% |
| B | stock + Default (stock Forge) | 138 | 23.15% |
| C | stock + SimLabHuman (floodgate, no gate) | 154 | 25.84% |
| D | plan + Default (our policy, no floodgate) | 151 | 25.34% |

596 decided games gives SE 2.90 pp, so the 95% interval is about ±5.7 pp. **This
rules out a large effect and cannot resolve a small one.** The honest statement
is: our engine plays Magic about as well as stock Forge, not detectably better
and not detectably worse.

This is the second direct test of `MARKET_SCAN.md` §8's claim that the humanized
agent is the product's competitive moat. The correlation pilot found it does not
buy predictive validity; this finds it does not buy playing strength either.
Neither result is fatal to the product, but §8 needs rewriting rather than
defending.

## The secondaries are more useful than the headline

**A − D = +0.34 pp**, CI [−5.42, +6.09]. **The SimLabHuman profile contributes
nothing measurable inside the engine that ships.** It is four lines of
counterspell config (`CHANCE_TO_COUNTER_CMC_{1,2,3}=100`,
`MIN_SPELL_CMC_TO_COUNTER=0`) that the shim writes on every planned run and that
`PlanPlayerController`'s threat veto exists to gate. On this evidence the pair
does no work. That is actionable: it is dead weight in the system and removing
it would simplify the agent with no measured cost.

**B − C = −2.68 pp**, CI [−8.32, +2.91]. The *ungated* floodgate slightly
outperformed stock Default. Null, but the sign is **opposite** to the design
rationale, which treats the maxed counterspell chances as something that needs
the plan controller's veto to be safe. If anything, ungated eagerness was
harmless here.

**Interaction (A−D) − (C−B) = −2.35 pp.** Null, and again the sign is opposite
to the interaction the shim's own comment asserts by design. Three measurements
now point the same way: the profile/controller pairing is not doing what its
design comment says it does.

## Survival: the early signal did not survive

At 10 cells on one deck, arm A was alive in 13/13 censored games against C's
8/13, which looked like "our engine is durable but not lethal." **It was noise.**
Across all 8 decks:

| arm | alive at the clock | mean life |
|---|---|---|
| A | 160/168 (95.2%) | 28.5 |
| B | 158/168 (94.0%) | 28.8 |
| D | 159/168 (94.6%) | 28.8 |
| C | 151/168 (89.9%) | 24.9 |

Flat, like everything else. C is marginally worst on both survival and life,
which is the one place the floodgate-without-gate prediction holds up, and it is
within noise.

The survival instrument still earned its place: it is what turned 168 otherwise
information-free games into a reported outcome, and it is what showed the
one-deck signal was noise rather than leaving it as an open question.

## One deck does not terminate

**Tricky Terrain censored 94 of 96 games (97.9%)**, median 1270 s at a median of
**48 turns** — 0.038 turns/sec, slower than the slowest *natural* completion in
the correlation pilot. This is a genuine stall, not a long game: a 4-way mirror
of a lands-and-counters deck reaches a state that does not resolve.

| precon | censored | median s | median turns |
|---|---|---|---|
| Doom Prevails | 0.0% | 146 | 44 |
| Mutant Menace | 2.1% | 214 | 38 |
| Explorers of the Deep | 6.2% | 189 | 37 |
| Deadly Disguise | 11.5% | 388 | 53 |
| Blight Curse | 16.7% | 249 | 44 |
| Grand Larceny | 19.8% | 734 | 60 |
| Planeswalker Party | 20.8% | 575 | 64 |
| **Tricky Terrain** | **97.9%** | **1270** | **48** |

**Post-hoc sensitivity (labelled as such; the pre-registered analysis pools all
8 decks).** Dropping Tricky Terrain moves the primary from +2.52 pp to
**+2.53 pp** and censoring from 21.9% to **11.0%**. The conclusion is unchanged,
because that deck contributed only 2 decided games either way. Reproduce with
`--exclude-deck "Tricky Terrain"`.

## Censoring: honest status

168 of 768 games censored (21.9% pooled, 11.0% excluding Tricky Terrain). The
worst-case bound — assign every censored game against the observed direction —
gives −20.03 pp pooled and −8.83 pp excluding Tricky Terrain. **The result is
NOT censoring-proof.**

That matters less than it would have. The bound cannot decide a 2.5 pp effect at
11% censoring, but the confidence interval already spans zero on its own, so
censoring is not what is limiting this conclusion. A follow-up would need a
longer clock to tighten it, and on this evidence there is no effect there to
find.

## What this design cannot claim

Stated in `PLAN.md` §3 before the run and worth repeating:

- A result here is relative to **stock Forge's `PlayerControllerAi`
  specifically**. The mirror cannot distinguish general Magic skill from an
  exploit tuned to one opponent. That is what the Playgroup ground truth is
  still for (`PLAN.md` §5), and it is untouched by this null.
- **A mirror is a symmetric, unusual matchup.** Four copies of one deck is not
  how Commander is played, and an agent could plausibly be better at piloting
  *diverse* pods in ways a mirror cannot show. This is the most substantive
  limitation of the design, and it is the natural next experiment: the same 2x2
  in heterogeneous pods, with deck-to-arm assignment rotated so deck strength
  still cancels.
- Effects smaller than about 6 pp are below this run's resolution.

## Instrument notes

- **Seat bias is mild in a mirror.** Decided wins by seat: 22.0 / 23.7 / 28.4 /
  26.0%, against the 11% / 36% documented for heterogeneous pods
  (`run_sim.py:308`). Rotation balanced it regardless, and the analyzer confirms
  each arm sat in each seat an equal number of games.
- **Game length in the 2x2 pod is much longer than all-stock**: natural games
  mean 517 s versus the 363 s measured on the all-stock probe, which is why the
  run took 7.95 h against a 6 h estimate. Plan agents lengthen games, as the
  correlation pilot found.
- 16-way concurrency ran clean for 8 hours with zero failures on 32 cores /
  63 GB.

## What follows from this

1. **Rewrite `MARKET_SCAN.md` §8.** Two independent tests now say the humanized
   agent is not the moat: it does not predict human outcomes better, and it does
   not play better. The durable asset is the measurement apparatus and the
   corpus, which is where §8 already says it lives.
2. **Consider deleting the SimLabHuman profile.** A−D is +0.34 pp. It is
   unmeasurable, and the code carries a `writeHumanProfile()` side effect on
   every planned run to install it.
3. **The engine is not worse.** Humanization was hypothesized to trade playing
   strength for realism; it does not appear to. The behavioural-resemblance
   numbers in `SIM_CALIBRATION.md` stand, and they now come at no measured cost
   in strength. That is a weaker claim than the moat argument but it is true and
   defensible.
4. **The next experiment is heterogeneous pods**, which is the limitation above
   and the configuration the product actually runs. **Done: Part 2.**

---

# Heterogeneous pods — results, 2026-08-06

The limitation Part 1 could not address: a mirror is a symmetric matchup, and an
agent could plausibly be better at piloting *diverse* pods. Same 2x2 arms, but
pods of four **different** decks, 2 groups of 4, 768 games, same pinned shim
`c50a9cc2c51d4634`, `--clock 1260`. 96/96 cells, 0 failures, 0 arm mismatches,
7.5 h wall at 1.70 games/min. Reproduce with:

```
python3 studies/skill_headtohead/analyze_h2h.py --results studies/skill_headtohead/runs_hetero/results.jsonl
```

The mirror cancelled deck strength for free. Here it is cancelled by a
**Graeco-Latin square of order 4** over GF(4) (`run_hetero.py`), balancing deck,
arm and seat simultaneously. Both balance checks pass on the recorded rows:
every arm sat in every seat an equal number of games, and **every (deck, arm)
pair was played an equal number of games**. Without the second one the pooled
comparison would be confounded by deck strength, and deck strength here is
enormous: win shares range from Grand Larceny at 8.8-20.0% to Doom Prevails at
34.1-47.6%.

## Null again, with the sign flipped

**A − B = −2.43 pp**, 95% CI **[−7.89, +3.05]**, P(Δ>0) = 0.185.

| arm | | wins | share |
|---|---|---|---|
| A | plan + SimLabHuman (ships today) | 160 | 24.32% |
| B | stock + Default (stock Forge) | 176 | 26.75% |
| C | stock + SimLabHuman | 171 | 25.99% |
| D | plan + Default | 151 | 22.95% |

The mirror gave +2.52 pp and this gives −2.43 pp. The two designs **bracket
zero**, which is what no effect looks like.

## Combined across both designs

Fixed-effect, inverse-variance weighted. **Post-hoc: not pre-registered**, and
reported here because two null runs of opposite sign are more informative pooled
than separately.

| design | A − B | SE | decided games |
|---|---|---|---|
| mirror | +2.52 pp | 2.90 pp | 596 |
| heterogeneous | −2.43 pp | 2.76 pp | 658 |
| **combined** | **−0.08 pp** | **2.00 pp** | **1254** |

**95% CI [−3.99, +3.84] pp over 1536 games.** Pooling is defensible: the two
designs differ by 4.95 pp against a 4.00 pp SE, i.e. 1.24 SE, so there is no
significant heterogeneity to pool across.

**This is now a well-powered null.** Our engine plays Magic within about ±4 pp of
stock Forge, in both symmetric and diverse pods. Not better. Also not worse.

## Secondaries agree with Part 1

- **A − D = +1.37 pp** [−3.82, +6.60]. The SimLabHuman profile again contributes
  nothing measurable inside the engine that ships (+0.34 pp in the mirror). Two
  independent runs now say those four counterspell config lines are dead weight.
- **B − C = +0.76 pp** [−4.89, +6.33]. The ungated floodgate is again
  indistinguishable from stock Default.
- **Interaction = +2.13 pp** (mirror: −2.35 pp). Sign flips between designs, so
  there is no interaction to speak of.

## No archetype dependence

A − B by the deck each arm piloted (~90 decided games per cell, SE of a
difference ≈ 6.6 pp, so read the spread not the cells):

| deck | A − B | | deck | A − B |
|---|---|---|---|---|
| Blight Curse | +6.2 | | Grand Larceny | −3.4 |
| Tricky Terrain | −1.7 | | Explorers of the Deep | −4.0 |
| Planeswalker Party | −2.4 | | Deadly Disguise | −4.6 |
| Doom Prevails | −2.9 | | Mutant Menace | −8.0 |

A beats B on 1 of 8 decks. Spread 14.2 pp against a per-cell difference SE of
6.6 pp, and the arm *ordering* is not consistent across decks (C is best on Doom
Prevails, B on Explorers, D on Grand Larceny). This is what noise looks like, and
it closes the archetype-uniformity hypothesis the correlation pilot raised: there
is no arm effect to be uniform or non-uniform about.

## The one signal that appears in both runs

Survival at the clock, ordered **A > D > B > C in both designs**:

| arm | mirror alive | hetero alive |
|---|---|---|
| A | 95.2% | 89.1% |
| D | 94.6% | 85.5% |
| B | 94.0% | 84.5% |
| C | 89.9% | 82.7% |

The two plan-controller arms are the top two, and the ungated floodgate is last,
in both. Every individual gap is within noise (A − B is +1.2 pp and +4.6 pp), so
this is a hint and not a finding. But it is the only ordering that reproduced,
and it is consistent with the plan controller playing more defensively without
converting that into wins. If anything is worth chasing, it is this.

## Two instrument findings

**Tricky Terrain's stall was a mirror pathology, not a deck property.** As a
4-way mirror it censored 94/96 games. As one copy in a pod of four it is
unremarkable: group 1 (which contains it) censored 14.6% against group 0's 14.1%,
and its own win share is a normal 17.1-21.2%. Four copies of a lands-and-counters
deck cannot resolve; one copy plays fine.

**Diverse pods resolve much better than mirrors.** Censoring 14.3% vs 21.9%, and
natural games average 383 s vs 517 s. The worst-case bound still does not survive
(±12 pp at 14.3% censoring against a 2.4 pp effect), but with the CI spanning
zero in both designs censoring is not what limits either conclusion.

**Forge's documented seat bias does not reproduce.** `run_sim.py:308` records
"seat 1 wins ~11%, seat 4 ~36%", a 25 pp spread. Measured here with decks and
arms balanced across seats: **26.4 / 24.8 / 24.2 / 24.6%**, a 2.2 pp spread over
658 decided games. The mirror run showed 6.4 pp. Rotation remains cheap
insurance and should stay, but that documented figure is either wrong or specific
to a configuration neither of these runs used, and it should be re-measured
before anyone relies on it again.

## What follows

Part 1's conclusions stand and strengthen. Specifically:

1. **`MARKET_SCAN.md` §8 needs rewriting.** Three independent tests now: the
   humanized agent does not predict human outcomes better, does not play better
   in mirrors, and does not play better in diverse pods.
2. **Delete the SimLabHuman profile**, or justify it on something other than
   strength. A − D is +0.34 pp and +1.37 pp across two designs.
3. **The engine is not worse.** Humanization buys behavioural realism at no
   measured cost in strength. That is a real and defensible claim, and it is the
   one the product should make.
4. **The remaining open question is the exploit check** (`PLAN.md` §5): all of
   this is measured against stock Forge's `PlayerControllerAi`, and only the
   Playgroup ground truth can say whether that generalizes.
