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
- Wins this sample: Drana 50%, Wyleth 25%, Kilo 25%, Wilhelt 0% (n=8 — for
  behavior measurement, not win-rate conclusions). Archetype baselines above
  remain STOCK-AI baselines until re-measured under the agent at scale.

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
2 fires, 5 optional-trigger misses, 32 splits. Wins 38/38/12/12
(UrD/Meren/Kilo/Atraxa) vs the pre-agent run's 67/17/17/0 — n=8, direction
only.

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
