# Simulator Calibration — Known Biases and How to Read Win Rates

Findings from ~500 simulated 4-player Commander games (July 2026). Any product
built on this engine MUST apply these corrections before showing users a number.

## Bias 1: Seat position (FIXED — always use --rotate)

Fixed deck order gives seat 1 an 11% win rate and seat 4 a 36% win rate
(148-game measurement) — Forge's attack AI defaults toward the first-listed
opponent. `run_sim.py --rotate` cycles every deck through every seat and merges
by deck name. Never report unrotated 4-player results.

## Bias 2: Archetype (UNFIXABLE at AI level — report against class baselines)

Seat-fair measurement across 320+ deck-games:

| Deck class | Avg win rate | Examples |
|---|---|---|
| Creature-forward (swarm, dragons, voltron, stompy) | **38%** | Ur-Dragon 44-62%, Wilhelt 19-44%, Drana 31-67% |
| Engine/spell (artifacts, counters/proliferate, burn, draw-go) | **12%** | every Inspirit build 0-25%, Torbran burn 6%, Talrand 12-38% |

The AI converts battlefield creatures into wins and cannot execute multi-turn
engine plans, hold protection for wipe turns, or sequence setup->payoff kills.

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
- Win-rate spread compressed under the agent (38/25/25/12 vs stock
  38/38/12/12 on 8-game samples — n too small for conclusions, direction
  plausible: interaction punishes runaway starts).
- Familiarity level is full-decklist (every seat knows every plan's threat
  signature). Blind/archetype-aware dials are not implemented yet.

**Default change (2026-08-01):** humanized is now the DEFAULT agent.
`run_sim.py` resolves `--agent auto` to plan agents whenever the shim jar is
available and falls back to stock Forge with a stderr warning and
`meta.humanized: false` otherwise. Opt-outs: `--agent forge` (CLI),
`MTG_SIM_HUMANIZE=0` (worker env). Every result now carries
`meta.humanized` on all paths, including stock and rotated runs.
