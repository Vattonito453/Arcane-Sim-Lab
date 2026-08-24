# Simulator Calibration — Known Biases and How to Read Win Rates

Findings from ~500 simulated 4-player Commander games (July 2026). Any product
built on this engine MUST apply these corrections before showing users a number.

## Reading the win rates in this document

**Every win rate below is tagged PRE-FIX or POST-FIX. Never mix them.**

- **PRE-FIX** = measured at the old `--clock 120` default, before shim commit
  77e4ddb forced a draw on timeout. At that clock a clock-expired game was still
  credited to a winner, so an unknown share of these wins were awarded by the
  stopwatch rather than won. Measured on the v1/v2/v3 pods, **15.1% (stock) and
  13.0% (agent) of games run past 120 s on a quiet 12-core Mac**, and far more on
  slower hardware. Treat PRE-FIX win rates as unusable, not merely noisy.
- **POST-FIX** = `--clock 900`, shim 7d15e42b16301276 or later, timeout games
  excluded from the denominator rather than credited.

**Behavioural metrics are unaffected by all of this.** Mulligan rate, split
rate, block rate, counter vetoes and the Stage 4/5 counters come from agent
telemetry, not from game outcomes, and neither the clock nor the timeout bug
touches them. They need no pre/post tag.

## Bias 1: Seat position (FIXED — always use --rotate)

Fixed deck order gives seat 1 an 11% win rate and seat 4 a 36% win rate
(148-game measurement) — Forge's attack AI defaults toward the first-listed
opponent. `run_sim.py --rotate` cycles every deck through every seat and merges
by deck name. Never report unrotated 4-player results.

**Wired into production as of 2026-08-02** (was previously CLI-only, so every
sim launched through `POST /simulate` — worker → `Engine.simulate()` →
`run_sim.py` — ran fixed-seat despite this doc's rule; see the `_rotated`
suffix on the result filename as the tell). `Engine.simulate()` now passes
`--rotate` by default; `MTG_SIM_ROTATE=0` is a debug-only escape hatch for a
faster single-seat run. Any `sim_*.json` without the `_rotated` suffix (or
without `meta.source == "rotated"`) predates this fix and should not be read
as a verdict on the deck.

## Bias 2: Archetype (UNFIXABLE at AI level — report against class baselines)

Seat-fair measurement across 320+ deck-games:

| Deck class | Avg win rate | Examples |
|---|---|---|
| Creature-forward (swarm, dragons, voltron, stompy) | **38%** | Ur-Dragon 44-62%, Wilhelt 19-44%, Drana 31-67% |
| Engine/spell (artifacts, counters/proliferate, burn, draw-go) | **12%** | every Inspirit build 0-25%, Torbran burn 6%, Talrand 12-38% |

The AI converts battlefield creatures into wins and cannot execute multi-turn
engine plans, hold protection for wipe turns, or sequence setup->payoff kills.

**These baselines are PRE-FIX as well as stock-AI-only.** They were measured at
the 120 s clock, so an unknown share of the games behind them were decided by
the stopwatch. They still describe the right *shape* (creature decks convert,
engine decks do not) because the effect is large and the Inspirit case study
below is corroborated by telemetry rather than by win rate alone. But the
specific 38% / 12% figures are due a POST-FIX re-measurement before they are
shown to a user as a threshold.

**Controlled proof (the Inspirit case study):** four progressively fixed Inspirit
builds plus the EDHREC 10,818-deck consensus list all scored 6-25% seat-fair,
while full telemetry showed the final build's engine fully operational
(charge events 0.7 -> 6.9/game, proliferate 7.1/game, all finishers live).
A functioning engine deck and the global community's consensus build score
identically to a broken one: the simulator, not the decks, is the ceiling.

## How to report simulation results honestly

1. Always seat-rotate.
2. Compare a deck's win rate to its ARCHETYPE baseline (38% creature / 12% engine),
   not to 25%. "18% for an engine deck" is above class average.
3. Pair the win rate with FUNCTION telemetry (`deck_telemetry.py`): commander
   cast timing, engine trigger rates, finisher activity, death causes. A deck
   whose machinery runs but loses to the archetype bias is probably fine in
   human hands; a deck whose machinery never fires is actually broken.
4. Voltron/politics/protection-trick decks: sim results are a floor, sometimes
   a badly misleading one (Siona: 10% sim, competent human pilot in the source
   video). Label them as such.
5. The most human-predictive opponents in the pool are the real decklists
   (dnide_wildsear / nanman_felix / n3cro_raggadragga): the sim's winner
   distribution on that pod matched the actual human game outcome.

## Sim Lab agent v1 (humanized shim, measured 2026-07-31)

`run_sim.py --humanize` runs plan agents (simlab-forge-shim + deck_plan.py)
instead of stock Forge AI. Results carry `meta.humanized: true` — NEVER mix
them with stock numbers unlabeled; the archetype baselines above are
stock-AI baselines and need re-measuring under the agent before use.

A/B, same 4-deck pod (kilo/drana/wilhelt/wyleth), 8 games each, seat-rotated
(`humanness_scorecard.py`; agent telemetry is authoritative for agent
actions — Forge's GameLog writes combat lines before the agent's
adjustments, so raw log text under-reports them):

| metric                    | stock AI | agent v1 | human reference |
|---------------------------|----------|----------|-----------------|
| mulligan rate (decisions) | ~3-6%    | 14.3%    | ~15-25%         |
| attack-split rate (turns) | 0.0%     | 23.3%    | "constantly"    |
| block rate                | 8.1%     | 22.7%    | routine blocks  |
| counterspells             | CMC dice | 9 vetoed / 1 fired (threat-gated) | held for threats |

Notes:
- keep-7 rate from log text (93.8% both) is misleading for the agent: the
  free Commander mulligan redraws to 7, so a mulled hand still logs "kept a
  hand of 7". Use agent `mull_take`/`mull_keep` events for the true rate.
- ~~Win-rate spread compressed under the agent (38/25/25/12 vs stock
  38/38/12/12 on 8-game samples — n too small for conclusions, direction
  plausible: interaction punishes runaway starts).~~ **RETRACTED 2026-08-04.**
  PRE-FIX, and n=8 could not have supported it even without the timeout bug:
  four *identical* decks over 8 games produce a spread SD of 14.1 pp on average,
  which is larger than the entire claimed effect (stock 13.0 pp vs agent
  9.2 pp). Re-measured POST-FIX the direction reverses. See "Win-rate spread
  re-measured" below.
- Familiarity level is full-decklist (every seat knows every plan's threat
  signature). Blind/archetype-aware dials are not implemented yet.

**Default change (2026-08-01):** humanized is now the DEFAULT agent.
`run_sim.py` resolves `--agent auto` to plan agents whenever the shim jar is
available and falls back to stock Forge with a stderr warning and
`meta.humanized: false` otherwise. Opt-outs: `--agent forge` (CLI),
`MTG_SIM_HUMANIZE=0` (worker env). Every result now carries
`meta.humanized` on all paths, including stock and rotated runs.

## Sim Lab agent v2 (Stage 4 politics, measured 2026-08-01)

Adds grudge memory, kingmaker avoidance, politics-gated countermagic, and an
optional-trigger miss chance. All dials are per-seat data in the deck plan
(`grudgeWeight`, `kingmakerRatio`, `politics`, `triggerMiss`); mechanisms
live in the shim. Same 4-deck pod, 8 games, seat-rotated. Agent telemetry
(shim JSONL events) is authoritative for agent actions, as with v1.

| metric                       | agent v1 | agent v2 | human reference |
|------------------------------|----------|----------|-----------------|
| mulligan rate (decisions)    | 14.3%    | 15.8% (6/38)          | ~15-25% |
| attack-split rate (turns)    | 23.3%    | 35.7% (56 splits)     | "constantly" |
| block rate (raw log text)    | —        | 14.7% + 6 agent-added | routine blocks |
| counterspells                | 9 vetoed / 1 fired | 19 vetoed / 2 fired, bar raised to 6.0 by politics; both fires hit threat-signature spells | held for the win attempt |
| kingmaker re-aims            | n/a      | 6 across 32 seats — attacks moved off the weakest seat onto the leader | avoid kingmaking |
| optional triggers missed     | n/a      | 5 (all optional; `isOptionalTrigger()` guard means a mandatory trigger can never be skipped) | humans miss triggers |

Notes:
- Politics gate observed working end-to-end: chaff vetoed at threat 1-4
  (Swiftfoot Boots, Read the Bones), fires only on threat-signature spells
  (Endless Ranks of the Dead, Baneful Omen) at the raised bar.
- Hidden-zone hygiene re-confirmed for the new paths: grudge accumulates
  from public combat declarations, table threat reads battlefield + life,
  the open-mana check counts untapped lands on the battlefield. No hand or
  library reads anywhere in the controller.
- Wins this sample: Drana 50%, Wyleth 25%, Kilo 25%, Wilhelt 0%. **PRE-FIX,
  n=8: do not read this line at all.** It sits inside the noise band for four
  identical decks. The behavioural rows in the table above are unaffected.
  Archetype baselines above remain STOCK-AI baselines until re-measured under
  the agent at scale.

## Sim Lab agent v3 (Stage 5 combo pursuit, measured 2026-08-01)

The agent now pursues its own win condition — the last human behavior from
`training/ai_vs_human_analysis.md` no prior stage attempted. Knowledge
crosses the boundary as plan JSON (`lines`, `tutors`, personality `greed`);
mechanisms live in the shim. The **line-of-sight gate** is the design rule:
pursuit activates only when every piece of a known line is on the agent's
battlefield or in its own hand, or exactly one piece short with a tutor in
hand. It acts only on an empty stack and never touches attack/block paths —
combat and interaction stay exactly as Stages 2-4 tuned them.

Mechanism validation (synthetic 2-piece line, Scourge of Valkas + Rite of
Replication, vs Torbran):
- `combo_cast` sequencing: Scourge deployed, Rite cast the same turn to
  complete the line; the seat won. One-shot (instant/sorcery) pieces are
  only ever cast when they complete the line.
- `tutor_cast` + `tutor_steer`: one piece short, the agent cast Diabolic
  Tutor — which stock AI draws and NEVER casts (measured) — and the search
  took Rite over stock's pick (Dragonlord Atarka).
- `combo_hold` line discipline: stock AI burns Rite as an early value play
  with Scourge still in hand (measured twice in 4 games); the veto keeps
  the piece for the line. No priority stalls from the deferral.

Combo pod, 8 seat-rotated games (atraxa/urdragon/meren/kilo_helm_final),
behavior vs training-data human reference:

| metric | stock Forge | agent v3 (this run) | human reference |
|---|---|---|---|
| mulligan rate (agent events) | ~3% | 23.7% (9/38) | 15-25% |
| attack-split rate (turns)    | 0%  | 22.7%        | "constantly" |
| block rate                   | 14% | 23.2%        | routine blocks |
| commander deploy (median game-turn) | 30+ for synergy decks | 19 (≈ player-turn 5) | player-turn 4-5 |
| pursues own win condition    | never | gated: 1 `combo_cast` in the run's single sighted moment; 88 searches, none mis-steered | every human winner |

Stage 4 behaviors intact this run: 11 kingmaker re-aims, 6 counter vetoes /
2 fires, 5 optional-trigger misses, 32 splits. ~~Wins 38/38/12/12
(UrD/Meren/Kilo/Atraxa) vs the pre-agent run's 67/17/17/0 — n=8, direction
only.~~ **PRE-FIX and RETRACTED 2026-08-04**: this pod re-measured POST-FIX at
n=64 gives UrD 58 / Meren 33 / Atraxa 5 / Kilo 5 under the agent and
UrD 48 / Meren 20 / Atraxa 19 / Kilo 12 under stock, which is spread
*expansion*, the opposite of what this line was cited for. The behavioural
counters in this paragraph stand.

Honesty notes:
- This pod cannot showcase pursuit: Atraxa's five known lines are all
  4-card packages and the deck runs ZERO nonland tutors (draw odds predict
  ~0 assemblies in 8 games — the wincon table now says `sample_too_small`
  instead of implying a deck problem). Ur-Dragon's line is 2 cards but also
  tutorless. The gate held: no tutor was ever burned on a combo hunt
  without line of sight, per the design rule.
- Rite-style completion still relies on stock targeting after the cast:
  the shim sequences and deploys but does not (yet) steer the copy target
  onto the dragon. Assembled-but-not-converted remains the expected reading
  for such lines.
- Hidden-zone hygiene (Stage 5 paths): reads own battlefield / own hand /
  own command zone plus the search option list Forge reveals to the
  searching player. Opponents' hands and libraries stay unread.

**Re-verified 2026-08-02 before publishing the shim.** The run above could
not exercise the tutor path on a real deck (both combo decks in that pod are
tutorless), so the claim rested on synthetic decks. Re-run on a
tutor-carrying pod (krenko/atraxa/kilo_helm_final/drana), 8 seat-rotated
games, with plans generated by `deck_plan.py` from the real decklists:

- `tutor_cast` fired twice on a real deck — **Goblin Recruiter cast seeking
  Skirk Prospector**. Stock Forge AI never casts tutors at all, so this is
  the behavior the stage exists to add.
- `combo_cast` once (Skirk Prospector, line 0/3 online — early development,
  which is the designed sequencing for permanent pieces).
- `search_seen` 69 — the hit-rate denominator; no search was mis-steered
  without line of sight.
- Stages 1-4 all still active alongside pursuit: 50 splits, 14 added blocks,
  9 kingmaker re-aims, 14 counter vetoes, 10 optional-trigger misses,
  mulligan rate 9/40. 8 games, 0 draws, no stalls or illegal actions.

Pursuit remains **rare by design** — 3 pursuit actions in 8 games — because
the line-of-sight gate only opens when a line is nearly complete. ~~Wins this
run were Kilo 50 / Drana 38 / Atraxa 12 / Krenko 0 (n=8, direction only)~~
**PRE-FIX, retracted 2026-08-04**; POST-FIX at n=64 this pod gives
Drana 38 / Atraxa 36 / Kilo 16 / Krenko 11 under the agent, so Kilo was not
the strongest seat and Krenko was not at zero. Pursuit did not rescue Krenko,
and nothing here says it should.

## Win-rate spread re-measured (POST-FIX, 2026-08-04)

The claim under test: "the agent compressed the win-rate spread," cited in this
doc's v1 section and in `MARKET_SCAN.md` §8 as evidence that humanization
changed *outcomes* and not just behaviour.

**It does not survive. The measured direction is expansion, not compression.**

Method: the three pods this doc quotes, re-run at `--clock 900` with the pinned
post-fix shim (7d15e42b16301276), 64 seat-rotated games per arm per pod, 384
games total. Both arms run through the shim (`--agent shim` vs `--humanize`) so
the harness is held constant and only the decision policy varies; the original
A/B used Forge's CLI for its stock arm, which changed pilot and harness at once.
Timeout games are excluded from the denominator. Tools:
`studies/agent_spread/run_pods.py` and `spread_analysis.py`.

| pod | stock spread SD | agent spread SD | delta |
|---|---|---|---|
| krenko / atraxa / kilo / drana | 14.8% | 11.8% | **-2.9 pp** |
| atraxa / urdragon / meren / kilo | 13.8% | 22.2% | **+8.3 pp** |
| kilo / drana / wilhelt / wyleth | 4.4% | 10.1% | **+5.7 pp** |
| **pooled** | | | **+3.7 pp** (95% CI -0.9 to +7.5) |

Compression would require a negative delta. Two of three pods expand, the pooled
estimate expands, and P(agent spread < stock spread) = 0.064. The one pod that
does compress has a CI spanning zero on its own.

Corroborating, on different decks: five precon pods (test precon vs three fixed
C14 controls, post-fix shim, clock 600) give deltas of +13.2, +4.7, -1.5, -16.4
and -2.4 pp, mean ≈ 0, four of five CIs spanning zero.

### Why the original claim was never measurable

Independent of the timeout bug: **at n=8 with four decks, the spread SD of four
identical decks averages 14.1 pp** (95th pct 23.4 pp). Scoring this doc's own
PRE-FIX tuples against that null:

| figure | spread SD | vs. chance at n=8 |
|---|---|---|
| v1 stock 38/38/12/12 | 13.0 pp | below the chance mean |
| v1 agent 38/25/25/12 | 9.2 pp | below the chance mean |
| v2 agent 50/25/25/0 | 17.7 pp | inside the chance band |
| v3 stock 67/17/17/0 | 25.1 pp | marginally above |
| v3 agent 38/38/12/12 | 13.0 pp | below the chance mean |
| v3 re-verify 50/38/12/0 | 19.9 pp | inside the chance band |

The headline comparison (13.0 vs 9.2) is two numbers that are both *below* what
four identical decks produce. The annotation "n=8, direction only" was too
generous: at this sample size there is no direction to read. **Rule going
forward: quote the null spread next to any spread claim.** `spread_analysis.py
--null-only --decks D --games G` prints it.

### Timeout rate per arm

At `--clock 900` on a quiet box (6 concurrent sims, 12 cores): **0 timeouts in
all six cells, both arms.** There is no timeout asymmetry to correct for on
these pods once the clock is right and the machine is not oversubscribed.

The agent is mildly more expensive per game turn: median 0.960 turns/sec vs
stock's 1.019 (**1.06x**), median game 52.7 s vs 45.7 s. That gap is small
enough to be irrelevant at a 900 s clock.

**It is not irrelevant under load, and the clock is wall-clock.** Same decks,
same 600 s clock, differing only in how many sims shared the box:

| concurrent sims | timeouts (Planeswalker Party, stock) | median game |
|---|---|---|
| 4 | 0 / 27 | 89 s |
| 10 | 8 / 17 | 306 s |

At 10 workers the agent arm's timeout rate exceeded stock's in all five precon
pods (47 vs 16%, 26 vs 9%, 29 vs 12%, 53 vs 47%, 65 vs 33%), because a modest
per-turn cost difference becomes decisive once absolute game times inflate ~5x
and everything crowds the clock. **Consequence: never compare arms across runs
made at different concurrency, and keep sim concurrency well under core count.**
An oversubscribed box does not just run slower, it silently changes which games
count.

### What this does and does not overturn

- **Overturned:** every PRE-FIX win-rate line in this document, and the
  spread-compression claim specifically.
- **Untouched:** all behavioural metrics (splits, blocks, mulligans, counter
  vetoes, tutor casts, kingmaker re-aims, trigger misses). These are agent
  telemetry, not outcomes.
- **Still open:** whether the agent predicts *human* win rates better than stock
  does. That is the predictive-validity question, it is a different claim from
  both resemblance and spread, and `studies/precon_correlation/` exists to
  answer it.
