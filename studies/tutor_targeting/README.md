# Tutor targeting — task 20 Stage 0 measurement

Does stock Forge AI pick the same search target a plan-weight ranking of the
same legal options would pick? Measured per `tasks/20-plan-driven-tutor-
targeting.md` Stage 0; the verdict and its interpretation live in that file.

## Contents

- `analyze_stage0.py` — parses `search_seen` events (shim >= 0.4.1) out of
  raw shim JSONL and reports plan coverage, agreement, and every
  disagreement for eyeballing.
- `runs/` — the 2026-08-25 measurement run: 8 seat-rotated humanized games
  on the Magda pilot pod from `studies/human_ceiling` (video n7WpsqsZtdQ),
  clock 900, serial, shim 0.4.1 (`stage0-search-seen-measurement` branch).
  Raw JSONL per rotation, the generated plans file, the merged result, and
  the run log.

## Headline numbers (2026-08-25)

**Stage 0 (`runs/`, keep-weight ranking, cold-cache plans):** 176
searches; 68.8% offered a plan-weighted option; agreement 5.0% (6/121).
The eyeball check showed the plan picks were WORSE than stock's: keep
weights are enabler-quality, so the ranking fetched mana rocks late and
would have overridden stock's Portal to Phyrexia (the human-verified
correct Magda fetch) with Relic of Legends four times. Verdict: Stage 2
blocked on Stage 1 plan data.

**Stage 1 re-measurement (`runs_stage1/`, target ranking, shim 0.4.2,
warm-cache plans with combo lines):** 87 searches; 66.7% coverage;
agreement 29.3% (17/58). The disagreements flipped: the plan now prefers
Spellbook-verified line pieces over stock's big-toughness fetches, and no
disagreement proposes a mana rock. Side effect of warm plans: 0 timeouts
(2 before) and games of 20-215 s, because combo pursuit finally has lines
to pursue. Verdict: the Stage 2 gate is met. Full reading in
`tasks/20-plan-driven-tutor-targeting.md`.

## Outcome comparison: does any of this move game results yet? (2026-08-25)

`compare_arms.py` scores arms on the human-ceiling behavioral metrics (win
round, win method, win-line behavior), because three prior studies showed
raw win rate is a weak discriminator. Arms: `runs_stage1/` (agent v3 +
Stage 1 plans) vs `runs_stock/` (pure stock AI), both shim 0.4.2, same pod,
8 seat-rotated games each, clock 900, serial.

| | agent + Stage 1 plans | stock | human target |
|---|---|---|---|
| win rounds | 6-17, mean 11.8 | 8-14, mean 11.5 | 5 and ~6 |
| methods | combat 8/8 | combat 7/8, spell 1 (Knuckles the Echidna) | Portal toolbox |
| winners | magda 3, selvala 2, rog 2, tymna 1 | magda 5, selvala 3 | magda |
| timeouts | 0 | 0 | n/a |
| Portal to Phyrexia fetched | 2 arrivals from library (1 game) | 8 arrivals from library (5 games), rounds 4-13 | the win line |

Reading, stated plainly:

- **Outcome level: parity.** At n=8 per arm the agent is not faster and not
  more human in method. Expected: Stage 2 has not shipped, so nothing acts
  on the target ranking yet. Decision-level improvement (the ranked picks,
  21 tutor steers, a round-5 library Portal fetch matching the human
  timing) is real but does not convert.
- **This comparison falsified a study claim.** Stock Forge DOES fetch
  Portal, early and repeatedly; the human_ceiling "never fetched" claim
  contradicted its own zone records and is corrected there. What stock
  (and the agent) never do is CONVERT the fetched card into the win: every
  Portal game still ended in combat rounds later.
- **Implication for task 20:** Stage 2 remains justified by the
  decision-level measurement, but temper outcome expectations on this pod;
  the binding constraint on win round is conversion (human_ceiling
  priority 2, win-speed calibration), not target selection.

## Stage 2: the mechanism acts (2026-08-25, shim 0.5.0)

`runs_stage2/` is the acceptance run: same pod, 8 seat-rotated humanized
games, plus two 2-game probes (`probeA.jsonl` steering on,
`probeB_inert.jsonl` with `search` stripped from the plans).
`analyze_stage2.py` checks steer legality, combo priority, declines, and
inertness, and reports UNPROVEN rather than passing a check the run never
exercised.

**The mechanism is correct.** 90 searches, 38 steers (23 plan, 15 combo),
38/38 legal, 9 genuinely contested searches where combo could have lost
priority and lost none, 0 steers over a stock decline, 0 unparsed or
unpairable events. Inert arm: 0 plan steers, all 32 searches `mode=weights`,
and combo pursuit still firing 3 steers, so the addition is dark by
construction rather than by a flag.

**The outcome moved the wrong way, and the cause is legible.**

| arm | win rounds | mean | methods | combo_hold |
|---|---|---|---|---|
| stock 0.4.2 | 8-14 | 11.5 | combat 7, spell 1 | n/a |
| agent 0.4.2 (Stage 1) | 6-17 | 11.8 | combat 8 | 4 |
| agent 0.5.0 (Stage 2) | 8-23 | 14.2 | combat 6, **spell 2** | **47** |

Non-combat wins went up (2 of 8, the most of any arm), which is the
human-like direction. But mean win round rose by 2.4 rounds, away from the
human target of 5-6. Every one of the 47 holds is the same event: the greed
dial seeing an opponent with two or more untapped lands and waiting on the
last piece.

The causal story fits the numbers rather than excusing them. Stage 2 made
assembly work, so the agent now reaches "one piece from winning" far more
often than it did at 4 holds per 8 games; each arrival meets a greed check
that waits about half the time and re-rolls every turn. Better fetching
exposed a conversion bottleneck that was previously too rare to see. That is
the same wall the human ceiling study named as priority 2 (win-speed
calibration), reached from a different direction.

Caveats, stated rather than buried: n=8 per arm, so 11.8 vs 14.2 is a signal
and not a verdict. `greed` is plan data (personality), not shim mechanism, so
the next experiment is a greed sweep on our side of the boundary, with no
Java change. Magda's Portal to Phyrexia never arrived in this arm, consistent
with the ranking preferring value-8 line pieces over a value-6 bomb, which
Stage 1 already flagged as its honest residue.

## Reproduce

```bash
python3 engine/run_sim.py \
  --decks magda.dck rog_ishai.dck tymna_thrasios.dck selvala_archetype.dck \
  --deck-dir studies/human_ceiling/decks/n7WpsqsZtdQ/dck \
  --games 8 --rotate --humanize --clock 900 \
  --out studies/tutor_targeting/runs
python3 studies/tutor_targeting/analyze_stage0.py \
  studies/tutor_targeting/runs/shim_raw_*.jsonl
```
