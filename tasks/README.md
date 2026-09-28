# Task specs

One file per independently shippable unit. Each spec states what to build, which
files to touch, what "done" means, and how to prove it. Read `../CLAUDE.md` first —
its invariants bind every task here.

**Work one spec at a time and finish it.** Each is sized to be completable and
verifiable on its own; none requires a later one to be useful.

**Through February 2027 the repair plan sets the order.**
`25-repair-plan.md` (with the UX review in `26-ux-review.md`) sequences the
work week by week, and the owner decisions below bind it. Where the tier list
under "Order" disagrees with the plan or with the freeze, the plan wins.

## Decisions 2026-09-26

Vincent accepted every recommendation in `25-repair-plan.md` §6 on
2026-09-26. Each row is the decision, the recommendation as accepted, and
what still has to happen for it, with the date or gate the plan gives.

| # | Decision | Accepted | Follow-through |
|---|---|---|---|
| 0 | Reviewed developer-days per week | About 7 (two sessions most weekdays); §4.5 scales everything else | Calendar in §4 stands |
| 1 | Freeze combat, personality, hold and attack-targeting work until G4 | Yes; stock-value dial settings allowed under the harm-removal exception (§2.3) | Freeze note below |
| 2 | Readmission scope | Production: every seat (all are plan seats). Studies: the frozen pure-stock control plus a stock+readmit arm with stock dials, after an A/A check. Never without plan data | E3, G2b (Mon 11/23) |
| 3 | KeyCards scope | A plan-seat staged copy in studies; all seats in production if E4 passes | W17 |
| 4 | Is the `orderAndPlaySimultaneousSa` override a thin adapter? | Yes, under the written checklist: data-named triggers only, delegate to `super` otherwise, no card names or scoring, lint, at most 600 lines; recorded in the shim README | Checklist signed off Fri 10/16, after the harness spike |
| 5 | DS amendment A: opaque reading surfaces, backdrop only on ceremony screens, sentence case, no resting glow, home §5-6 removed | Approve from screenshots | Screenshots and approval Wed 10/28 |
| 6 | DS amendment B: violet retired, monochrome status shapes, `--combat` and `--warn` tokens | Deferred until after G-UX | W9 |
| 7 | Install Node LTS on the dev box | Yes, on day 1 | Mon 9/28 |
| 8 | Retire random block skips and the "humanized" claim | Yes; applied through E8 | E8, G2a (Mon 11/9) |
| 9 | Where the knowledge base lives | Compiler inputs, tools, scenarios and overrides in the main repo's `simkb/`; generated and human data in a private data repo; per-run output on the VM. The data repo and `studies/diagnosis_2026-09/local/` join the strip-before-public list | W9 |
| 10 | Reviewer schedule and authority | Nightly, proposals only, in its own data-repo worktree, never pushes; every override is a PR Vincent merges, for at least 6 weeks | W9 |
| 11 | Flag queue owner, and a key for Richard | Vincent triages 30 minutes a week; a flags-only key (`MTG_FLAG_KEYS`) so Richard's key cannot start sims | Fri 10/9 |
| 12 | Where owner data (win-con tags, band notes) lives before accounts exist | A deck sidecar in `$MTG_DATA_DIR/decks/`, editable with the API key; the UI says "saved for this deck" | W8 |
| 13 | Archetype baselines (CLAUDE.md "show them" vs SIM_CALIBRATION "re-measure first") | Re-measure under the plan agent after G3 (W18); until then show only the labelled pod average | CLAUDE.md and `engine/SIM_CALIBRATION.md` amended in the same commit as this memo |
| 14 | Human ground truth | 50 labelled moments (Vincent 20 in W11, Richard 30 over W12 to W14); human traces with `trace_entry.py`, owned by Vincent, first 2 games over the holidays and 10 by W20; Vincent supplies 8 fresh cEDH lists if the holdout falls short | Mon 10/19 |
| 15 | Flat cost-glyph commission | Deferred; painted pips at 18px or larger meanwhile | W18 |
| 16 | Executor in production | Off until G3 plus the VM CPU check, then on for plan seats | W16 |
| 17 | Precons for calibration only; `model_runs_agent.json` stays uncommitted | Yes / yes; refit on clean arms after G3 | Standing rule |
| 18 | Capacity: two sessions or one | Two sessions through R2; then Vincent chooses, and the §4.5 order and cut list apply | After R2 (Fri 11/13) |
| 19 | Prediction model on plan-piloted runs | Label it "fit on stock Forge games" from R1; rank check at each pilot-changing release; suppress it if the check fails; refit after G3 | Fri 10/9 |

**Capacity.** About 7 reviewed developer-days a week: two Claude Code
sessions, Track A (engine, shim, QA analyzers) and Track B (product, web, QA
plumbing, reviewer), each in its own worktree, both reviewed by Vincent,
through R2. Holiday weeks count as 2 days, Thanksgiving week as 5.

**Freeze (decision 1; repair plan §2.5, WS0 task 7).**
- No new combat, personality, hold or attack-targeting features or study
  arms before G4 (Fri 2027-01-22). The only exceptions are dials turned to
  their stock values under the harm-removal exception: E8, the random-block
  retirement (decision 8) and R0's 0.16.0 pin. The 0.16.0 combat solver
  stays off.
- Follow-ups to tasks 21, 23 and 24 are **parked** until G4: task 21's
  Half 2 and any retuning after its fourth criterion, further attack-target
  or kingmaker retuning under task 23, and task 24's retention-metric rework.
  G4 lifts the freeze only if the WS9 and WS5 targets are met and a combat
  detector ranks in the top 3 by rate times severity.
- Also from day 1: no acceptance on overall win share; no combo or tutor
  study on precons; no Pilot's notes before the tutor-weight fix; no LLM
  output changes behaviour without a human merge; "humanized" is no longer a
  product claim.

**Holdout.** Drawn by lot on 2026-09-26: `Bq-nFi0f1jA` and `CxKMqO36DdM`.
Untouched until G3; the rule, the seed and the caveats are in
`studies/holdout/HOLDOUT.md`.

## Decisions 2026-09-27

Three follow-ups raised by the week-1 work; Vincent accepted the
recommendation on each.

| Decision | Accepted | Where it landed |
|---|---|---|
| Holdout seats that duplicate a cEDH-dev decklist (Bq-nFi0f1jA/cabbage_merchant, CxKMqO36DdM/joseph_ral) | Report holdout results per deck, and pooled both with and without those two seats; the draw stands | `studies/holdout/HOLDOUT.md` rule 5 |
| Import warning wording | "Forge's AI doesn't cast these cards on its own" (our pilot does cast some through combo pursuit and tutoring) | `engine/convert_decklist.py`; WS4 task 3 text updated |
| Commander fidelity | Polluted only when a commander was refused at load or the deck lists none; loaded-but-never-cast is a visible, clean-severity note (`commander_never_cast`) | `engine/run_sim.py`, `engine/validity.py` (VALIDITY_VERSION 3); WS4 task 4 text updated |

## Order

Dependencies are the only reason to prefer one order over another. Within a tier,
pick by what you care about most.

```
Tier 1 — product value, no infra dependencies
  01-coaching-pipeline.md      the flagship feature; the product is a sim viewer without it
  02-telemetry-ui.md           deck_telemetry.py has no UI; small and high-value
  03-rules-assistant.md        retrieval already exists; needs generation + cache
  07-humanlike-agent.md        CRITICAL for sim credibility — deck-plan-driven GPL shim,
                               staged (skeleton → mulligans/plan → combat → politics)
  08-goldfish-mode.md          Part A: solo rules-free playtest sandbox (web-only,
                               no opponent/adjudication/outcome — see its legal
                               line); Part B: AI goldfish telemetry after 07 Stage 0
  10-counter-events-replay.md  parse counter triggers (+1/+1, charge, energy,
                               experience, poison) from the Forge log into replay
                               events and badges — proof the triggers fired; the
                               shim's GameLog is the same free text (measured),
                               so this parser covers both paths
  11-card-art-coverage.md      audit + fix missing card art: stale cache entries,
                               the _offline latch, name-normalization parity
  12-deck-picker-gallery.md    rebuild /new as an art-forward deck gallery
                               (commander art tiles, hover decklist, selected-decks
                               rail) in the design system; needs commander in /decks
  13-deck-link-import.md       import a deck from a Moxfield/Archidekt URL, not
                               just pasted text
  14-commander-damage-tracking.md  live per-opponent commander-damage totals in
                               the replay, not just the post-hoc win reason
  16-post-run-analysis-rollup.md   surface the win-method distribution and link
                               Overview/Telemetry/Coaching together; most of
                               "analysis after a sim" already shipped — read
                               the file before scoping more here
  17-deck-history-page.md      a deck's own page: every run it's appeared in,
                               rolled-up win rate/win-method/combo stats, and a
                               capped set of cross-run highlights; depends on
                               12, do after 16
  18-decklist-hover-preview.md  DOES NOT EXIST. Listed here for a while with no
                               file behind it; write the spec before citing it.
  19-hidden-zones-replay.md    show each player's hand, graveyard, exile and a
                               library count in the replay; on shim runs the
                               zones stream already records all of it (measured),
                               so this is board.py + UI work, no shim change
  20-plan-driven-tutor-targeting.md  tutors advance the deck's plan, not just
                               combos: measure stock-AI target quality first,
                               then rank legal search options by plan weight;
                               knowledge as data, shim stays thin
  21-interaction-timing.md     PARKED until G4 (decisions 2026-09-26). Spend
                               answers when a plan is being executed, not
                               in turn order; carries a 2026-08-30 addendum
                               measuring what the counter veto actually declines
  22-equipment-policy.md       RETRACTED premise: the "0 of 20 equips" figure was
                               a detection artifact, Forge logs "activated X
                               targeting" and never "Equip". Read before reviving
  23-threat-aimed-attacks.md   PARKED until G4. Threat signature v2 shipped; the
                               re-measure came back noise
                               (studies/threat_targeting.py)
  24-defensive-retention-metric.md  PARKED until G4. keptEnough needs a
                               denominator a player can meet; today it is a
                               table-wide maximum
  25-repair-plan.md            THE PLAN through February 2027: prove the combo
                               executor, fix what users see, then build; its
                               section 6 decisions are recorded above
  26-ux-review.md              the expert UX review and redesign direction the
                               plan's WS11 and WS12 build from

Tier 2 — needed for multi-host scale (do when Tier 1 saturates one box)
  04-postgres-queue.md         unlocks workers on separate machines
  05-object-storage.md         moves 2.6 MB result files off the app host
  09-multi-format.md           Pauper/Standard/etc; mostly plumbing + per-format calibration
  15-sim-performance.md        research spike: measure where sim wall-clock time
                               actually goes before proposing a fix; may hand off
                               into 04/05/07 rather than standing alone

Tier 3 — needed for open signup
  06-accounts-and-quotas.md    replaces shared API keys with per-user identity
```

## What is already done

Don't rebuild these. See `deploy_plan.md` for the measurements.

- Threaded API, gzip, per-game payload endpoints, immutable cache headers
- API-key auth, per-caller quotas, queue backpressure, input validation,
  path-traversal guards
- Scryfall card cache (`engine/cards.py`) and board reconstruction
  (`engine/board.py`, 86.5% exit match — see CLAUDE.md for the ceiling)
- Front end: home, import, run progress, run results, replay theater
- Docker compose with env config, healthcheck, `.env.example`
- G0a, the tutoring-hotfix gate: PASS on 2026-09-27 (`studies/hotfix_g0/RESULTS.md`).
  Shim 0.17.0 is cleared for R1 at commit b8894e1 only; merge simlab-forge-shim
  PR #15, tag `v0.17.0` there, and set `MTG_PLAN_VERSION=2` at the R1 deploy.

## What is deliberately NOT here

- **Playable game client.** Out of scope permanently; see `CLAUDE.md` legal.
- **Patching Forge.** Still out — but *linking* it from a separate GPL shim is
  now allowed under the 2026-07-31 posture (CLAUDE.md "Legal posture"); that
  work is task 07, and it also unlocks board snapshots via the typed GameLog.
- **Paid tier.** Needs legal review before any code. (Ad revenue is the
  sanctioned first monetization — see CLAUDE.md.)

## Definition of done, for every task

1. The acceptance criteria in the spec are met.
2. The verification commands in the spec pass, and you ran them.
3. `python3 engine/tests/test_adapter.py` still passes; `cd web && npx tsc --noEmit`
   is clean.
4. `python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch`
   shows no regression in `exit_match_rate`.
5. Any number you changed in a doc is re-measured and updated in the same commit.
6. New UI obeys `mockups/design_principles.md` Part 3 — audit your own diff for
   ALL-CAPS labels, pills, a second `.btn.pri`, emoji, and new CSS files.
