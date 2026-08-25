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

176 searches; 68.8% offered a plan-weighted option; agreement 5.0%
(6/121). The eyeball check shows the plan picks are WORSE than stock's:
current weights are keep-quality enablers, so the ranking fetches mana
rocks late, and would have overridden stock's Portal to Phyrexia (the
human-verified correct Magda fetch) with Relic of Legends four times.
Stage 2 is blocked on Stage 1 plan data, not justified by this rate.

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
