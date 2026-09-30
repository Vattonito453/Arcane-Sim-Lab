# E1: the combo-executor prototype (repair plan WS9 Phase A)

Repair plan `tasks/25-repair-plan.md`, WS9 "Phase A: prototype E1", for the
G1 go/no-go (Fri 10/23). A thin step interpreter in the public GPL shim
(`simlab-forge-shim`, branch `exec-proto`, 0.18.0-proto) runs hand-written,
data-named combo steps on the seeded-board suite (WS3), and this directory
holds the step data, the runner's exec arm and the development results.
The gate itself (fresh seeds, pre-registered) is the gate agent's; nothing
in this README was run on a seed outside the DEV range 2026200000-2026200999.

**G1 result:** GO under the pre-registered primary reading, PARTIAL if S1
is read by kills only; see `PREREG.md` (the rules, fixed before any gate
game), `RESULTS.md` (the gate's figures) and `g1_summary.json` (the
reader's output). `run_g1.py` and `read_g1.py` reproduce it. An
independent review confirmed the reading, reproduced it on fresh seeds
and corrected the S1 attack split (`RESULTS.md`, "Independent review").

**Development result, in short** (20 trials per arm, DEV seeds
2026200000-019, jar `88e7564`, step files at `e28eeb2`; the gate's own
figures will come from fresh seeds). Stock converts none of the five
scenarios (0/20 each). With the step data:

- **S3** (Devoted Druid, a flagged activation) and **S6** (Isochron
  Scepter and Dramatic Reversal, a mana loop into an X outlet): 20/20
  kills on the scenario turn each.
- **S4** (Magda, Clock of Omens, Liquimetal Torque, then Grinding
  Station): 20/20 wins by turn 12 (the harness's rule; the opponents deck
  out on their draws). Every S4 trial takes 9 to 14 minutes of wall
  clock, all of it Forge's, on a 780 s per-turn budget; under the 600 s
  budget the run began with, 3 of these 20 lines would have been cut
  short. See "S4's wall time" below.
- **S1** (Kiki-Jiki and Zealous Conscripts, a trigger target): the stated
  state then the outlet 20/20 (44 hasty copies bound to untap Kiki, then
  the attack handed to the pilot), but 0/20 kills on the scenario turn:
  the pilot's attack kills two of the three opponents and the seat wins
  on its next turn (turn 11) in 20/20.
- **S2** (Derevi, Emiel, Gaea's Cradle): 0/20. The Derevi trigger's target
  is bound to the tapped Cradle every time, but Forge's
  `PlayerControllerAi.chooseBinary` then answers "tap or untap?" with tap,
  a constant, so the loop cannot run inside decision 4's API list. The
  evidence branch `exec-proto-binary` (one more override) makes it 20/20.
- 0 aborts and 0 unhandled exceptions in 100 exec trials; the executor's
  own decision time has a median of 0.436 ms over 60,760 decisions (p95
  2.0 ms, max 122 ms).

Against G1's wording, that is 16/20 or better on four of the five (S1
through "the stated infinite state followed by the outlet", S3, S4, S6)
with stock at 0/20, which is the shape of a GO on dev seeds, but S1 is
not a kill and S2 fails outright. Under 2-core affinity the executor's
median decision is 0.400 ms (limit 2 s), and C1 reads stock 10/20 and
the plan pilot on this jar 9/20 with no executor record (week 3: 10/20
and 11/20), so C1 is not broken. Details below.

## What was built

**Shim** (`exec-proto`, public repo, not pushed): `StepRunner.java` plus
three hooks in `PlanPlayerController`. The shim README's section "Combo
executor prototype, 0.18.0-proto" is the reference; in short:

1. **Generic data-named path.** In `chooseSpellAbilityToPlay`, an armed
   line returns the data-named SpellAbility (a spell from any zone, an
   activation, flagged or not, or a mana ability to float mana) after
   `sa.canPlay()` and `ComputerUtilCost.canPayCost`, with its target set
   through `sa.canTarget`. Forge's `PhaseHandler` plays it through the stock
   `playChosenSpellAbility`, so Forge pays the costs and resolves it. This
   is the path WS6's readmission reuses.
2. **Trigger targets.** An `orderAndPlaySimultaneousSa` override binds the
   target of a trigger whose host the armed line's data names, then puts it
   on the stack with `ComputerUtil.playStack`, after `super` has handled
   every other trigger. Anything else, and any mismatch, is `super`'s.
3. **Stop.** Loops stop on `count`, `power_vs_life`, `opponents_out`,
   `mana_at_least` or `no_progress`, on `max`, or when the line's per-turn
   wall budget (`budget_ms`) runs out; `confirmTrigger` declines an
   optional loop trigger marked `"stop": true` once its loop's predicate
   holds, and answers the line's other named optional triggers.
4. **Payoff and fallback.** The outlet is a step like any other (Walking
   Ballista's pings, Magda's search) or a `pass` that hands the turn to the
   pilot (a combat finish). Any exception or unmet precondition ends the
   line with `exec_abort` and the reason, and the seat plays on as the
   0.17.1 plan pilot.

Records: `exec_arm`, `exec_step`, `exec_stop`, `exec_abort`, each with
`ms=` (the executor's own wall time for that decision) and `at=` (ms since
the line armed).

**Java diff: 395 lines**, under G1's cap of 400. Counted as the gate
words it (added plus changed) with `git diff --numstat
origin/shim-0.17.1-scenario..exec-proto -- '*.java'` against
`shim-0.17.1-scenario` at 13eeed7: 395 added, 1 removed. The removed line
is the version string, whose replacement is one of the 395, so a changed
line counts once; the strictest reading, added plus removed, is 396. By
file: `StepRunner.java` 355 (new), `PlanPlayerController.java` +30,
`DeckPlan.java` +5, `SimShim.java` +5/-1. Without blank and comment
lines the diff is 335. Decision 4's own limit (600 lines for the
`orderAndPlaySimultaneousSa` override and the helpers only it uses): the
override is 20 lines with its comment, and its helpers in `StepRunner`
(`bindTriggers` 27, `pick` 24, `bind` 11, `spec` 9) 71, so 91. The
card-name lint (`tools/lint_card_names.py`, run by `build.sh`) passes:
10 Java files against 35,069 Forge card names.

**Here:** `steps/` (the five hand-written step files the plan calls for),
`steps_binary/` (S2 for the evidence branch, below), the exec arm in
`studies/scenarios/run_scenarios.py`, and `tests/test_exec_arm.py`.

## The step format (`simlab-steps/1`)

One file per scenario, `steps/<scenario id>.json`. The shim reads only
`lines`; the other fields are the runner's.

```json
{
  "format": "simlab-steps/1",
  "scenario": "s3_druid_reconfiguration",
  "deck": "tymna_thrasios",
  "state": "What the stated infinite state is, in a sentence.",
  "state_step": 0,
  "outlet_step": 2,
  "plan_patch": {"search": {"targets": {"Grinding Station": 9}}},
  "lines": [
    {
      "id": "druid_ballista",
      "pieces": {"Devoted Druid": "Battlefield", "Walking Ballista": "Battlefield"},
      "budget_ms": 240000,
      "triggers": [
        {"card": "Derevi, Empyrial Tactician", "target": {"card": "Gaea's Cradle", "tapped": true}},
        {"card": "Emiel the Blessed", "confirm": false}
      ],
      "steps": [
        {"loop": [{"op": "activate", "card": "Devoted Druid", "api": "Mana"},
                  {"op": "activate", "card": "Devoted Druid", "api": "Untap"}],
         "until": {"mana_at_least": 476}, "max": 600},
        {"op": "activate", "card": "Walking Ballista", "api": "PutCounter", "max": 200},
        {"op": "activate", "card": "Walking Ballista", "api": "DealDamage",
         "target": {"player": "opponent", "policy": "lowest_life"},
         "until": {"opponents_out": true}, "max": 200}
      ]
    }
  ]
}
```

- `deck`: the line seat's deck name (the plans file key). `plan_patch`
  (optional) is deep-merged into that deck's plan for the exec arm; S4 uses
  it to value Grinding Station for the plan pilot's existing search
  steering (0.5.0), because no step op picks a search result.
- `state_step` / `outlet_step`: the step whose loop is the stated infinite
  state and the step that is the outlet. The report scores "state then
  outlet" from them (below).
- `lines[].pieces`: card name to zone (`Battlefield`, `Hand`, `Graveyard`,
  `Exile`, `Command`, `Library`); the line arms on the seat's own turn, in a
  main phase, on an empty stack, once per turn, when every piece is there.
- `lines[].triggers`: per host card, `target` (bind the trigger's target
  when it goes on the stack), `confirm` (answer its "you may"; default yes),
  `stop` (decline it once the current loop's predicate holds).
- `lines[].steps`: an action or a loop. Actions: `op` `activate` (default)
  | `cast` | `pass`; `card`; `zone` (`Battlefield` for activate, `Hand` for
  cast by default); `api` (Forge's ApiType name, picks the ability);
  `target`: `{"card": name}` (own permanent), `{"card": name, "tapped":
  true}`, `{"player": "self"}`, `{"player": "opponent", "policy": "first" |
  "lowest_life" | "largest_library"}`. A loop: `{"loop": [actions], "until":
  {predicate: value}, "max": N}`; an action with `until` or `max` is a
  one-action loop. Predicates: `count` (passes), `power_vs_life` (margin:
  untapped creature power over the living opponents' total life),
  `opponents_out` (true), `mana_at_least` (the pool), `no_progress` (`{"of":
  "mana" | "opp_life" | "opp_library" | "power" | "permanents", "after":
  k}`). A loop whose first action cannot be played after at least one full
  pass has run out (`exhausted`): the next step starts. Anywhere else an
  action that cannot be played aborts the line.

How this maps onto Phase B's closed vocabulary: `cast` with `zone` is
`cast` / `cast_from(zone)`; `activate`; a trigger `target` is
`resolve_trigger` with its bind; `confirm: true` / `false` are
`confirm_repeat` / `decline_trigger`; `pass` is `hand_off_attack`. Binds:
`{"card"}` is `own_piece`, `{"card", "tapped": true}` `own_piece_tapped`,
`{"player": "self"}` `self_player`, `{"player": "opponent", "policy"}`
`opponent(policy)`. Not built (no prototype scenario needs them):
`name_card` (`chooseCardName`) and `any_legal`.

The runner validates every step file before a run (`validate_steps`).

## The exec arm

`run_scenarios.py` has an arm `exec`: the plan arm (every seat
`plan:SimLabHuman`, version-2 plans, every fix flag on) plus the scenario's
step file merged into its line deck's plan as `"steps": {"lines": [...]}`.
The other seats keep their plans unchanged. A scenario with no step file
(C1) runs the exec arm with no steps, which is the plan arm on the new jar.

```bash
py studies/scenarios/run_scenarios.py studies/scenarios/suite/s{1_kiki_conscripts,2_derevi_emiel_cradle,3_druid_reconfiguration,4_magda_clock_torque,6_scepter_reversal}.json \
    --jar <scratch>/e1/shim-0.18.0-proto-<sha>.jar --out <out> --arms stock,exec \
    --trials 20 --parallel 8 --seed <SEED> --data-dir <scratch>/g0a/cache_cedh
#   --steps DIR               step files (default studies/e1_executor/steps)
#   --jvm-arg=-XX:ActiveProcessorCount=2 --affinity 3,C,30,C0   2-core timing (below)
py studies/scenarios/run_scenarios.py --report-only --out <out>
```

New runner flags: `--steps DIR`; `--jvm-arg OPT` (repeatable, passed to
every JVM); `--affinity MASKS` (comma list of hex CPU masks; worker slot i
pins its JVM to mask i mod n with Windows processor affinity, set right
after the JVM starts). A cached trial is now also re-run when its plans
file changed (the shim header's `plansSha256`), so an edited step file
never reuses an old game.

What the report adds for an arm with executor records (`report.md`, an
"Executor (E1)" table under each scenario; `report.json`, `summary.exec`
and each trial's `exec`):

- **Armed**: trials whose line armed.
- **State**: the state step's loop stopped on one of its own predicates
  (`count`, `power_vs_life`, `opponents_out`, `mana_at_least`,
  `no_progress`); stopping on `max`, the budget or exhaustion is not the
  stated state.
- **Outlet**: the outlet step issued an action, or, for a `pass` outlet,
  the line seat declared attackers on the scenario turn after the hand-off.
- **State then outlet**: both, with a Wilson interval. This is the second
  half of G1's "16/20 kills (or the stated infinite state followed by the
  outlet)"; the first half is the harness's own `success` column, scored by
  each scenario's unchanged success rule.
- Aborts with reasons, stop reasons, actions per trial, the number of
  executor decisions and their ms (median / p95 / max), and **unhandled**
  (the JVM exited non-zero, the shim died, or the game ended as an errored
  result) beside the raw count of printed exception lines, most of which
  are Forge's own caught exceptions.

`ms_per_decision` (per trial and per arm), null since 0.17.1, is now the
median executor decision time where executor records exist.

## Development results (DEV seeds only)

**The run.** S1, S2, S3, S4 and S6, arms `stock` and `exec`, 20 trials
each, seeds 2026200000-019 (trial k shares its seed and library shuffle
across arms), jar `shim-0.18.0-proto-88e7564.jar` (sha256
`3795f534d24093f98e629f63553d19bab3d24b555295a24f688f3c84d69a0a0a`,
class-identical to a fresh `build.sh` of `exec-proto` at 88e7564), step
files as committed at `e28eeb2`, plans from `--data-dir
<scratch>/g0a/cache_cedh`, the harness's 900 s game clock and 8-turn
horizon. It ran in three invocations into one `--out` (run.json keeps
all three): the first (8 JVMs) was cut off by a usage limit during S4's
exec trials; a resume at 7 JVMs was stopped after five minutes, before
any trial finished, to change S4's budget (below); the third, at 7 JVMs
beside one profiled S4 trial, ran the rest. The runner reuses a finished trial
only when its state file and plans file hashes match, so every S4 exec
trial was re-run on the final step file and S6 ran for the first time;
the 140 reused trials (S1 to S3 both arms, S4 stock) are on the same jar
and the same plans bytes as now.

| Scenario | Stock success | Exec success | Exec kill on the scenario turn | State | Outlet | State then outlet (95% CI) | Aborts | Timed out (stock / exec) | Game s, exec (mean / max) |
|---|---|---|---|---|---|---|---|---|---|
| S1 kiki_conscripts | 0/20 | 0/20 | 0/20 | 20 | 20 | 20/20 (0.84-1.00) | 0 | 0 / 0 | 30.1 / 34.1 |
| S2 derevi_emiel_cradle | 0/20 | 0/20 | 0/20 | 0 | 20 | 0/20 (0.00-0.16) | 0 | 0 / 0 | 20.3 / 28.3 |
| S3 druid_reconfiguration | 0/20 | 20/20 | 20/20 | 20 | 20 | 20/20 (0.84-1.00) | 0 | 0 / 0 | 55.0 / 83.9 |
| S4 magda_clock_torque | 0/20 | 20/20 (by turn 12) | 0/20 (not its rule) | 20 | 20 | 20/20 (0.84-1.00) | 0 | 0 / 0 | 653.6 / 800.2 |
| S6 scepter_reversal | 0/20 | 20/20 | 20/20 | 20 | 20 | 20/20 (0.84-1.00) | 0 | 0 / 0 | 44.2 / 50.5 |

| Scenario | Stops (all trials) | Actions per trial (mean) | Executor decisions | Decision ms (median / p95 / max) | Unhandled / printed exception lines (stock; exec) |
|---|---|---|---|---|---|
| S1 | handoff x40; power_vs_life x40 | 60.0 | 2,520 | 0.281 / 1.845 / 29.901 | 0 / 1; 0 / 578 |
| S2 | done x20; exhausted x60 | 7.0 | 300 | 0.706 / 46.155 / 122.463 | 0 / 0; 0 / 1 |
| S3 | exhausted x20; mana_at_least x20 | 1,192.0 | 23,900 | 0.349 / 1.164 / 30.996 | 0 / 1; 0 / 0 |
| S4 | count x40; hold x20; no_progress x20; turn-or-phase-ended x20 | 213.0 | 10,120 | 0.045 / 10.381 / 58.065 | 0 / 0; 0 / 0 |
| S6 | exhausted x20; mana_at_least x20 | 1,193.0 | 23,920 | 0.475 / 0.965 / 29.13 | 0 / 0; 0 / 0 |

Pooled over the five exec arms: 60,760 executor decisions, **median
0.436 ms**, p95 2.025 ms, max 122.463 ms (8 JVMs on the dev box, no CPU
pinning). Stock seats played every stock trial to the 8-turn horizon
without a win (draws x20, capped x20 in each stock row).

What happened, scenario by scenario:

- **S1.** Every trial: the line arms on turn 9, Kiki-Jiki copies Zealous
  Conscripts 44 times, every copy's enter trigger is bound to Kiki-Jiki
  (44 `op=bind` records, 0 mismatches), and the loop stops on
  `power_vs_life` (untapped power at least the opponents' 120 life plus
  15). The `pass` outlet hands combat to the 0.17.1 pilot. Forge's
  `AiAttackController` in assault mode sends every attacker at one
  defender (read from Forge's source, not observed apart from the split
  that follows), then the plan's split pass (`splitAttacks`) moves 15 of
  them onto a second opponent: the declaration was 31 attackers (Zealous
  Conscripts) at one opponent and 15 (Kiki-Jiki and 14 Conscripts) at
  another, 46 in all, in 20 of 20 trials, and the third opponent was never
  attacked. (An earlier count read 33 and 17: it counted the `Ai(1)` and
  `Ai(2)` seat prefixes as instance ids, the trap CLAUDE.md gotcha 5
  names; corrected in the review, `RESULTS.md`.) Two opponents die on
  turn 9; the line arms again on
  turn 11 and the seat wins then, 20 of 20. So S1 is 0/20 by its success
  rule and 20/20 on "the stated infinite state followed by the outlet".
  No data can fix the split: attack distribution is not an executor
  operation (Phase B's `hand_off_attack` is the same hand-off), and the
  split pass only ever moves a third of the attackers to one other
  opponent. The 578 printed exception lines are 289
  `ConcurrentModificationException`s thrown inside Forge's parallel
  must-attack futures (`AiAttackController.declareAttackers`) with 46
  attackers; Forge catches them and the games finish normally.
- **S2.** The Derevi trigger is bound to the tapped Gaea's Cradle in
  every trial (`op=bind ... target=Gaea's Cradle`), Emiel's "you may"
  trigger is declined as the data says, and then Derevi's effect asks
  its controller "tap or untap?": `PlayerControllerAi.chooseBinary`
  answers tap, always. The Cradle stays tapped, the mana loop is
  `exhausted` after one pass (`canPlay Gaea's Cradle`), the Ballista
  steps spend what little mana there is, and the line ends `done`.
  Evidence branch, same seeds: 20/20 (below).
- **S3.** Devoted Druid's untap, which Forge's AI never plays
  (`AI:RemoveDeck:All`), runs 476 times per trial through the generic
  path; the mana loop stops on `mana_at_least` (476), the Ballista
  counter loop spends the pool (`exhausted`), and the pings kill all
  three opponents on the scenario turn, 20 of 20.
- **S4.** Torque, Sol Ring, 20 Clock of Omens passes (`count`), three
  Magda searches (Battered Golem, Grinding Station, Maskwood Nexus, found
  by the plan pilot's search steering with `plan_patch`), then 94 passes
  of Station and Clock until the opponents' libraries stop shrinking
  (`no_progress`), then the holding pass to the end of the turn. The
  same 213 actions and 659 stack items in every trial; 277 cards milled
  (92, 92, 93). The opponents lose drawing on turns 10 to 12; every
  trial won on turn 12.
- **S6.** The four-action loop (Sol Ring, Arcane Signet, Fellwar Stone's
  `ManaReflected`, the Scepter's copy of Dramatic Reversal) floats 476
  mana, then Ballista; 20 of 20 on the scenario turn.

### S4's wall time

An S4 exec trial takes 9 to 14 minutes of wall clock (559 to 811 s per
JVM; game 548 to 800 s, mean 654 s; 8 JVMs running), against 44 to 55 s
of game time on average for S3 and S6 and less for S1 and S2. The
executor is not where it goes:

- **The executor's own decisions** on S4 have a median of 0.045 ms (p95
  10.4 ms, max 58 ms), 10,120 decisions in 20 trials. The `ms` field
  times the executor from entering a hook to returning; Forge's
  resolution and the other seats' decisions are outside it. In 40 thread
  samples of a fresh S4 trial (`jstack` every 15 s, same seed as trial 0,
  game 612 s) `StepRunner` was on the game thread's stack in none.
- **Where the time goes.** The line puts 659 items on the stack in one
  turn (160 Magda Treasure triggers, 144 Battered Golem and 143 Grinding
  Station untap triggers, 114 Clock and 94 Station activations, 3 Magda
  searches and the Torque), and every item passes priority round the
  table. Of the 33 samples taken while the
  line ran, 25 were Forge's AI at priority
  (`AiController.getSpellAbilityToPlay` into
  `Card.getAllPossibleAbilities` for every card the seat could play,
  mostly `StaticAbilityAlternativeCost` checks that filter cards through
  `CardLists.getValidCards`), 5 were stack resolution, and one each
  state-based actions, the last-known-information copy and other. While
  the line is armed the line seat passes on its own items without asking
  Forge's AI, so those priority walks are the three opponents'. GC is not
  a factor: 4.7 s of collection in the whole 612 s game.
- **It grows as the game fills.** Time per Station pass rises from about
  1 s over the first ten passes to 12 to 14 s over the last ten (trial 5:
  0.85 s to 11.9 s; trial 13: 1.2 s to 14.4 s) as 277 cards reach the
  opponents' graveyards and Magda's Treasures accumulate (53 at the end
  of the turn). Every trial does exactly the same work, yet the line
  took 449 to 706 s: the spread follows the seed (trials 2, 4 and 5 took
  598, 593 and 459 s here and 595, 599 and 453 s in the interrupted
  first invocation), because what the opponents hold and mill sets the
  cost of each priority walk.
- **The per-turn wall budget did matter.** `budget_ms` is wall time since
  the line armed, so it includes all of the above. The step file's
  budget was 600 s when the dev run began; in the first invocation one
  line ended 0.9 s inside it, and in the final 20 three lines ran past it
  (600.4, 623.9 and 706.3 s). A budget stop there ends the line before
  its holding pass and hands the pilot a board it could not finish a
  turn on inside the clock (4 of 4 dev trials before the holding pass
  timed out). `e28eeb2` raised it to 780 s: the 900 s game clock less
  the longest measured remainder after the line (114 s; 94 to 111 s in
  the final 20) and setup. All 20 S4 exec trials above are on 780 s.
- **What is left is the game clock.** The slowest game was 800.2 s, 100 s
  inside the 900 s clock. A seed slower than any dev seed, a busier
  machine or the 2-core arm can push an S4 game past the clock, which
  the harness scores as a timeout, not a win. See "2-core timing".

This is a finding for Phase B as much as for G1: a mill of about 280
cards through 94 activations costs about 450 to 700 s of Forge's time on
this box, twice to three times a typical whole game (240 s), and none of
it can be saved by the executor, because the rules give every opponent
priority on every item.

### S2 on the evidence branch

`exec-proto-binary` at 1a6c5d1 (`shim-0.18.0-proto-binary-1a6c5d1.jar`,
sha256 `69f5ad6a5d141fdb0c84e5d3b3ba1c73abf6d0d0129f222e9e9ec3d759837c62`)
is `exec-proto` plus a `chooseBinary` override: while a line is armed, a
`triggers` entry may answer its card's binary question by Forge's
`BinaryChoiceType` (`steps_binary/s2_derevi_emiel_cradle.json` adds
`"choice": {"TapOrUntap": false}`, untap); otherwise `super`. It is 22
Java lines more (9 in `PlanPlayerController`, 13 in `StepRunner`), 417
against `shim-0.17.1-scenario`, so it breaks the 400-line cap as well as
decision 4's list. Same seeds (2026200000-019), exec only, 1 JVM: 20/20
kills on the scenario turn, the state then the outlet 20/20, 0 aborts, 0
exceptions, game 47.8 s mean, decision ms median 0.067 (p95 0.540, max
29.0) over 33,440 decisions. It is evidence for the owner that S2 fails
on one Forge constant, not on targeting; it is not the G1 jar.

### C1 on the final jar

C1 has no step file, so its exec arm is the 0.17.1 plan pilot on the
0.18.0-proto jar with no `steps` in any plan: G1's "C1 not broken" check.
The 20 real boards, `--trials 1`, seed 2026200000 (the week-3 baseline
used 2026101400), 4 JVMs pinned to CPUs 8-31 beside the timing run:

| C1 | Won within 8 turns (success) | Won on the scenario turn | Agreement with the source game | Same outcome as week 3, board by board | Unhandled / exceptions | Executor records |
|---|---|---|---|---|---|---|
| stock | 10/20 | 4/20 | 16/20 | 18/20 (stock) | 0 / 0 | – |
| exec (plan, no steps) | 9/20 | 4/20 | 17/20 | 16/20 (plan) | 0 / 0 | 0 |

The "same outcome as week 3" column is weak evidence: it pairs one trial
per board on seed 2026200000 with week 3's one trial per board on seed
2026101400, so it measures two single draws, not the jar. The paired,
same-seed comparison is G1's (`RESULTS.md`, C1: exec and `plan017`, the
same pilot on both jars, differ on 1 board of 20).

Week 3 read stock 10/20 (4/20 on the turn) and plan 11/20 (3/20). One
trial per board on a different seed moves a board or two either way
(the week-3 review's 10 trials per board read 97/200 for stock), and no
executor record appeared, so C1 is not broken by the jar. An earlier C1
run on `aa91088` (same no-steps path) read the same 10/20 and 9/20.

### 2-core timing (WS9 "Timing without Docker")

Four JVMs, each pinned with Windows processor affinity to 2 logical CPUs
(`--affinity 3,C,30,C0`, CPUs 0-7) and started with
`-XX:ActiveProcessorCount=2`, `--parallel 4`, exec arm only, 4 trials per
scenario on fresh DEV seeds 2026200100-103, jar `88e7564`, step files at
`e28eeb2`. Nothing else of this study ran on CPUs 0-7 (the C1 run was
pinned to 8-31); other agents' processes were not controlled.

| Scenario | Exec success | State then outlet | Decisions | Decision ms (median / p95 / max) | Game s | Unhandled / printed exceptions |
|---|---|---|---|---|---|---|
| S1 | 0/4 | 4/4 | 504 | 0.342 / 1.744 / 23.766 | 31-33 | 0 / 0 |
| S2 | 0/4 | 0/4 | 60 | 0.523 / 28.133 / 51.088 | 13-21 | 0 / 0 |
| S3 | 4/4 | 4/4 | 4,780 | 0.288 / 0.836 / 26.32 | 43-45 | 0 / 0 |
| S4 | 4/4 (by turn 12) | 4/4 | 2,024 | 0.039 / 10.049 / 50.55 | 543-698 | 0 / 0 |
| S6 | 4/4 | 4/4 | 4,784 | 0.461 / 0.88 / 22.58 | 39-46 | 0 / 0 |

Pooled: 12,152 decisions, **median 0.400 ms** (p95 1.734 ms, max 51.1
ms), against G1's limit of 2 s. Outcomes match the unpinned run. S4's
games (543 to 698 s) sit in the range of the unpinned run, which fits
the profile: the work is one game thread walking cards. S1 printed no
exceptions pinned (0 in 4 trials, against 289
`ConcurrentModificationException`s in 20 unpinned trials); they come
from Forge's parallel attack futures, which have fewer cores to race on
here. Four trials per scenario is a timing check, not an outcome
measurement.

### What Forge decides that the data cannot (known failure modes)

- **Binary choices.** `PlayerControllerAi.chooseBinary` answers
  `TapOrUntap` with tap, always (S2). Fixable only by an override outside
  decision 4's list (the evidence branch).
- **Combat.** A `pass` outlet hands combat to the 0.17.1 pilot: Forge's
  assault sends every attacker at one defender and the plan's split pass
  moves a third to one other opponent, so a three-opponent kill in one
  combat does not happen however large the board (S1: 44 copies,
  untapped power at least 135 against 120 life, two of three killed).
  Forge's attack code also throws, catches and prints
  `ConcurrentModificationException`s from its parallel futures with that
  many attackers.
- **Cost choices.** `AiCostDecision` pays costs and no controller method
  sees it: Clock of Omens taps the two lowest-power untapped artifacts
  and a sacrifice takes the newest Treasure. The S4 data is written to
  work with those choosers (Golem and Nexus make every Clock pass yield
  two Treasures), not around them. A line whose cost choice matters and
  cannot be arranged this way is not drivable by this prototype.
- **Search results.** No step op picks what a tutor finds; S4 relies on
  the 0.5.0 search steering, valued through `plan_patch`.
- **Forge's throughput.** Every stack item gives each opponent's AI a
  full walk of its playable cards, and that walk grows with graveyards
  and boards: S4's line costs 450 to 700 s (above).
- **Things the prototype does not exercise.** `name_card`
  (`chooseCardName`), `any_legal`, cast-from-graveyard or exile lines,
  and responses: across the 100 exec trials the only opponent stack
  items on a scenario turn were one Mother of Runes activation per S1
  trial, protecting the opponent's own Thalia; no opponent answered a
  line, so "faced a response" is untested here.

### For the gate agent

- **What to run.** The CLI above with the five S files, `--arms
  stock,exec --trials 20`, fresh seeds outside 2026200000-2026200999
  (every dev run here used seeds inside it: 2026200000-019 for the
  suite, S2's evidence run and C1; 2026200100-103 for 2-core timing;
  2026200500-501 for the no-steps check; single trials at 2026200004),
  the jar and sha256 above, `--steps` left at its default
  (`studies/e1_executor/steps`, the committed files), and
  `--data-dir <scratch>/g0a/cache_cedh` for plans identical to these.
  C1 runs the same way with `suite/c1/c1_*.json --trials 1`.
- **Budget the wall clock for S4.** The invocation that ran S4's 20 exec
  trials and S6's 40 took 2,141 s at 7 JVMs; one S4 trial takes up to 14
  minutes. Keep S4 at 8 JVMs or fewer, leave the game clock at the
  harness's 900 s (`--timeout`, as every baseline ran) unless the
  PREREG says otherwise, and check the exec rows for `timed out` and the
  exec table's stops for `budget`: either is a failure by the harness's
  rule, and a busier machine or a slower seed makes both likelier (see
  "S4's wall time"). S4's 780 s budget is step data, committed at
  `e28eeb2`; no Java changed after the jar.
- **Scoring.** The harness's `success` column is each scenario's
  unchanged rule. "State then outlet" is the second half of G1's first
  bullet: the state step's loop stopped on its own predicate, and the
  outlet step then fired (for S1's `pass` outlet: the line seat declared
  attackers on the scenario turn after the hand-off). Whether S1's
  20/20 on that column with 0/20 kills counts toward "including S1 or
  S2" is the gate's reading to pre-register; both figures are reported.
- **Exceptions.** `unhandled` counts a JVM that exited non-zero, a shim
  that died, or an errored game. The printed count also includes Forge's
  own caught exceptions (S1's CMEs, Forge's `setGameOver` throwing at the
  turn-cap kill, which the harness already handles); G1's "0 unhandled"
  is the `unhandled` column.
- **Decision time.** `ms` is the executor's own time per decision
  (median per arm and pooled in `report.json`); G1's 2 s limit is
  against that under 2-core affinity (`--affinity 3,C,30,C0
  --jvm-arg=-XX:ActiveProcessorCount=2 --parallel 4`).
- **The evidence branch** is not the G1 jar and should not be timed or
  scored as it; its S2 result is for the owner's decision on
  `chooseBinary`.

## No behaviour change without steps

A plan without `steps` builds no `StepRunner`; the three hooks then run
the 0.17.1 code (`steps == null`), and the header gains `planSteps`.
Measured with the harness method of `studies/scenarios/SPIKE.md`: no
`--scenario`, pod `2iA_Jt0d6sM` (derevi, godo_archetype, nadu,
rograkh_silas), `--games 2 --max-turns 12`, an all-plan arm on G0a's
version-2 plans (`plans_2iA_Jt0d6sM_v2.json`, no steps) and an all-stock
arm; 6 runs of 0.17.1 (`shim-0.17.1-967cb71.jar`) and 6 of 0.18.0-proto
(`aa91088`, whose no-steps path is the final jar's: the two later commits
touch only step-data code) on each of two DEV seeds, 8 JVMs (4 for the
second seed). Turns 1 to 12 compared by variant: runs sharing a letter
logged byte-identical `entry`, `zone`, `tap` and `agent` records
(`det_compare.py`), and in brackets the variants once the order in which
the same mana sources were tapped is forgiven (`det_norm.py`).

| Seed | Arm, game | 0.17.1, runs a-f | 0.18.0-proto, runs a-f |
|---|---|---|---|
| 2026200500 | stock, game 0 | A B C D E F [same] | G H I J K L [same] |
| 2026200500 | stock, game 1 | A A A A A A | A A A A A A |
| 2026200500 | plan, game 0 | A B C D B E [same] | F G H I J K [same] |
| 2026200500 | plan, game 1 | A A A A A A | A A A A A A |
| 2026200501 | stock, game 0 | A B C D E C [same] | F G H I F J [same] |
| 2026200501 | stock, game 1 | A B C B A C [A A B A A B] | A A B B A A [all A] |
| 2026200501 | plan, game 0 | A A A B C C [same] | D A D C D E [same] |
| 2026200501 | plan, game 1 | A A A A A A | B B A B A B [all A] |

- Game 1 of both arms on both seeds: with tap order forgiven, every run
  of both jars played one variant, except seed 2026200501's stock arm,
  where 2 of the 6 0.17.1 runs played a second variant.
- Game 0 splits in most runs on each jar by itself, so a variant count
  cannot separate the jars there. Where does each pair of runs first
  differ in Forge's log (`diverge_all.py`)? Within one jar and across
  jars, the first difference fell between turns 7 and 12 and was of the
  same kinds: the order Forge logs a fetch land's search and a shock
  land's payment (`STACK_RESOLVE`/`EFFECT_REPLACED`/`LIFE`), mana tap
  order (`MANA`), a land played before or after the beginning of combat.
  19 pairs of runs from different jars logged identical entries through
  turn 12 (seed 2026200500: 1 stock, 5 plan; seed 2026200501: 3 stock,
  10 plan).
- Stock seats never reach `StepRunner` (they are Forge's own controllers),
  so the stock rows measure Forge's nondeterminism alone, and they split
  as much as the plan rows.
- Headers: identical except `shim`, `shimCommit` and the new `planSteps`
  (every plan seat `false`). Plan-arm agent-event counts through turn 12:
  64 to 66 per run on both jars (seed 2026200500).

So, as SPIKE.md concluded for 0.17.1 against 0.17.0: no split that one
jar does not also show against itself, and a no-steps code path that is
the 0.17.1 call line for line. Byte identity of whole runs is not
claimed; neither jar has it with itself.
