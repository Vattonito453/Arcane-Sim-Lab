# Engine A/B: the "new engine" architecture against the 0.15.0 agent

**Verdict (2026-09-09): parity head-to-head, worse against stock, blocks
less. Do not turn it on.** Both dials ship off (`combatSolver`,
`priorityGates` = 0 in `deck_plan.py`), the code stays in shim 0.16.0 as an
opt-in arm, and the one dial worth tuning before any retest is `lifeValue`.

## What was asked, and what was built

An outside architecture note (Gemini, shared 2026-09-09) proposed rebuilding
Forge's AI in five phases: (1) decouple `SpellAbilityAi.canPlay` from target
binding, (2) combat as a branch-and-bound assignment problem scored by Static
Exchange Evaluation with Foundations-rule damage assignment and race-clock
(beatdown/control) weights, (3) an event-driven stack and priority engine
with a threat matrix and three gating rules (end step, red zone,
response-gated protection), (4) bitboards, a Zobrist transposition cache and
an embedded ONNX value net, (5) a 10,000-game tournament benchmark.

Phases 1 and 4 modify Forge internals. This repo's legal posture puts all
decision policy on our side of the process boundary and forbids patching or
forking Forge (CLAUDE.md, "Legal posture"), and the CPU profile in
`engine/SIM_PERFORMANCE.md` puts the shim's combat code at 0.0% of game
time, so bitboards and a cache would not have bought speed here either. They
were not built. Phases 2 and 3 are decision policy, which is what the shim
exists for; they were built in `simlab-forge-shim` 0.16.0 as `SeeCombat`
(solver) and the priority gates in `PlanPlayerController`, off unless a plan
asks. Forge stays the rules engine throughout: legality from `CombatUtil`,
lethal thresholds from `ComputerUtilCombat`, every chosen assignment
validated by Forge and reverted to Forge's own on rejection, and Forge's own
assignment always scored as a candidate so the solver never applies a set it
rates worse. Details, records and the two defects fixed on the smoke runs
are in the shim README, "Combat solver and priority gates, 0.16.0".

Phase 5 is this study, sized to the box rather than to 10,000 games.

## Design

`run_ab.py`. Mixed pods, both pilots plan agents on the same jar: two NEW
seats (dials 1.0) and two BASE seats (dials 0.0, which is exactly the
0.15.0 agent) in every game, so the comparison is paired within a game. Pod
0 is the four bundled decks the 0.15.0 acceptance was measured on; pods 1 to
15 are seeded precon pods from the prediction cohort (the
`behavior_rubric/run_arms.py` shuffle). Four rotations per pod: each deck
sits in every seat once and is NEW twice and BASE twice. 2 games per
rotation, 128 games. 1200 s clock, 120-turn cap. The first cut of the
harness flipped the NEW parity on odd rotations, which the seat rotation
exactly cancels, so every deck sat on one side four times; rotations 2 and 3
were regenerated with the corrected assignment (`ab_run.log`,
`ab_run_flip.log`).

Two more arms on the same jar: `studies/agent_viability/run_pilot.py --arm
engine016` (one NEW plan seat against three stock seats on the two cEDH
pods, 128 games, the design the 0.15.0 default arm ran on 2026-09-07) and
`run_ab.py --mode allnew` (the bundled pod with all four seats NEW, 16 games
seat-rotated, for `studies/precon_predict/divergence.py` against the 0.15.0
humanized pod and the stock control from the same day).

## A defect found on the way, in every earlier agent version

The first A/B run (archived as `runs_prefix_reask_bug/`) leaned NEW, 43 of
73 decided, but 41% of its games died to the clock. In one of them Forge
asked one seat to declare attackers 3,970 times in a single turn. Forge's
PhaseHandler re-asks while a declaration fails its attack requirements;
`kingmakerReaim` moved an attacker onto a player it was not permitted to
attack, Forge rejected the set, the stock AI declared again, the re-aim
fired again, until the clock. The signature (more than one re-aim record
per turn) appears on BASE seats here and in 23 turns of the 0.15.0 cohort
arm's first round, so part of the 30 to 34% censoring every agent arm has
carried since August was this loop, not deliberation. Fixed in 0.16.0 for
both pilots (validate and revert, one adjusted answer per turn), which is
why the clean runs below censor at 17 to 20%. Censoring rates measured
before and after are not comparable.

## Results

**Head-to-head, paired within game** (`runs/`, balanced sides):

| | NEW | BASE |
|---|---|---|
| wins, 103 decided of 128 played | 55 | 48 |
| share | **53.4%** +/- 4.9 pp | |
| 95% CI | 43.8% to 63.0% | null 50% |
| per-deck paired (64 decks, each on both sides) | better with NEW 20 | better with BASE 19 (25 ties) |

Sign test two-sided p = 1.0. Parity. The bundled pod went 3 of 8 to NEW.

**Against stock, cEDH pods** (`agent_viability/runs_016_engine/`):

| arm | plan-seat win share | decided | 95% CI |
|---|---|---|---|
| 0.15.0 default (2026-09-07) | 29.6% | 115 | 21.2 to 37.9 |
| 0.16.0 engine016 | **22.1%** | 113 | 14.5 to 29.8 |

Null 25%. Two-proportion z 1.28, p 0.20: not significant at this size, but
the new engine wins fewer of its games against stock on the combo-live pods
than the agent it replaces, and every read during the run pointed the same
way. 15 of 128 games censored (12%), against 13 for the 0.15.0 arm.

**Behaviour, bundled pod, 16 games each** (`runs_allnew/`, `divergence.py`):

| | stock | 0.15.0 humanized | 0.16.0 all-NEW |
|---|---|---|---|
| instants cast on an opponent's turn | 20.0% | 41.1% | 42.7% |
| all spells cast off-turn | 2.8% | 5.7% | 5.7% |
| attackers blocked | 9.1% | 11.6% | **7.3%** |
| median game seconds | 58 | 92 | 109 |
| games killed by the clock | 0 | 0 | 0 |

The gates moved 20 answers to the opponent's end step and 4 into the red
zone, and held 13 under the threat floor, but they change WHEN in the
opponent's turn an answer fires, not WHETHER it fires off-turn, so the
off-turn share is flat against 0.15.0. The largest own-turn leak is the same
one 0.15.0 has: `pastCutoff`, the round-10 release (57 of 143 NEW windows in
the A/B).

## Why it did not win

- **The solver blocks less than stock.** At `lifeValue` 0.6 a 2/2 is worth
  about five omega units and three damage costs under two, so the search
  declines most blocks as bad trades, and with more bodies at home it also
  attacks less (in the A/B it called off 284 of 911 stock attacks entirely
  and removed 557 attackers while adding 368). Humans block far more than
  stock Forge; that gap is the divergence the whole prediction programme is
  built around, and this engine widens it. The dial is plan data. Anyone
  retesting should start at `lifeValue` 1.5 to 2.0 and re-measure the block
  rate before anything else.
- **Combat search is not where agent games are decided.** Seven personality
  arms over two campaigns reached the same parity conclusion
  (`agent-strength` findings): win-rate gains live in strategy content
  (lines, tutor targets, conversion), not in combat or personality
  mechanics. A better combat solver on a precon board is a small effect.
- **The gates are mostly already 0.15.0.** The hold was the big move; the
  end-step timing on top of it is cosmetic for the metrics that matter, and
  the protection gate fired 10 times in 128 games.

## What the note got right anyway

The observation that the agent was dying to the clock for a reason other
than slow play was correct; the loop above is exactly the "engine hangs on
wide boards" failure mode the note describes, though its cause was ours,
not Forge's. And the Foundations damage rule (no assignment order) was
worth building: `see_damage` re-split 79 multi-blocks in the A/B.

## Files

- `run_ab.py`: harness and `--report`. `runs/` (balanced A/B), `runs_allnew/`
  (divergence arm), `runs_prefix_reask_bug/` (first run, loop present, kept
  for the defect record). Cell JSONL is gitignored with the rest of the raw
  output; `*.sides.json` next to each cell says which seat was NEW.
- Shim: `SeeCombat.java`, the `see*` and gate code in `PlanPlayerController`,
  dials in `DeckPlan`, `simlab-forge-shim-0.16.0.jar`.
- Engine: `deck_plan.py` ships both dials at 0; `engine/tests/test_deck_plan.py`
  pins that. `agent_viability/run_pilot.py` has the `engine016` arm.
