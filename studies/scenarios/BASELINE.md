# Scenario suite baselines (WS3 task 4)

The initial suite (S1 to S9, S5b, and the C1 positive control on 20 real
boards) ran 20 trials per scenario on two arms, stock Forge and the plan
pilot, on shim 0.17.1 (`967cb71`) on the dev box on 2026-09-28. Stock
reproduces every in-game failure the plan names: 0/20 on S1 and S2, and 0/20
on every other loop scenario (S3, S4, S6, S7). Of the four acceptance rows
fixed in the plan, two pass (S1 and S2 reproduce; one arm takes 21 min), the
load row is partial (every S scenario loads exactly in 20/20 trials per arm;
C1 plays all 20 boards and seeds the Godo and Helm line on all 20, but 10
boards differ elsewhere after the load), and C1 fails its target: stock won
10/20 against a target of at least 17/20. Forge itself won only 10 of these
20 boards in the games they came from, and 5 stock trials per board (100
trials) put the harness at 48/100, 43/50 on the boards the game won.

The review (branch `r3/harness-review`) found that 3 of the 20 C1 boards
had been written with an unpaid shock land untapped that was tapped in the
game (anomaly 14), regenerated them, re-ran those 3 boards in every C1
run below, and re-ran S1, S2 and all of C1 under stock for 10 trials each
(Review re-run, at the end). Every C1 figure here is on the regenerated
boards; before the fix the stock row read 9/20 and the supplement 49/100.

The plan arm is reported, not judged. It converts S5 (Thassa's Oracle) 20/20
on the scenario turn and no other S scenario (C1: 11/20). It also reproduces both tutor
regressions: Magda fetched Battered Golem over Portal to Phyrexia in 20/20
trials, and Kess binned Archon of Cruelty, never Blasphemous Act or
Hullbreaker Horror. And it kills itself under an opposing Torpor Orb in all
19 scored S5b trials.

## Acceptance (the plan's table, fixed before running)

| Metric (tasks/25-repair-plan.md, WS3) | Target | Measured | Verdict |
|---|---|---|---|
| Scenarios that load and play | 10/10, or 8/10 via the 2-player fallback | 4-player route. Stock and plan: S1 to S9, S5b and S8 loaded exactly as written and played to a result in 20/20 trials each, with no errored game. C1: all 20 boards play in both arms, and the line pieces (Godo, Helm attached) load as written on 20/20. The whole board loads exactly on 10/20; the other 10 differ in 1 to 3 cards off the line (below). So 9 of the plan's 10 rows pass outright and C1 passes on its line but not on its whole board. | **Partial** (9/10 exact; C1 line 20/20, board 10/20) |
| C1 positive control | ≥ 17/20 under stock | **10/20** won within 8 turns (4/20 on the scenario turn). Forge's own games on the same 20 boards: 10/20 within 8 turns, 5/20 on the turn. Board by board, the harness agrees with the game on 18/20. The review's 10 trials per board: 97/200. | **Fail** |
| Stock reproduces its in-game failures on S1 and S2 | ≤ 2/20 each | S1 **0/20**, S2 **0/20**. The Conscripts copy's untap never targeted Kiki-Jiki (0 of 39 triggers), and Derevi's trigger never targeted Gaea's Cradle (0 of 155). The review's re-run: 0/10 each, 0 of 19 and 0 of 74. | **Pass** |
| Suite wall time, one arm | under 50 min | Stock **1,274 s (21.2 min)**, plan **1,441 s (24.0 min)**, 220 trials per arm at 8 JVMs. | **Pass** |

Why C1 fails, and what it does and does not show:

- The target came from "stock converts 28/32 in games once Helm is
  attached". That figure (studies/diagnosis_2026-09/verify/helm.py) counts
  games where the Godo seat reached 4 or more combats in one turn, pooled
  over pilots (stock alone: 19 of 22; recomputed from `helm_rows.json` in
  review): it conditions on the loop having already run. A board seeded
  before combat cannot condition on that. Among stock seat-games with Helm
  attached to Godo, 21 of 31 were eventually won. Among the 23 attached in
  the precombat main phase of Godo's own turn (the population C1 draws from),
  the 20 drawn won 14/20 at any time, 10/20 within 8 turns and 5/20 on the
  attach turn.
- So no pilot that plays like Forge could reach 17/20 on these boards.
  With the 95% intervals, the harness's 10/20 (0.30 to 0.70) and the games'
  10/20 are the same rate. A supplement of 5 stock trials per board (100
  trials, below) gives 48/100 (0.39 to 0.58), and the review's 10 trials
  per board give 97/200 (0.42 to 0.55). On the 10 boards the game won
  within 8 turns, the harness won 43/50 in the supplement (85/100 in the
  review); on the other 10 it won 5/50 (12/100). The harness tracks Forge
  board by board, and the 17/20 target was set on the wrong base.
- What would pass the target as written is a board that converts for any
  pilot, like `smoke/smoke_godo_helm.json` (4/4 for both arms). That is a
  loader check, not a control on Forge's play, which is why C1 uses real
  boards.

## What ran

- Shim `shim-0.17.1-967cb71.jar` (sha256 `56758de2551b70e8510545f5b426fcdc5fc2adfcb6781f570e9d89375ff064fe`),
  branch `shim-0.17.1-scenario` of the public shim repo (not pushed yet),
  Forge 2.0.13 desktop jar, JDK 17. Dev box: Windows 10, 32 logical CPUs,
  63 GB RAM, 8 JVMs at `-Xmx3g`, one game per JVM.
- Seeds: trial k uses `--seed-forge 2026101400+k` and the same library
  shuffle in both arms (k = 0..19). Each C1 board runs as trial 0.
- Arms: `stock` (every seat `stock:Default`) and `plan` (every seat
  `plan:SimLabHuman`, plan version 2 with every fix flag on, the tutoring
  hotfix). Plans were built by the runner. For pods 2iA_Jt0d6sM and
  n7WpsqsZtdQ and for C1 they came from `--data-dir <scratch>/g0a/cache_cedh`
  and match G0a's: the 2iA file byte for byte (sha256 `ed88b2e4...`), and
  n7W deck for deck (the file lists the decks in the scenario's seat
  order). The OuY6mdiXbHU plans (S1) were built fresh from the same cache.
  S8's came from `<scratch>/g0a/cache_richard`, over the normalised copies
  of Richard's decks (anomaly 13).
- Decks: allowed study pods only. S1 is OuY6mdiXbHU; S2 and S7 are
  2iA_Jt0d6sM; S3 to S6 and S9 are n7WpsqsZtdQ; C1 is 2iA_Jt0d6sM; S8 is
  Richard's pod through `$SIMLAB_PRIVATE`. No holdout deck was used.
- Repo commits recorded by each run (the code that runs trials, `trial_cmd`
  and the writer, did not change between them; later commits changed report
  parsing, which is rebuilt from the raw logs): stock suite `facd33c`, stock
  S8 `a74ab54`, stock C1 `02a91bf`, plan suite `c775175`, plan S8 and C1
  `02a91bf`. All reports were rebuilt with `--report-only` at the commit
  that adds this file. In review, the 3 regenerated C1 boards (anomaly 14)
  were re-run in stock C1, plan C1 and the supplement by the same commands
  on a copy of these directories (6 JVMs; the runner re-ran exactly the 21
  trials whose state file had changed). Those invocations record
  `51fc0c8-dirty`: the trial code was committed, the dirty file was an
  uncommitted SPIKE.md edit. `suite/baseline.json` lists every invocation
  per directory under `invocations`; the review's copy is
  `<scratch>/harness_review/final/`.

```bash
# one arm (the driver ran these three in sequence, timing each)
SIMLAB_PRIVATE=<scratch>/scenario_suite/private   # Richard's decks, S8 only; never committed
py studies/scenarios/run_scenarios.py studies/scenarios/suite/s{1,2,3,4,5,5b,6,7,9}_*.json \
    --jar <scratch>/harness/shim-0.17.1-967cb71.jar --out OUT/stock/suite --arms stock \
    --trials 20 --parallel 8 --seed 2026101400 --data-dir <scratch>/g0a/cache_cedh
py studies/scenarios/run_scenarios.py studies/scenarios/suite/s8_kess_unmarked_grave.json \
    --jar ... --out OUT/stock/s8 --arms stock --trials 20 --parallel 8 --seed 2026101400 \
    --data-dir <scratch>/g0a/cache_richard
py studies/scenarios/run_scenarios.py studies/scenarios/suite/c1/c1_*.json \
    --jar ... --out OUT/stock/c1 --arms stock --trials 1 --parallel 8 --seed 2026101400 \
    --data-dir <scratch>/g0a/cache_cedh
# the same three with --arms plan and OUT/plan/...
# C1 supplement: 5 stock trials per board, trial 0 reused (cached) from OUT/stock/c1
cp -r OUT/stock/c1 OUT/stock_c1_x5
py studies/scenarios/run_scenarios.py studies/scenarios/suite/c1/c1_*.json --jar ... \
    --out OUT/stock_c1_x5 --arms stock --trials 5 --parallel 8 --seed 2026101400 \
    --data-dir <scratch>/g0a/cache_cedh
# then the tables:
py studies/scenarios/suite/compile_baseline.py --suite OUT/stock/suite OUT/plan/suite \
    --s8 OUT/stock/s8 OUT/plan/s8 --c1 OUT/stock/c1 OUT/plan/c1 --c1-supplement OUT/stock_c1_x5 \
    --timing OUT/timing_stock_final.json OUT/timing_plan.json --json studies/scenarios/suite/baseline.json
```

The raw JSONL, state files and per-arm reports stay in
`<scratch>/scenarios_runs/final/` (outside git). `suite/baseline.json` is
the committed summary (per scenario and arm, plus the per-trial fields the
tables use).

## Per scenario and arm

Columns: *Loaded* is exact (every zone, life and battlefield signature as
written) / line pieces only (the line seat's line pieces as written: on
the battlefield card by card, in other zones by count). *Success* is out
of scored trials (see S5b).
*Kill on scenario turn* is a win by the line seat on turn 9. *Executed* is
derived: 5 or more activations and triggers of line pieces in one turn, or
an extra combat on the scenario turn. *Iterations* are those activations
and triggers in the line seat's busiest turn. *Capped* games ran into the
turn cap (scenario turn + `horizon_turns`). *Wall s* sums the 20 trials'
JVM wall clocks; the arm's elapsed time is under Wall times.

| Scenario | Arm | Loaded (exact / line pieces) | Finished | Success (of scored) | 95% CI | Kill on scenario turn | Line seat won (any turn) | Turns to kill (median) | Executed | Iterations, best turn (mean / max) | Extra combats (mean) | Capped / timed out | Errors / exceptions | Wall s (sum of trials) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s1_kiki_conscripts | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 3.0 / 3 | 0.0 | 20 / 0 | 0 / 0 | 744.1 |
| s1_kiki_conscripts | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 3.0 / 3 | 0.0 | 20 / 0 | 0 / 1 | 829.5 |
| s2_derevi_emiel_cradle | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 20/20 | 10.1 / 11 | 0.0 | 20 / 0 | 0 / 0 | 812.7 |
| s2_derevi_emiel_cradle | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 20/20 | 12.0 / 12 | 0.0 | 20 / 0 | 0 / 1 | 974.0 |
| s3_druid_reconfiguration | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 1 | 722.9 |
| s3_druid_reconfiguration | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 0 | 656.9 |
| s4_magda_clock_torque | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 0.3 / 3 | 0.0 | 20 / 0 | 0 / 0 | 681.3 |
| s4_magda_clock_torque | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 0.3 / 3 | 0.0 | 20 / 0 | 0 / 0 | 660.6 |
| s5_oracle_consultation | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 0 | 691.7 |
| s5_oracle_consultation | plan | 20 / 20 of 20 | 20/20 | 20/20 | 0.84-1.00 | 20/20 | 20/20 | 0.0 | 0/20 | 1.0 / 1 | 0.0 | 0 / 0 | 0 / 0 | 557.4 |
| s5b_oracle_consultation_torpor | stock | 20 / 20 of 20 | 20/20 | 19/19 | 0.83-1.00 | 0/20 | 0/20 | – | 0/20 | 0.0 / 0 | 0.0 | 20 / 0 | 0 / 2 | 750.2 |
| s5b_oracle_consultation_torpor | plan | 20 / 20 of 20 | 20/20 | 0/19 | 0.00-0.17 | 0/20 | 0/20 | – | 0/20 | 0.0 / 0 | 0.0 | 20 / 0 | 0 / 1 | 1079.9 |
| s6_scepter_reversal | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 1 | 658.8 |
| s6_scepter_reversal | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 0 | 648.6 |
| s7_breach_brainfreeze_led | stock | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 1 | 665.5 |
| s7_breach_brainfreeze_led | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 0 | 667.5 |
| s9_magda_portal | stock | 20 / 20 of 20 | 20/20 | 20/20 | 0.84-1.00 | 0/20 | 0/20 | – | 0/20 | 2.0 / 2 | 0.0 | 20 / 0 | 0 / 0 | 604.2 |
| s9_magda_portal | plan | 20 / 20 of 20 | 20/20 | 0/20 | 0.00-0.16 | 0/20 | 0/20 | – | 0/20 | 1.0 / 1 | 0.0 | 20 / 0 | 0 / 1 | 596.6 |
| s8_kess_unmarked_grave | stock | 20 / 20 of 20 | 20/20 | 20/20 | 0.84-1.00 | 0/20 | 0/20 | – | 0/20 | 0.0 / 0 | 0.0 | 20 / 0 | 0 / 0 | 589.6 |
| s8_kess_unmarked_grave | plan | 20 / 20 of 20 | 20/20 | 20/20 | 0.84-1.00 | 0/20 | 0/20 | – | 0/20 | 0.0 / 0 | 0.0 | 20 / 0 | 0 / 0 | 561.6 |

What each row shows, from the per-arm piece counts and targets in
`suite/baseline.json` and, for zone moves, fizzles and outcome lines, the
raw logs:

- **S1 (Kiki-Jiki + Conscripts).** Both arms had Kiki copy Conscripts once
  on turn 9 (20/20) and once on turn 13 (19/20 stock, 20/20 plan); stock
  also copied Legion Warboss once, on an opponent's turn. The copy's untap
  never went to Kiki. On turn 9 it targeted Thalia, Guardian of Thraben in
  20/20 trials in both arms, and the ability fizzled each time; on turn 13
  it targeted Bartz Klauser. Stock: 0 of 39 triggers on Kiki; plan: 0 of
  40. The in-game failure is reproduced exactly.
- **S2 (Derevi + Emiel + Cradle).** Emiel blinked Derevi 67 times (stock)
  and 83 times (plan), about 3 and 4 per trial. Derevi's tap-or-untap trigger
  targeted Ragavan, Birds of Paradise, Sol Ring and other permanents, never
  Gaea's Cradle (0 of 155 triggers stock, 0 of 180 plan). *Executed* reads
  20/20 because the blink ran 5 or more times in a turn; it ran with the
  wrong target, so no mana grew.
- **S3 (Devoted Druid + Swift Reconfiguration).** Neither arm activated the
  Druid's untap (flagged `AI:RemoveDeck:All`) in any trial. The one line
  activation per trial is Walking Ballista removing its counter to ping
  Dwarven Grunt. (Mana abilities never reach the stack, so Druid's own
  mana taps are not in these counts.)
- **S4 (Magda + Clock of Omens + Liquimetal Torque).** No arm activated
  Clock of Omens or Liquimetal Torque in any trial. Magda triggered 4 times
  and searched twice across 20 trials, in both arms.
- **S5 (Thassa's Oracle + Demonic Consultation).** Stock never casts
  Consultation (0/20; it is flagged). It cast Oracle alone in 20/20 trials,
  and the games reached the cap. The plan pilot cast Consultation and Oracle
  and won on turn 9 in 20/20 trials, in a mean game of 4.1 s.
- **S5b (S5 plus an opposing Torpor Orb).** Stock passes by not casting
  Consultation (19/19 scored). The plan pilot cast Consultation in 20/20
  under the Orb and lost to its empty library in every scored trial
  (0/19). One trial per arm is unscored: Forge's setGameOver threw at the
  turn-cap kill, so Forge wrote no outcome lines (anomaly 2).
- **S6 (Isochron Scepter + Dramatic Reversal).** Scepter was never
  activated. The one line activation is again Ballista pinging Dwarven
  Grunt.
- **S7 (Breach + Brain Freeze + LED, negative control).** 0/20 in both
  arms, as expected. Stock used Breach on turn 9 (escaping Gamble 18 times
  and Snap 13) but cast Brain Freeze only in 2 trials, from hand on turn
  13, with storm 2 (3 copies at derevi). The plan pilot tried Brain Freeze
  on turn 9 in 20/20 trials (a `combo_cast`), and Forge refused it every
  time ("Couldn't add to stack, failed to target"): the plan's cast path
  picks no targets, RC1 in the repair plan (anomaly 12). It escaped Gamble
  22 times. Lion's Eye Diamond's ability is a mana ability, so whether
  anyone cracked it is not in these counts.
- **S8 (Kess + Unmarked Grave, Richard's regression).** Both arms cast
  Unmarked Grave from hand on turn 9 in every trial, then again from the
  graveyard with Kess the same turn. Stock's first pick was Blasphemous Act in
  20/20. The plan pilot's first pick was Archon of Cruelty in 20/20. That
  meets the widened success rule (a creature is a reanimation target), but
  it is 0/20 on the two cards the regression names (anomaly 7).
- **S9 (Magda + Portal to Phyrexia, the Magda regression).** Stock fetched
  Portal to Phyrexia in 20/20. The plan pilot fetched Battered Golem in
  20/20, the same miss the games showed.

Tutor picks, the first library-to-graveyard (S8) or library-to-battlefield
(S9) move on the scenario turn:

| Scenario | Arm | First move per trial (the pick) | Named cards (strict) |
|---|---|---|---|
| s9_magda_portal | stock | Portal to Phyrexia x20 | 20/20 |
| s9_magda_portal | plan | Battered Golem x20 | 0/20 |
| s8_kess_unmarked_grave | stock | Blasphemous Act x20 | 20/20 |
| s8_kess_unmarked_grave | plan | Archon of Cruelty x20 | 0/20 |

## C1, the positive control

20 real stock-game boards (pod 2iA_Jt0d6sM, runs 015 and 016), each at the
end of the precombat main phase on Godo's turn with Helm of the Host on
Godo, drawn with a fixed seed before any trial ran (`suite/c1/make_c1.py`,
`suite/c1/sources.json`). Success is a Godo win within 8 turns; the source
game's own outcome is the comparison.

| C1 | Arm | Loaded (exact / line pieces) | Finished | Won within 8 turns (success) | Won on the scenario turn | Executed | In game, same boards: won within 8 turns / same turn / ever | Agreement with the game (within 8) | Errors / exceptions | Wall s (sum) |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | stock | 10 / 20 of 20 | 20/20 | 10/20 | 4/20 | 15/20 | 10 / 5 / 14 of 20 | 18/20 | 0 / 0 | 1724.6 |
| C1 | plan | 10 / 20 of 20 | 20/20 | 11/20 | 3/20 | 17/20 | 10 / 5 / 14 of 20 | 15/20 | 0 / 0 | 1904.8 |

| Board | Turn | In game: won within 8 / same turn (end turn) | stock: success / turns to kill / extra combats | plan: success / turns to kill / extra combats |
|---|---|---|---|---|
| c1_015_default_r0_g00 | 25 | yes / yes (25) | yes / 0 / 21 | yes / 0 / 20 |
| c1_015_default_r0_g10 | 27 | no / no (36) | no / – / 1 | no / – / 1 |
| c1_015_default_r0_g14 | 19 | yes / yes (19) | no / – / 0 | no / – / 0 |
| c1_015_default_r0_g15 | 32 | yes / yes (32) | yes / 0 / 13 | yes / 0 / 14 |
| c1_015_default_r2_g04 | 58 | yes / no (60) | yes / 2 / 1 | yes / 2 / 1 |
| c1_015_default_r2_g06 | 45 | no / no (46) | no / – / 0 | no / – / 0 |
| c1_015_default_r2_g08 | 49 | yes / yes (49) | yes / 0 / 9 | yes / 3 / 5 |
| c1_015_default_r2_g13 | 54 | no / no (57) | no / – / 0 | no / – / 0 |
| c1_015_default_r3_g06 | 16 | yes / no (19) | yes / 2 / 12 | yes / 2 / 13 |
| c1_015_default_r3_g08 | 24 | no / no (38) | no / 10 / 1 | yes / 4 / 1 |
| c1_016_engine_r0_g06 | 21 | no / no (32) | yes / 8 / 1 | yes / 4 / 2 |
| c1_016_engine_r0_g09 | 24 | no / no (36) | no / – / 0 | no / – / 0 |
| c1_016_engine_r0_g12 | 40 | yes / no (43) | yes / 3 / 2 | no / – / 3 |
| c1_016_engine_r0_g15 | 29 | no / no (35) | no / – / 0 | no / – / 0 |
| c1_016_engine_r2_g00 | 26 | yes / no (31) | yes / 7 / 3 | yes / 4 / 5 |
| c1_016_engine_r2_g02 | 25 | yes / yes (25) | yes / 0 / 19 | yes / 0 / 19 |
| c1_016_engine_r2_g03 | 35 | no / no (53) | no / – / 1 | no / – / 1 |
| c1_016_engine_r2_g12 | 35 | no / no (52) | no / – / 0 | no / – / 0 |
| c1_016_engine_r3_g01 | 33 | yes / no (40) | yes / 6 / 2 | yes / 7 / 2 |
| c1_016_engine_r3_g11 | 32 | no / no (42) | no / – / 0 | yes / 8 / 0 |

- Stock disagrees with its source game on 2 boards. In r0_g14 the game won
  within 8 turns and the harness did not: an opponent exiled Godo with
  Swords to Plowshares before combat, which did not happen in the game (the
  seeded board gives every seat a fresh priority window in the main
  phase). In 016_r0_g06 the harness won in 8 turns and the game took 11.
  (On the pre-fix boards 016_r3_g01 was a third disagreement: 2 extra
  combats and no win in trial 0; on the regenerated board stock won it in
  6 turns.)
- Of the 5 boards the game won on the attach turn (10 to 22 combats), stock
  converted 4 the same way, on the scenario turn with 9 to 21 extra combats;
  the fifth is r0_g14. Of the 5 the game won 2 to 7 turns later, stock won
  all 5, also 2 to 7 turns after the scenario turn.
- On 015_r3_g08 stock won in 10 turns, 2 past the 8-turn window, so it is
  scored a loss; in the game Godo never won (it ended on turn 38).
- 10 boards load with differences off the line, the same 10 in both arms,
  because Forge runs enter-the-battlefield replacement effects while
  GameState places the board. Mox Diamond is on 8 of them: it goes to the
  graveyard, or its seat discards a land from hand to keep it. A clone died
  after re-picking what to copy on 3 (Phyrexian Metamorph twice, Clever
  Impersonator once; Cursed Mirror loaded on all 5 of its boards). An
  untransformed Invasion of Ikoria, a battle, left the battlefield on 1.
  None of them is Godo or Helm, and 20/20 boards seed the line exactly. The
  state format has no way to skip replacements: by the source, Forge's
  `NoETBTrigs` option still sends the card through `moveToPlay`, which runs
  them. So this stays a known limit of seeded real boards.
- Before the fix in `02a91bf`, 2 of the 20 boards did not load at all
  (anomaly 5). The pre-fix stock C1 run read 8/20; the table above is the
  rerun on the fixed boards.

**Supplement: 5 stock trials per board** (seeds 2026101400..04, the fixed
boards and the same jar; trial 0 is the run above, trials 1 to 4 ran after
it, 909 s at 8 JVMs, commit `27e5d90`, and the review re-ran all 5 trials
of the 3 regenerated boards; not part of the fixed acceptance, which is
the 20-trial row):

| | Trials | Won within 8 turns | 95% CI | Won on the scenario turn | Loaded (exact / line pieces) | Errors / exceptions |
|---|---|---|---|---|---|---|
| All 20 boards | 100 | 48 | 0.39-0.58 | 20 | 50 / 100 | 0 / 0 |
| The 10 boards the game won within 8 turns | 50 | 43 | | | | |
| The 10 boards it did not | 50 | 5 | | | | |

Per board, the harness is consistent with itself. The 4 boards it
converted on the scenario turn did so 5/5 each, and 5 more boards went
5/5 or 4/5 within 8 turns. Seven boards went 0/5,
and all 7 but r0_g14 were also losses in the game. **r0_g14 is the one
systematic difference found:** in 5/5 trials derevi exiles Godo with
Swords to Plowshares in the precombat main phase. In the game derevi never
cast Swords at all, and Godo won on that turn. The seeded board starts
every seat at the top of the main phase with that Swords in hand and white
mana open. Whatever held Forge's AI back in the game, which this harness
cannot see, is gone. (The review checked that this is not the
entered-tapped gap of anomaly 14: board_from_game finds no such card on
r0_g14, and the review's 10 trials also went 0/10.)

## Wall times

| Arm | Suite (S1 to S7, S9; 180 trials) | S8 (20) | C1 (20) | One arm, total |
|---|---|---|---|---|
| stock | 801.5 s | 82.7 s | 389.9 s | **1,274.1 s (21.2 min)** |
| plan | 848.2 s | 80.3 s | 512.3 s | **1,440.8 s (24.0 min)** |

Elapsed per invocation at 8 JVMs, from the driver (the runner's own
`wall_s` in each run.json agrees to within 5 s). Each arm is 220 trials. The
mean trial takes 28 to 54 s per S scenario, 90 s (stock) and 99 s (plan) on
C1, whose boards play a real game for up to 8 turns. One C1 board
(r2_g06, a turn-capped game with 1 combat) took 389 s stock and 512 s plan
by itself, which sets C1's elapsed time. The harness agent estimated 21 min
from its smoke run; the measurement is 21.2 min (stock). These are the
original runs, on the pre-fix C1 boards (anomaly 14 changed 4 tapped
flags on 3 boards, which does not bear on timing); the review's top-up of
those 3 boards took 82 s (stock) and 68 s (plan) at 6 JVMs, and the C1
table's per-trial wall sums (1,724.6 s and 1,904.8 s) now count those 3
re-run trials in place of the originals. The review's
own stock run of S1, S2 and all 20 C1 boards at 10 trials each (220
trials, 6 JVMs) took 2,657 s.

## Anomalies and notes

1. **The turn cap overshoots by 1 to 3 turns.** The shim polls the turn
   every 2 s, so a game capped at turn 13 ends at 14 or 15, and S5b's
   (capped at 14) ends at 15 to 17. Every capped game here counts as
   `turnCapped`, and no success rule reads a turn past its `by_turn`
   deadline, so no verdict moves. Durations near the cap are wall-clock
   dependent.
2. **Forge's setGameOver threw at the turn-cap kill in 7 of 440 trials**
   (the `NullPointerException ... "replacement" is null` the shim catches
   and records). These trials count under *exceptions* but are handled.
   Such a game still ends as a turn-capped draw, but Forge writes no
   outcome lines, and the result's alive flags came back wrong: stock S5b
   trial 11 had its seat at 33 life with its library intact, flagged dead.
   `alive` success (S5b) now reads Forge's own "has won / has lost" lines
   and leaves such a trial unscored (commit `c775175`). That leaves 1 trial
   per arm unscored on S5b. The other 5 are in win- or zone-scored
   scenarios, whose scoring does not read the alive flags.
3. **Stock S5b trial 9: `StackOverflowError` inside Forge's AI**
   (`ManaAi.doManaRitualLogic`, `CharmAi.chooseOptionsAi` and
   `CopySpellAbilityAi.checkApiLogic` recursing into each other). Forge's
   `AiController.chooseSpellAbilityToPlayFromList` evaluates candidates on
   a `FutureTask` and caught it there; the game played on and finished as a
   normal turn-capped draw with outcome lines. It is a stock Forge AI bug,
   not the harness.
4. **Plan S2 trial 16 printed a bare `java.util.concurrent.TimeoutException`**
   with no stack trace, from inside the JVM and not from the shim's poll loop.
   The game finished normally (turn-capped). This is noise, counted as an
   exception.
5. **A seat at life 0 crashed GameState on 2 C1 boards** (`applied:false`,
   `IndexOutOfBoundsException: Index 3 out of bounds for length 3`). Forge
   sets a life of 0 before its state-based check, which removes the seat,
   then re-sets life by index over the shortened player list. Negative life
   is set after that check, and seats seeded at -1, -2 and -3 loaded and lost
   at the first check. Fixed in `02a91bf`: `board_from_game.py` writes an
   already-lost seat at -1 with a note, and the writer refuses life 0 with
   the reason. `make_c1.py` regenerated all 20 boards, and only those two
   changed. Stock C1 was then rerun in full; the plan arm ran on the fixed
   boards from the start.
6. **C1's off-line load differences** are the ETB replacements above. The
   report now shows both counts (`line_loaded`, commit `27e5d90`), so a
   board whose line did not seed cannot hide among them.
7. **S8's success rule was widened after a 2-trial probe**, before the
   20-trial runs. It was first "Blasphemous Act or Hullbreaker Horror". A
   plan-arm probe binned Archon of Cruelty, so the rule became "any instant,
   sorcery or creature" (usable from the graveyard with Kess or by
   reanimation). The scenario's notes say so. Both readings are reported:
   plan 20/20 widened, **0/20 strict**. It never binned Sol Ring, the
   original failure, but it never took either named card either. Stock:
   20/20 on both readings.
8. **Placed cards the decks do not list.** Walking Ballista (S2, S3, S6) and
   Isochron Scepter (S6) are placed as the plan's outlets, with a writer
   warning. The plan arm's plan data does not know them, so the plan
   pilot's S2, S3 and S6 rows test Forge's own handling of those cards.
9. **The scenario turn is reproducible under stock; whole games are not.**
   The interrupted earlier run (commit `04f4d00`, same jar, same scenario
   files byte for byte) played S1 and S2 from the same seeds. In all 38
   paired trials, the success and the turn-9 play match the final run: the
   first log difference always falls after turn 9, so every turn-9 action
   and target is the same. The final turn count moves by the cap overshoot
   in 3 of them. Whole logs were byte-identical in 2/20 (S1) and 2/18 (S2).
   This agrees with SPIKE.md's determinism measurements. The review's
   re-run (seeds k = 0..9, same jar) repeated it: the scenario turn's log
   entries were identical to this run's in 10/10 paired trials of S1 and
   10/10 of S2, whole logs in 1/10 and 2/10. On C1 the review's trials at
   seeds 0..4 matched the supplement trial for trial, success and
   kill-on-turn, in 100/100 on the pre-fix boards and 14/15 on the 3
   regenerated ones, so a C1 game is reproducible in outcome most of the
   time but not always.
10. **Plan pilot in extra combats.** The plan seat's attack guard hands
    every combat after the first back to Forge (`attack_reask`; combat work
    is frozen until G4, owner decision 1). So the plan arm's C1 row is
    mostly Forge's attack logic too.
11. **ms per decision** is not exposed by shim 0.17.1. The report carries
    game ms (for example S5 plan 4.1 s, S2 plan 30.2 s per game) and ms per
    turn. The E1 prototype adds the per-decision figure G1 needs.
12. **The plan pilot's combo cast cannot target.** In S7 it cast Brain
    Freeze as a combo piece (`combo_cast`, "2/3 online") in 20/20 trials,
    and Forge refused the spell every time because no target was chosen.
    That is RC1 ("the shim casts only spells from hand and chooses no
    targets"), seen here on a targeted spell. The E1 prototype's generic
    path sets targets through `canTarget`; S7 will show whether it does.
13. **Richard's decks are read as normalised copies.** Richard's Stella
    Lee list writes two double-faced cards as "A / B" (Primal Amulet,
    Riverglide Pathway), which Forge does not load; in the probe that
    seat's library read back two cards short and the board check failed.
    S8 therefore reads a scratch copy of the four decks
    (`$SIMLAB_PRIVATE/dck`) with those two lines at their front faces, as
    WS4's normalisation will write them. The S8 plans were built from those
    copies, so they are not byte-identical to G0a's Richard plans. Nothing
    of the decks is committed.
14. **Three C1 boards had a tapped shock land written untapped (found in
    review, fixed in `3126e7e`).** Forge puts a card that enters tapped
    into play with `Card.setTapped`, which fires no tap event, so the
    shim's tap stream never says so and `board_from_game.py` wrote such a
    card untapped. In C1's source games that was 4 unpaid shock lands
    still tapped at the snapshot, all opponents': 015_r3_g08 (rograkh's
    Watery Grave, derevi's Hallowed Fountain), 016_r0_g06 (derevi's
    Breeding Pool), 016_r3_g01 (rograkh's Steam Vents). The board check
    could not catch it, because it compares Forge's loaded board with the
    file, not the file with the game, and the state's tapped flag
    overrides "enters tapped" on load. `board_from_game.py` now reads a
    card as tapped when its next record is an untap; `make_c1.py`
    reproduced the 20 boards byte for byte before the fix and changed
    exactly these 3 after it, each noting the card. The 3 boards were
    re-run in every C1 run here. Effect: stock trial 0 went from 9/20 to
    10/20 (016_r3_g01 now wins in 6 turns) and agreement with the games
    from 17/20 to 18/20; the plan row stayed 11/20 (3/20 on the turn, was
    4/20); the supplement went from 49/100 to 48/100; over the review's 10
    trials per board the 3 boards read 16/30 before the fix and 16/30
    after it.
15. **Harness fixes in review that did not move a number here.** The
    runner now re-runs a cached trial whose state file changed (stale),
    marks such trials in reports, and compile_baseline refuses them (all
    560 committed trials matched their state files); `line_loaded` now
    checks the line pieces in every zone, not only the battlefield (it
    read true for lines held in hand without checking them; every count
    above is unchanged); `run.json` keeps every invocation into one
    directory. `suite/baseline.json` was rebuilt from the raw logs with
    this code and differs from the previous one only in the C1 rows of
    anomaly 14 and the added provenance.

## Review re-run (stock, 10 trials each)

The review re-ran S1, S2 and all 20 C1 boards under stock on the same jar,
seeds 2026101400..09 (k = 0..4 repeat the runs above, 5..9 are new), 6
JVMs, 220 trials in 2,657 s, then the 3 regenerated boards again (30
trials, the runner picking them as stale). Raw output:
`<scratch>/harness_review/runs/stock10/`.

| Scenario | Trials | Success | 95% CI | Kill on scenario turn | Loaded (exact / line pieces) | Errors / exceptions |
|---|---|---|---|---|---|---|
| s1_kiki_conscripts | 10 | 0 | 0.00-0.28 | 0 | 10 / 10 | 0 / 0 |
| s2_derevi_emiel_cradle | 10 | 0 | 0.00-0.28 | 0 | 10 / 10 | 0 / 0 |
| C1, 20 boards | 200 | 97 | 0.42-0.55 | 40 | 100 / 200 | 0 / 1 |
| C1, seeds 0..4 | 100 | 49 | 0.39-0.59 | | | |
| C1, seeds 5..9 (new) | 100 | 48 | 0.39-0.58 | | | |
| C1, the 10 boards the game won within 8 turns | 100 | 85 | | | | |
| C1, the 10 boards it did not | 100 | 12 | | | | |

S1: Kiki copied Conscripts once on turn 9 in 10/10 trials and once on
turn 13 in 9/10 (plus Legion Warboss once, on turn 14); the copy's untap
targeted Thalia on turn 9 (10) and Bartz Klauser on turn 13 (9), never
Kiki, as in the 20-trial run.
S2: Derevi's trigger resolved 74 times, never on Gaea's Cradle. Both
reproduce the 20-trial rows within noise, and C1's 97/200 agrees with
the 20-trial row (10/20) and the supplement (48/100). Per board the 10
trials rank the boards as the supplement does: the 4 boards converted on
the scenario turn went 10/10 each, r0_g14 went 0/10.

## What this gives G1 (Fri 10/23)

G1 compares the E1 prototype against stock on S1, S2, S3, S4 and S6 with
"stock at most 2/20 on the same scenarios, and C1 not broken". This
baseline has stock at 0/20 on all five. For "not broken", C1's stock
reference is 10/20 won within 8 turns, 4/20 on the scenario turn and 15/20
executed (an extra combat, or 5 or more line triggers in a turn), on these
seeds and boards; over 5 trials per board it is 48/100 (20/100 on the
scenario turn) and over 10, 97/200 (40/200). Rerun the stock arm on the
same jar and seeds for a paired comparison, and don't compare against the
plan's 17/20.
