# Engine strength head-to-head — plan and pre-registration

**Status: BOTH RUNS COMPLETE 2026-08-06, 1536 games. The primary outcome is null
in both mirror and heterogeneous pods; combined A - B = -0.08 pp, 95% CI
[-3.99, +3.84].** Results: [`RESULTS.md`](RESULTS.md).

**Question.** Does the Sim Lab engine play Magic *better* than stock Forge AI?

Not "does it predict human win rates better" — that is a different question, it
is what `studies/precon_correlation/` asked, and its pilot answered it null
(Δr = −0.063, 95% CI [−1.249, +1.068]).

---

## 1. Why the thesis changed, recorded as §5 of the old plan requires

`studies/precon_correlation/STUDY_PLAN.md` §5 pre-registers its analysis and
requires that any change be recorded, dated, with the reason. This document is
that record. The old pre-registration is **not** edited; it stands as written
and its result stands as reported.

**Dated 2026-08-05.** The primary question becomes relative playing strength.
The correlation study and its two known instrument defects (weak C14 controls,
asymmetric censoring) become secondary work. Reasons:

1. **Proximity to human win rates cannot measure strength.** It is not on the
   same scale (Playgroup's rate is "vs the human field", ours is "vs a fixed
   gauntlet" — §3 of the old plan concedes this, which is why it used rank
   correlation), and more importantly it **is not monotone in skill**. A pilot
   that played *better* than the humans who logged the ground truth would win
   more than they did and therefore score *worse* on proximity. Human win rates
   benchmark human skill; they do not ceiling good play.
2. **The old design structurally cannot answer the strength question.**
   `run_study.py` arms are `--agent shim` and `--humanize`, and `--humanize` is
   pod-global, so both arms are **self-play**: agent deck vs three agent
   controls, or stock deck vs three stock controls. The four seats' win rates
   sum to 100% in both arms by construction. The two pilots never met. No
   reanalysis of the pilot's 512 games can rank them.
3. **A head-to-head dissolves both instrument defects.** Deck strength cancels
   in a mirror, so control strength stops mattering and the contemporary-control
   replacement is unnecessary. And both arms sit in the *same game*, so a
   timeout removes an observation from every arm at once: the pilot's 2.6x
   arm-asymmetric censoring (stock 7.8%, agent 19.9%) becomes structurally
   impossible.
4. It costs hours instead of the 168-264 the full cohort needed, and it does not
   depend on Playgroup's data quality at all — the ground truth is only 46%
   reliable and caps even a perfect predictor at r ≈ 0.68.

**What censoring the mirror does NOT fix**, stated plainly because it is the
main threat to this design: it removes differential *sample size*, not
length-*selection*. Timeouts are the long games. If an arm's edge lives in long
games, the surviving sample under-represents it and the effect attenuates toward
the null. §4 is how that is handled.

---

## 2. Design: the full 2x2 in one mirror pod

Four seats, all playing **the same decklist**, one seat per arm:

| Arm | Controller | AI profile | What it is |
|---|---|---|---|
| **A** | `PlanPlayerController` | `SimLabHuman` | what ships today |
| **B** | stock `PlayerControllerAi` | `Default` | stock Forge |
| **C** | stock `PlayerControllerAi` | `SimLabHuman` | floodgate without the gate |
| **D** | `PlanPlayerController` | `Default` | our policy without the floodgate |

**Why the profile is a factor and not a nuisance.** `SimLabHuman.ai` is written
by the shim itself (`SimShim.writeHumanProfile`) as `Default.ai` with exactly
four fields changed:

```
CHANCE_TO_COUNTER_CMC_1=100
CHANCE_TO_COUNTER_CMC_2=100
CHANCE_TO_COUNTER_CMC_3=100
MIN_SPELL_CMC_TO_COUNTER=0
```

It makes the AI counter everything it can, and the shim's own comment states
the design: the profile makes the stock AI eager with counterspells and
`PlanPlayerController`'s threat veto then decides which actually fire. Profile
and controller are a **designed pair with an intended interaction**, so a 3-cell
design cannot estimate it and arm identity is the pair, never the controller
alone. Arm C is deliberately included as the degenerate cell (floodgate, no
gate); it is expected to play *badly*, and that expectation is itself the check
that the floodgate is what makes it bad.

**Why a mirror.** Identical decks means deck strength cancels exactly, so any
deviation from the null is piloting. It also means the weak-control problem and
the cohort-scope question simply do not arise.

**Seat rotation is mandatory, and it rotates arms, not decks.** Forge's seat
bias is measured at **seat 1 ~11%, seat 4 ~36%** (`run_sim.py:308`) — a 25pp
spread against a 25% null, far larger than any plausible skill effect. Because
the mirror's decks are identical, the thing that must move across seats is the
**arm assignment**: the `--seat-pilots` spec rotates while deck paths stay
fixed. Four rotations put each arm in each seat exactly once, so seat bias
cancels by balance. Games per deck are therefore a multiple of 4.

**Cohort.** The same 8 precons as the correlation pilot, so archetype tags and
the pilot's context carry over. In a mirror the deck does not set difficulty, so
these are here for **archetype coverage** — to test whether any strength edge is
archetype-uniform, which was the pilot's one promising signal and is the thing a
correction layer would depend on.

8 decks x 96 games = **768 games**, 24 games per arm-rotation per deck.

---

## 3. Pre-registered analysis

**Primary outcome.** Win share of arm **A** minus win share of arm **B**, over
all decks pooled, against a null of 0. Directional hypothesis: **A − B > 0**
(the engine we ship beats stock Forge).

**Inference.** Games are the resampling unit. Paired bootstrap over games
(10,000 resamples), recomputing both arms' shares on each resample; report the
point estimate with a 95% percentile interval. Censored games are excluded from
win share and handled per §4.

**Power.** With one seat per arm and a 25% null, the per-game contribution to
the A−B difference is +1/−1/0 with variance 0.5, so the SE of the difference in
win rates is `sqrt(0.5/n)`. At n=768 that is **2.55 pp**, detecting about a 5 pp
difference at p<.05 two-sided. Per-deck (n=96) the SE is 7.2 pp, so **per-deck
and archetype figures are exploratory, not powered.**

**Secondary outcomes**, all reported whatever they show:

1. **A − D**: does the SimLabHuman profile earn its keep inside the engine that
   ships? This is the profile's contribution where it actually operates.
2. **B − C**: what the floodgate does to an ungated stock AI. Expected negative;
   if it is *not*, the stated design rationale is wrong.
3. **Interaction**: (A − D) − (C − B). Whether the profile's effect depends on
   the controller gating it, which the shim's comment asserts by design.
4. **A − B per deck and by archetype tag**, exploratory, to see whether any edge
   is archetype-uniform or archetype-dependent. A uniform offset can be
   calibrated away; an archetype-dependent one cannot.
5. **Win-rate spread across decks per arm.** If an arm genuinely plays better we
   would expect the spread across decks to *widen*, since a stronger pilot
   extracts more from a stronger deck. The correlation pilot measured the
   opposite (calibration slope 0.167 for the agent vs 0.472 for stock). This
   run is a clean check on whether that compression was real weakness or the
   censoring artifact.

**Honest failure modes, declared in advance.**

- **If A − B is null**, the humanized engine does not play Magic better than
  stock Forge, and `MARKET_SCAN.md` §8's moat argument needs rewriting rather
  than defending. That gets reported.
- **If A − B is negative**, humanization actively costs playing strength.
- **If A beats B but A ≈ D**, the win comes from four lines of counterspell
  config and not from our decision policy. That is a materially weaker claim
  about the engine and must be reported as such.
- **If A beats B but the archetype spread is wide**, the edge is not a general
  strength gain.

**Not a claim this design can make.** A win here is a win *against stock Forge's
`PlayerControllerAi`*. It could be general Magic skill or it could be an exploit
specific to that one opponent. The mirror cannot tell those apart, which is what
§5 is for.

---

## 4. Censoring, and why the clock alone is not enough

Measured here 2026-08-05, 8 all-stock mirror games at `--clock 1260`
(`pinned/timing_probe.jsonl`):

| | value |
|---|---|
| median | 315.1 s |
| mean | 362.9 s |
| min / max | 26.2 s / 1260.3 s |
| **censored at 1260 s** | **1 of 8** |

n=8, so the rate is barely pinned (roughly 0.3-53%), but it is clearly not
negligible — and this is the all-stock mix, which should be the *fastest*
configuration. Plan agents lengthen games.

**The worst-case bound alone cannot rescue a modest effect.** At 768 games with
~12% censored: if A leads B by 5 pp on clean games that is about 25 wins on
676 clean games; reassigning all 92 censored games adversarially to B swamps it
outright. So all three mitigations are needed and only the third recovers
information:

1. **Clock 1260 s.** From the correlation pilot's recommendation (agent p99 x
   1.5). Reduces the censored share; does not eliminate it.
2. **Worst-case sensitivity bound.** Reported for every pairwise comparison:
   assign every censored game to the arm that disfavours the hypothesis and
   recompute. A result that survives this is censoring-proof. **A result that
   does not survive it is reported as not censoring-proof**, not quietly
   presented on clean games alone.
3. **Survival at the clock, as a separate paired outcome.** Each result record
   now carries per-seat life and alive status (shim `--seat-pilots` build,
   below), so a censored game yields data instead of nothing. In a mirror the
   pod is symmetric, so "still standing when the clock ran out" is a legitimate
   outcome with the same 25% null. **Survival is never folded into a win rate.
   Surviving is not winning.** Reported separately, alongside mean life at
   termination per arm.

---

## 5. What the Playgroup ground truth is still for

Demoted from primary outcome, not discarded. `ground_truth.json` and
`manifest.json` stay in `studies/precon_correlation/`.

- **Exploit detection.** Stock Forge is our only baseline, so the human deck
  rankings are the only external reference that can distinguish real Magic skill
  from an exploit tuned to `PlayerControllerAi`. If arm A wins the mirror *and*
  tracks human deck rankings at least as well as stock, that is evidence of
  general skill.
- **A validated difficulty ladder.** Human win rates say which precons are
  genuinely weak, independent of our sim. Giving each arm a weak deck against
  strong ones measures how much deck disadvantage each pilot can overcome, which
  is a strength measure that uses the ground truth for what it is good for.

Neither is in this run's pre-registered set.

---

## 6. Instrument, and what was verified before launching

**Pinned shim `sha256 c50a9cc2c51d4634`** at `pinned/simlab-forge-shim.jar`,
passed to every worker via `SIMLAB_SHIM_JAR` and recorded on every result row.
Built from the shim repo with two changes, both adapter/logging plumbing rather
than strategy logic, so the GPL boundary in CLAUDE.md is unaffected:

- **`--seat-pilots`**: positional per-seat pilot and profile, one entry per
  `--decks` entry. Necessary because plans are keyed by deck *name*
  (`plans.get(d.getName())`), so a mirror pod resolves to the same lookup for
  every seat and **cannot express a mixed pod at all**. Also the only way to put
  a profile on a stock seat, i.e. to have arms C and D exist. A seat declared
  `plan` with no matching plan exits 3 rather than silently seating stock AI,
  which is the failure that corrupted four cells of the correlation pilot.
- **Per-seat survival on the result record**: `seats: [{name, life, alive}]`,
  each entry carrying its own name rather than relying on positional alignment
  with `meta.players`, because `getRegisteredPlayers()` order is Forge's to
  decide and a silent reordering would mislabel every arm.
- `meta.profiles` joins `meta.agents`, since arm identity is the pair.

Verified 2026-08-05 before any wall time was spent:

| check | result |
|---|---|
| Forge plays a 4-copy mirror pod | **PASS** — same commander in four seats, 56 turns, natural completion |
| 2x2 seats correctly assigned | **PASS** — `agents ['plan','stock','stock','plan']`, `profiles ['SimLabHuman','Default','SimLabHuman','Default']` |
| `humanized` correct on a mixed pod | **PASS** — false, since not every seat is a plan agent |
| survival on a censored game | **PASS** — 4 seats with life and alive on a timed-out game |
| survival on a natural completion | **PASS** — 3 eliminated, winner alive at 8 life |
| adapter carries it through | **PASS** — `meta.profiles` and `result.seats` reach the result JSON |
| repo adapter tests | **PASS** — `test_adapter.py` ALL ASSERTIONS PASSED |

**Provenance note.** The correlation pilot recorded shim
`7d15e42b16301276`; the shared jar before this change was `3548f87ca5cb99f6`
(commit 81a44c9, built 2026-08-04). The shared jar had already been rebuilt
after the pilot, so **pilot data was never poolable with anything built since**,
independent of this study. Filter on `shim_sha256_16` as
`precon_correlation/STUDY_PLAN.md` §3c requires.

---

## 7. Files

| File | Role |
|---|---|
| `PLAN.md` | This document: thesis change record and pre-registration |
| `run_h2h.py` | Mirror-pod runner: stages 4 copies, rotates arms across seats, resumable |
| `analyze_h2h.py` | Win shares, paired bootstrap, worst-case bound, survival outcome |
| `pinned/simlab-forge-shim.jar` | Pinned shim, `c50a9cc2c51d4634` |
| `pinned/timing_probe.jsonl` | The 8-game timing probe behind §4 |
| `runs/` | Per-cell results and raw shim JSONL (gitignored, regenerable) |
