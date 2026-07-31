# 07 — Human-like sim agent (deck-plan-driven, GPL shim)

**Priority: CRITICAL.** Sim credibility is the product. If simulated games read
as "swing at face and lucky Lightning Bolts," nobody trusts the win rates or
the coaching built on them. The goal: games that *feel like Magic* — mulligans
with a reason, attacks that split, blocks that trade, and decks that pursue
their own win condition.

Read CLAUDE.md "Legal posture — two regimes, one bright line" first. The
architecture below exists because of it.

## Architecture (the boundary is the design)

```
THIS REPO (ours, non-GPL)                    SHIM REPO (GPL-3.0, separate)
engine/deck_plan.py  ──deck_plan.json──►  simlab-forge-shim (Java 17, Maven)
combos.py lines      ──────────────────►    • FModel.initialize → Match
web import UI (win-con tags)                • PlanPlayerController extends /
                                              wraps PlayerControllerAi
engine/run_sim.py    ◄──game JSON────────   • typed GameLog → JSON export
humanness_scorecard.py (validation)         • policy params in, decisions out
```

- The shim **links Forge, so it is GPL**: it lives in its own repository,
  never vendored here, invoked as a subprocess jar exactly like Forge is now.
- The shim is a **thin adapter**. Everything clever — win-con tags, card
  weights, personality dials, combo lines — arrives as JSON. If the Java file
  contains strategy knowledge rather than plumbing, it's on the wrong side.
- Forge stays an unmodified dependency (official release jar). The shim
  overrides *decisions among legal options Forge generates*; Forge still
  adjudicates every rule. This preserves the trust claim: rules correctness
  is unchanged, only choice quality improves.

## The deck plan (how the AI "sees" the deck's purpose)

New: `engine/deck_plan.py` — builds `deck_plan.json` at import time from:

1. **Win-condition tags** chosen by the user at deck import (new UI field,
   suggested automatically, editable). Starting vocabulary — extend as needed:
   `counters-proliferate`, `go-wide-tokens`, `voltron-commander-damage`,
   `combo`, `aristocrats-drain`, `spellslinger-burn`, `mill`, `stax-control`,
   `tribal-anthem`, `ramp-big-mana`, `reanimator`.
2. **Card roles** derived from Scryfall oracle text + type lines: payoff /
   enabler / protection / removal / land. (Invariant check: oracle text here
   informs *strategy hints and display*, never what happened in a game —
   Forge remains the only adjudicator.)
3. **Combo lines** from `combos.py` (Commander Spellbook), listed as ordered
   piece-sets with the finisher marked.
4. **Synergy keywords** per tag — e.g. `counters-proliferate` watches
   `charge counter`, `+1/+1 counter`, `poison counter`, `proliferate` —
   the same vocabulary `deck_telemetry.py` already greps for.

Example (Kilo): tags `counters-proliferate` + `combo`; payoffs Lux Cannon /
Dawnsire; plan says: keep hands with a counter-payoff plus an enabler,
sequence counter-producers before proliferate effects, tutor toward missing
combo pieces, protect the payoff once it's deployed.

## Stages (each shippable alone)

**Stage 0 — shim skeleton.** Java project: initialize FModel, run an N-game
4-player Commander match programmatically, emit typed `GameLog` entries
(`MULLIGAN`, `ZONE_CHANGE`, `COMBAT`, …) as JSON-lines to stdout. No behavior
changes — stock `PlayerControllerAi` for all seats. `run_sim.py` gains
`--agent shim` to invoke it and adapt its output (same downstream schema).
*Bonus measured here:* whether typed ZONE_CHANGE entries include battlefield
entries — if so, this is the path past the 86.5% board-reconstruction ceiling.

**Stage 1 — mulligans + plan-aware casting.** Override the mulligan hook:
human keep heuristics (2–4 lands, a castable early play, a plan reason —
payoff or enabler in hand; free first mull in Commander). Override spell
choice ordering: re-rank Forge's legal candidates by plan weight before
delegating. Baseline to beat: stock AI keeps 7 in 97% of hands (measured
across 1,786 hands in sim_results logs).

**Stage 2 — combat humanization.** Attack splitting (stock: 244/244 attacks
single-defender) and block valuation (stock block rate: 14%). Both have
human targets in `training/ai_vs_human_analysis.md`.

**Stage 3 — politics + personality.** Grudge/threat memory (who removed my
things, who is closest to winning), kingmaking avoidance, per-seat
personality dials: aggression, greed (combo pursuit vs safety), optional-
trigger miss probability. **Never** skip mandatory triggers — that produces
illegal games and poisons win rates; human imperfection is modeled in
*choices*, not rules violations.

## Training data track (parallel, not blocking)

The 7 extracted games + humanness scorecard are sufficient to validate
Stages 1–2 (`frontend_architecture.md` §5). For Stage 3 calibration, extract
toward 30–50 games **with published decklists** (Mana Dorks-style) using the
documented pipeline in `training/README.md`. Prioritize videos with
decklists — those are replayable in Forge for direct human-vs-agent diffing.

## Acceptance criteria

- [ ] Shim repo builds with `mvn package`; runs a 4-player Commander sim and
      emits JSON parseable by the adapter; results flow to the existing UI
      unchanged.
- [ ] `engine/deck_plan.py <deck.dck>` emits a plan JSON; import UI offers
      auto-suggested, editable win-con tags; plan stored beside the deck.
- [ ] Stage 1: agent mulligan keep-rate and average kept-hand size move
      measurably toward the human baseline; report both numbers in the task
      close-out and record them in `engine/SIM_CALIBRATION.md`.
- [ ] Stage 2: attack-split rate > 0 and block rate materially above 14% on
      the standard 4-deck gauntlet; humanness scorecard shows improvement on
      its four metrics with no win-rate baseline corruption (re-run archetype
      baselines and update `SIM_CALIBRATION.md` in the same commit).
- [ ] A `humanness_scorecard.py` (new, engine/) computes the four scorecard
      metrics from any sim result so regressions are one command.
- [ ] Docs: CLAUDE.md gotchas + SIM_CALIBRATION updated — sim numbers become
      "Sim Lab agent vX" numbers, labeled distinctly from stock-Forge runs.

## Verification

```bash
python3 engine/deck_plan.py engine/decks/kilo_helm_final.dck   # plan JSON to stdout
python3 engine/humanness_scorecard.py <result>.json            # 4 metrics
python3 engine/tests/test_adapter.py                           # still ALL PASSED
python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch  # no regression
```
