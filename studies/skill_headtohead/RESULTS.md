# Engine strength head-to-head — results, 2026-08-06

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
   and the configuration the product actually runs.
