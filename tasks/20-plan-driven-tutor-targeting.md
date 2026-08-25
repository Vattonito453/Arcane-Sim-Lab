# 20 — Plan-driven tutor targeting (combo agnostic)

Playtester feedback (2026-08-07): tutors act as a closer, not an opener — the
shim only steers a search when a combo line is nearly complete, and every
other tutor falls through to stock Forge AI's plan-blind target choice.
Vincent's direction from that thread: tutors should aggressively advance the
deck's win condition whether or not a combo is involved (example given:
Finale of Devastation is a finisher tutor — you seek a creature to the
battlefield and pump the team, not a combo piece).

Design decision this spec encodes: do NOT build a board evaluator. The
win-condition understanding already exists as data — `deck_plan.py` tags,
roles, weights and finisher detection cross the GPL boundary as JSON — and
the shim already sees its own battlefield natively. The missing piece is a
thin ranking rule at search-choice time. Knowledge in Python, mechanism in
Java, per the boundary (CLAUDE.md "Legal posture").

## What exists today (read before scoping)

- `deck_plan.py` ships per-deck JSON: `tags`, `weights` (1–8), `roles`
  (commander/payoff/enabler/protection/removal/tutor/filler), `threat`,
  `lines` (combo piece-sets), `tutors` (nonland tutors). The shim reads it.
- The shim's line-of-sight gate (fixed in shim 0.3.0 — it was dead code
  before, audit A18) steers searches only when ≤1 piece is missing, or 2
  with a tutor in hand. Telemetry events: `search_seen` (options, sighted,
  missing), `tutor_steer`, `combo_cast`.
- Un-steered searches resolve under stock Forge AI targeting. Nothing
  fizzles; the aim is just plan-blind.
- Measured on the VM run of 2026-08-07 (16 games, pre-0.3.0 shim): 16
  `search_seen`, 2 sighted, 1 steer. Post-0.3.0, measured locally
  2026-08-25 (8 games, Magda pod, shim 0.4.1): 176 `search_seen` in 8
  games. Search events cluster heavily (a mass search resolves card by
  card; one turn produced ~25 events), so they are not independent
  samples.

## Stages

**Stage 0 — measure the gap (shim repo, no behavior change).** Extend
`search_seen` to record what stock AI picked and what a plan-weight ranking
would have picked (`picked=X planPick=Y agree=bool`). Run a tutor-heavy pod,
report the disagreement rate and eyeball 10 disagreements: is the plan pick
actually better? This number is the justification (or refutation) for
Stage 1, and later the proof of improvement. Do this AFTER the VM is on
shim ≥0.3.0, or run locally.

**Stage 0 result (measured 2026-08-25, shim 0.4.1 branch
`stage0-search-seen-measurement`, run and analyzer in
`studies/tutor_targeting/`).** 8 seat-rotated humanized games on the Magda
pilot pod from `studies/human_ceiling` (magda / rog_ishai / tymna_thrasios
/ selvala_archetype, clock 900, serial, 2 timeouts). 176 searches resolved;
121 (68.8%) offered at least one plan-weighted option; stock agreed with
the plan-weight ranking in 6 of those 121 (5.0%), disagreement 95.0%.

The eyeball check inverts the naive conclusion: the plan pick is
essentially never better. Current plan weights are keep-quality weights
(Sol Ring, Relic of Legends, Arcane Signet, mana dorks, counterspells), so
the ranking wants a mana rock in round 8 or later, at the exact moment
stock targeting is choosing a payoff. Worst case observed four times:
stock picked Portal to Phyrexia, the human-verified correct Magda fetch
(see `studies/human_ceiling/RESULTS.md`), and the plan ranking would have
overridden it with Relic of Legends. Shipping Stage 2 on today's plan data
would make play strictly worse.

So Stage 0 neither confirms the >=80% stop condition nor green-lights the
mechanism: it moves the blocker to Stage 1. Tutor-target weights need to be
their own scale (payoffs and win-line cards, not keep enablers) plus the
context hints below; then re-run this measurement and require the eyeballed
plan picks to beat stock before Stage 2 merges. One encouraging side
observation: under agent v3 the stock targeting layer DID fetch Portal in
several games, so the target policy only has to protect and generalize a
choice stock sometimes finds, not invent it from nothing. (Corrected
2026-08-25: pure stock AI fetches Portal too, in the human_ceiling study's
own zone records and in a fresh stock rerun; the study's "never fetched"
claim was false and is corrected in `studies/human_ceiling/RESULTS.md`.
The binding gap is converting the fetched card into the win, not finding
it; see the outcome comparison in `studies/tutor_targeting/README.md`.)

**Stage 1 — plan data (this repo).** Give the plan a general target policy,
all data, no logic in Java:

- Promote every nonland tutor to plan weight (today they only get weight
  when combo `lines` exist).
- Per-card `context` hints where cheap and honest: `ramp` before turn N,
  `finisher` when own creature count ≥ K (Finale case), default = weight
  order. Derive from the same oracle-text heuristics deck_plan already uses;
  no new inference regime.

**Stage 1 result (landed 2026-08-25).** `deck_plan.py` now emits an additive
`search` section per deck, deliberately separate from `weights` (which the
shim also uses for mulligan keeps, cast priority, and the threat index, so
target values must not contaminate it):

```json
"search": {
  "targets":  {"Portal to Phyrexia": 6, "Sol Ring": 5},
  "context":  {"Sol Ring": {"hint": "ramp", "beforeRound": 5},
               "Craterhoof-alike": {"hint": "finisher", "minCreatures": 3}}
}
```

Semantics (the contract Stage 2 implements; the 0.4.2 measurement already
follows it): rank the legal options by target value; a card absent from
`targets` is worth 1 implicitly; a `ramp` card decays to 1 from table round
`beforeRound` on (rounds, not Forge player-turns); a `finisher` card is
worth 1 until the searcher controls `minCreatures` creatures. Ties and
all-floor lists mean the plan has no opinion: defer to stock. Combo
line-of-sight keeps absolute priority over all of this. Scale: combo piece
or finisher text 8, tagged payoff 7, cmc>=6 bomb the tags missed 6, cheap
mana source 5 (ramp-gated), protection 4, removal 3. Nonland tutors are
promoted to keep-weight 5 unconditionally (the combo-lines gate is gone).
Tests: `engine/tests/test_deck_plan.py`.

Two provenance fixes that fell out of Stage 1: plans record
`factsCoverage`, and `run_sim.py --humanize` warns when the card-fact
cache knows less than 90% of a deck. That matters because **the Stage 0
run's plans were built from a cold cache** (80 of ~100 Magda-list cards
unknown, zero combo lines) and nothing said so. The Stage 0 verdict stands
(keep weights rank fetch options wrongly by construction), but its
coverage/agreement numbers should be read as cold-cache numbers; the
Stage 1 re-measurement below runs warm.

**Stage 1 re-measurement (2026-08-25, shim 0.4.2, warm cache, plans with
36 Magda targets and 13 Magda lines; runs in
`studies/tutor_targeting/runs_stage1/`).** Same pod, same shape: 8
seat-rotated humanized games, clock 900. The run itself was much
healthier: 0 timeouts (2 before), every game decided, durations 20-215 s.
That is a Stage 1 data effect, not a mechanism change: warm plans carry
real combo lines, so pursuit engages.

87 searches; 58 (66.7%) had a plan opinion (all mode=targets); stock
agreed 17/58 (29.3%), up from 5.0%. The eyeball check now favors the
plan: the bulk of the 41 disagreements are the plan preferring a
Spellbook-verified line piece (Ashaya, Priest of Titania, Hyrax Tower
Scout, Demonic Consultation, Devoted Druid, Adaptive Automaton, Copy
Enchantment) where stock fetched a big-toughness vanilla (Phyrexian
Dreadnought, Phyrexian Soulgorger, Slumbering Trudge), a mana filter
(Elvish Spirit Guide), or a land (Ancient Tomb). Zero disagreements
propose a mana rock; the old failure mode is gone. The honest residue:
a Magda cluster where stock picked Portal to Phyrexia (target 6) and the
ranking prefers a line piece (8). Both are defensible; the human line was
Portal, the sim's fastest observed wins run through the lines, and combo
line-of-sight keeps absolute priority at steer time either way. Stock's
Selvala Dreadnought picks also carry real synergy (Selvala taps for the
biggest power), so a few of the 41 are judgment calls, not stock errors.

**Verdict: the Stage 2 gate is met.** Plan picks beat stock on eyeball,
agreement is nowhere near the 80% stop condition, and the ranking's
failure mode (enabler fetishism) is fixed in data. Stage 2 can build the
thin mechanism.

**Stage 2 — mechanism (shim repo, thin).** At search-choice time, rank the
LEGAL options Forge offers by plan weight + context hints; combo
line-of-sight keeps absolute priority (closer beats opener); unranked or
tied → defer to stock AI. Never touches combat, politics, or anything but
the agent's own search choices. Emit `tutor_steer` with `mode=plan|combo`.

**Stage 3 — honesty plumbing (this repo).** Bump the shim/agent version and
surface it (depends on the rotated-merge fix that currently drops the
version from `meta.agent`). Steered runs must not pool with earlier agent
versions — same rule as every agent change. Re-run a baseline pod and record
the before/after in SIM_CALIBRATION.md if any documented number moves.

## Acceptance criteria

- [x] Stage 0 disagreement rate measured and written into this file before
      Stage 2 merges; if stock AI already agrees ≥80% of the time, stop and
      say so instead of shipping the mechanism. Measured 2026-08-25:
      agreement 5.0%, but the eyeballed plan picks were worse than stock's,
      so Stage 2 stayed blocked. Re-measured after Stage 1 the same day:
      agreement 29.3%, plan picks beat stock on eyeball (line pieces over
      big-toughness vanilla), Stage 2 unblocked.
- [ ] Plan JSON schema change is additive; an old shim ignores it cleanly.
- [ ] With Stage 2 on: a Finale-of-Devastation-style search in a test pod
      picks the plan's top-ranked legal creature (verify via `tutor_steer`
      events), and combo line-of-sight still outranks it when both apply.
- [ ] Agent version bumped; analysis/UI label steered runs distinctly;
      no pooling with pre-steer results anywhere.
- [ ] `python3 engine/tests/test_adapter.py` and the staging/accounting
      tests pass; `cd web && npm run verify` clean if any UI text changes.

## Verification

```bash
python3 engine/deck_plan.py engine/decks/<tutor-heavy>.dck   # inspect weights/context
python3 engine/tests/test_adapter.py
# after a Stage-0 run: grep search_seen events, compute agree rate
# after Stage 2: same run, confirm tutor_steer mode=plan events and that
# combat/politics telemetry is byte-identical on a fixed seed
```
