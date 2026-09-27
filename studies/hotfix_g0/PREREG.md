# G0a pre-registration: does the tutoring hotfix remove the harms without collateral? (experiment E0)

Written and committed **before any G0a game is run**. The runner refuses to start unless this file is committed and unchanged; `meta.started` of every cell is later than this file's commit time. The analysis is `read_g0a.py`, committed in the same commit, so the reading cannot drift toward the data either.

Plan references: `tasks/25-repair-plan.md` section 4.4 (the G0a row), WS5 T1, section 3.0 (test beds, pairing, the tutors metrics and guards table), section 2.1 (game-clustered errors, per-deck catastrophe guard), and the R0 gate lesson in `studies/r0_gate/RESULTS.md` (pool at least 32 games per arm for event-rate comparisons, correct for the number of metrics).

## What is being tested

Shim 0.17.0 (branch `shim-0.17.0`, commit b8894e1, jar SHA-256 `c2273bef30d7cd9edb20d711f81bce01444470a91e9d15bbf23f2e3fd3081dfd`) with version-2 deck plans from `engine/deck_plan.py` (`plan_version=2`, every fix flag on): `fix.tutorReach`, `fix.commanderTutorZone`, `fix.noForcedChoices`, `fix.graveyardDest`, pilot lines narrowed to win-band lines, `threatLines` for opponent logic, `search.graveyardTargets`, and the `_FINISHER` self-loss fix.

## Arms (same decks, same clock, same turn cap)

| Arm | Jar | Plans | Seeds |
|---|---|---|---|
| **C** (control) | 0.17.0 (b8894e1) | version 1 (no fix flags: 0.16.0 behaviour by design) | `--seed-forge` per cell, same list as T |
| **T** (treatment) | 0.17.0 (b8894e1) | version 2, all fix flags on | same list as C |
| **Z** (equivalence) | 0.16.0 (62fe295, SHA-256 `f40ae8d2...8cd9`) | version 1 | none (0.16.0 cannot seed) |

## Beds

- **cEDH-A, all plan seats:** pods `n7WpsqsZtdQ` (magda, rog_ishai, selvala_archetype, tymna_thrasios) and `2iA_Jt0d6sM` (derevi, godo_archetype, nadu, rograkh_silas), the decks as regenerated in week 2 (DFC names fixed; 6 of these 8 decks changed, so no comparison is made against pre-week-2 baselines). 4 seat rotations x 8 games per pod = **64 games per arm**.
- **Richard's pod, all plan seats (as in production):** Kess, Reanimator; Skrat's Revenge; Stella Lee, Wild Card; Krenko Goblins. 4 rotations x 4 games = **16 games per arm**. The imported decklists are user data and stay off-repo.
- 900 s clock and 120-turn cap (production settings), `-Xmx3g`, at most 12 JVMs at once on the 16-core dev box.

Total 240 games.

## Metrics and pass rules

All tutor metrics come from `engine/qa/tutors.py` (port-tested: it reproduces the diagnosis figures exactly, `studies/scorecard/port_test.py`). "Unreachable" is the **every-basis** count `pooled.unreachable` (restriction, piece already in the graveyard or exile, not offered by Forge), the stricter of the two definitions the port test names; the restriction-only count is reported beside it.

**Primary (mechanism), arm T, both beds pooled:**

| # | Metric | Baseline | Pass |
|---|---|---|---|
| P1 | `unreachable / tutor_cast` for the shim's own tutor casts | 394/718 (54.9%) corpus; 4/5 on Richard's run | **<= 5%** |
| P2 | `gy_steers_no_use`: plan steers of a graveyard-destination search onto a card with no graveyard use | 2 on Richard's run (Sol Ring x2 over Blasphemous Act) | **0** |
| P3 | `x_zero` and `failed_to_target` among the shim's tutor casts | 18/18 and 26 in the corpus | **0 and 0** |

If arm T logs fewer than 20 shim tutor casts in total, P1 is not decided: 64 more cEDH-A games are run in arms C and T with new seeds, then P1 is read once on the pooled set. P2 and P3 are decided on whatever occurs (0 of 0 passes).

**Guards (collateral), T against C:**

| # | Metric | Pass |
|---|---|---|
| G1 | `casts_per_drawn` (tutor spells cast from hand per tutor drawn, plan seats), arm T | **>= 50%** (stock casts 544/892 = 61% on the diagnosis's seats) |
| G2 | Games won by a Thassa's Oracle alternate win ("won by spell 'Thassa's Oracle'"), T vs C | T **>= 70%** of C (vacuous if C has none; reported) |
| G3 | `counter_fire` agent events per seat-game, T vs C (the `threatLines` check: opponents must still see engine lines as threats) | T within **+/- 25%** of C |
| G4 | Per-deck win share on decided games, T vs C, each of the 12 decks | no deck lower in T by more than **2 SE** (two-proportion SE; games cluster the four seats, so each deck contributes one indicator per game) |

**Equivalence (the flags-off claim), C against Z, both beds pooled (80 vs 80 games):**

| # | Metric | Pass |
|---|---|---|
| E1 | Crashed or short cells (fewer result records than games requested) in any arm | **0** |
| E2 | Every agent-event type present in both C and Z, per seat-game rate, game-clustered SE, Holm-corrected at alpha 0.05 across the event types | **no difference significant** after correction |

Events that exist only in 0.17.0 (for example `tutor_skip`) are excluded from E2 and reported.

## Decision

- **All of P1-P3, G1-G4 and E1-E2 pass:** R1 ships the hotfix. The shim is tagged `v0.17.0`, production is pinned to it, and `MTG_PLAN_VERSION=2` is set at the R1 deploy (preflight refuses version 2 on an older shim).
- **E1 or E2 fails:** 0.17.0 changed behaviour with its flags off. The shim branch is not merged; the cause is found first.
- **Any of P1-P3 or G1-G4 fails:** R1 ships the truth patch with the hotfix off (`MTG_PLAN_VERSION=1`). Then one overnight run per flag alone (`MTG_PLAN_FIX=<flag>`, 4 arms plus version-2 data with every flag off), and the decision is re-made on the per-flag results.

## Expected, not gated (reported)

- `closer_overrides` (plan steers that overrode a stock closer pick, Magda's Portal case): expected to fall, because Magda + Clock of Omens + Liquimetal Torque leaves `plan.lines` in version 2.
- Kess's graveyard steers onto reanimation targets or cards castable from the graveyard: expected and not penalised; the Hullbreaker Horror vs Blasphemous Act choice goes to Richard as a review question.
- Win rates: 64 and 16 games cannot decide anything but a catastrophe; G4 is the only win-rate rule.
- Known classifier limitation (recorded before the run): `engine/combo_bands.py` v0 uses the plan's lenient win set, which counts "infinitely large creature" and "infinite power" as wins. So lines such as Umbral Mantle + Circle of Dreams Druid (Skrat's Revenge) and Umbral Mantle + Priest of Titania (selvala) stay in the version-2 pilot lines, although the playtester called the first one partial. This gate tests harm removal, not line quality; WS8's expert band overrides decide those lines.
