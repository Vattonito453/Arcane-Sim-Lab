# G1 pre-registration: does the E1 combo executor convert? (experiment E1, gate G1)

Written and committed **before any G1 game is run**. The runner
(`run_g1.py`) refuses to start unless this file, the runner, the reader
(`read_g1.py`), the five step files, the scenario runner and writer and the
scenario files are committed and unchanged, and unless every hash pinned
below matches. The reading is `read_g1.py`, committed in the same commit, so
the reading cannot drift toward the data either. Every game's `.cell.json`
records its start time, which is later than this file's commit time.

Plan references: `tasks/25-repair-plan.md` WS9 ("Before E1", "Phase A:
prototype E1", "Timing without Docker", "Pre-registered go/no-go, G1"),
section 4.4 (the G1 row), the experiments table (row E1), the risk table
(rows "Forced abilities misbehave in Forge's sub-choosers" and "CPU per game
rises on the 2-vCPU VM"); owner decisions in `tasks/README.md` (decision 4's
checklist; open decision (d) on C1); the builder's development record,
`studies/e1_executor/README.md`; the harness and its baselines,
`studies/scenarios/README.md` and `BASELINE.md`.

## What is being tested

**The jar.** `shim-0.18.0-proto-88e7564.jar` in the scratch folder
(`<scratch>/e1/`), SHA-256
`3795f534d24093f98e629f63553d19bab3d24b555295a24f688f3c84d69a0a0a`, built
from `exec-proto` at `88e756456304` (public shim repo, not pushed; four
commits on `shim-0.17.1-scenario` at `13eeed7`). Checked before this commit:
its `BUILD_COMMIT` reads `88e756456304`, and a fresh `javac` of the source
at that commit gives 19 class files identical to the jar's. The runner
refuses any other jar. The evidence branch `exec-proto-binary` (1a6c5d1,
the `chooseBinary` override) is not the G1 jar and is not run here.

**The step data.** The five hand-written step files the plan calls for,
committed at `e28eeb2` (S4's last change) and unchanged since:

| Scenario | Step file | SHA-256 |
|---|---|---|
| S1 | `steps/s1_kiki_conscripts.json` | `bed09a9eae7e19cee9a4ca646e3720a9b0ee43996d055c7fe3bb6a68b39f7599` |
| S2 | `steps/s2_derevi_emiel_cradle.json` | `4967a9f5803b1a376d9dad03f92d0cda87248a2df57caef9532bc23db18d3ff6` |
| S3 | `steps/s3_druid_reconfiguration.json` | `ac7c18f431f3ad453fd013b32bfc604dac087c706c1eaf9dcf5f560123414ad6` |
| S4 | `steps/s4_magda_clock_torque.json` | `d72f8f7e908eba7354014798ec4091387546aad4502da27e1751b7c034f6b019` |
| S6 | `steps/s6_scepter_reversal.json` | `3642c962b996357cb5bebd1054bc408ddf43b438561e6d94b3acedb136ecb1e0` |

**The plans.** Built by the scenario runner from `--data-dir
<scratch>/g0a/cache_cedh` (version 2, every fix flag on), with the step
file merged into the line deck's plan for the exec arm (the channel the shim
reads; `plansSha256` in every shim header covers it). Built once before this
commit, with no game, and pinned; they are byte-identical to the builder's
dev runs:

| Scenario | Exec-arm plans file SHA-256 |
|---|---|
| S1 | `674c60fbf617913bedd7a8236abb5efea3af3b8c4d62bf225e6008e233d1cbdf` |
| S2 | `66a52be86ab8a571f5267384442b967844f5ea99e45b6c5dc8ee616ebd8bf937` |
| S3 | `17d1662ab732926bb91b46911b6b5b64b67bb47c9264fb5c82e6f3800b120c31` |
| S4 | `5ccd66fcf2e58c05c714520b26bd10f9ec145758afa44440738f35a3610a54b9` |
| S6 | `6b84338908025e8efd5aadd6d39c7103f2c5ceaeb40c002c15ebaa660f391651` |
| C1 (no step file) | `ed88b2e47b64ba49af70c738c8da9e36db08f73ff816c3025e0a76739e51d7d6` |

**The harness.** `studies/scenarios/run_scenarios.py` (SHA-256
`d9f093ff...d6450`, with the exec arm), `writer.py` (`a9262ff1...174fc`),
the five S scenario files and the 20 C1 boards as committed (full hashes in
`run_g1.py`). Forge 2.0.13 desktop jar, JDK 17, `-Xmx3g`, one game per JVM,
the harness's 900 s game clock and each scenario's own horizon (S files:
4 turns after the scenario turn; C1: 8).

## What was known when this was written

Stated so the reader can judge the rules against it. The builder's
development runs (DEV seeds 2026200000-2026200999 only; README, "Development
results") read, stock against exec, 20 trials each: S1 0/20 and 0/20 kills
but the stated state then the outlet 20/20; S2 0/20 and 0/20 (Forge's
`chooseBinary` answers "tap"); S3, S4 and S6 0/20 and 20/20; 0 aborts and 0
unhandled exceptions; C1 stock 10/20, exec 9/20; 2-core executor median
0.400 ms. `read_g1.py` was run on those dev directories before this commit
to check that it parses them (`--dev`, no provenance checks): on dev data
it reads GO under the primary reading, PARTIAL under kills only and GO
under the harness's looser column. Writing it on dev data fixed one thing:
StepRunner records carry no sequence number, so S1's attack is ordered
against Forge's entries (below). No seed in the gate range below has been
played by this study. So the expected shape is: S3, S4 and S6 pass; S1
passes only through "the stated infinite state followed by the outlet"; S2
fails. **The verdict therefore turns on how S1 is read, and that reading is
fixed here** (primary reading, below), with the kills-only reading reported
beside it and its own verdict.

## Arms

| Arm | Seats | Jar | Gated |
|---|---|---|---|
| `stock` | every seat `stock:Default` (Forge's own AI) | the G1 jar | yes |
| `exec` | every seat `plan:SimLabHuman`, plan version 2, every fix flag on, plus the scenario's step file in the line deck's plan (C1 has no step file: the plan pilot on the G1 jar) | the G1 jar | yes |
| `plan017` | as `exec` without steps | `shim-0.17.1-967cb71.jar` (SHA-256 `56758de2...064fe`, week 3's harness jar) | **no**: C1 only, a reference that separates the jar's effect from the pilot's |

## Runs and seeds

Gate seeds start at 2026102300; none is inside the DEV range
2026200000-2026200999, and the runner asserts both.

| Phase | What | Seeds | JVMs | Trials |
|---|---|---|---|---|
| `outcome` | S1, S2, S3, S4, S6 x `stock`, `exec` x 20 trials | trial k: `--seed-forge` 2026102300+k and the same library shuffle, k = 0..19, paired across arms | 8, unpinned (as every baseline and dev run) | 200 |
| `c1` | the 20 C1 boards x `stock`, `exec`, `plan017` x 1 trial | 2026102320 on every board | 8, unpinned | 60 |
| `timing` | S1, S2, S3, S4, S6 x `exec` x **8 trials** | 2026102340..2026102347 | 8, each pinned to its own 2 logical CPUs | 40 |

**Timing without Docker** (WS9). Each timing JVM is started with
`-XX:ActiveProcessorCount=2` and pinned with Windows processor affinity,
set right after it starts, to its own pair of logical CPUs: masks `3, C,
30, C0, 300, C00, 3000, C000`, that is CPUs 0-15 as eight disjoint pairs,
one JVM per pair (the runner's `--affinity`, worker slot i on mask i). On
this box (Ryzen 9 7950X3D, 16 cores, 32 logical CPUs) Windows' usual
enumeration gives a core's two hardware threads the numbers 2k and 2k+1
(not checked with a topology tool here), so each JVM gets one core's two
threads, which is what a 2-vCPU GCP VM (`e2-standard-2`, production) gives
a worker, on a faster core. Nothing else of this study runs during the
timing phase. Other agents' processes share the box and are not
controlled; the runner logs the number of Java processes and the CPU load
once a minute during every phase, and RESULTS reports them.

Order: `check` (provenance only, no game), `outcome`, `c1`, `timing`. If a
phase is interrupted it is resumed with the same command: a finished trial
is reused only when its state file and plans file hashes match (the
harness's rule), and an unfinished trial is re-run from its start on the
same seed. That is reported as a deviation. No trial is re-run because of
its outcome, and the step data, jar and plans do not change in response to
any gate result.

## Definitions

**Kill (both arms).** The harness's `success` column, each scenario's
unchanged rule: S1, S2, S3 and S6, the line seat (seat 0) wins by turn 9,
the scenario turn; S4, seat 0 wins by turn 12 (the opponents lose drawing
from empty libraries on their turns 10 to 12).

**The stated infinite state followed by the outlet (exec arm).** From the
step file's `state_step` and `outlet_step` and the trial's StepRunner
records (`exec_arm`, `exec_step`, `exec_stop`, `exec_abort`, each stamped
with the game turn), both on the scenario turn (turn 9 in every S file) and
in this order:

1. **State:** an `exec_stop` record at `step` = `state_step`, not a
   `confirm` answer, whose reason is one of the loop's own stop predicates
   (`count`, `power_vs_life`, `opponents_out`, `mana_at_least`,
   `no_progress`). A loop that stopped on `max`, on the wall budget, or
   because its first action could no longer be played (`exhausted`) did not
   reach the stated state.
2. **Then the outlet:** a later StepRunner record, on the same turn: for
   an `activate` or `cast` outlet, an `exec_step` at `step` =
   `outlet_step` with `op` `activate` or `cast` (the action was issued);
   for S1's `pass` outlet, the `exec_stop` with reason `handoff` at
   `outlet_step`, and the line seat declaring attackers on the scenario
   turn (Forge's COMBAT entry "<line seat> assigned ... to attack ...")
   later in Forge's log than the seat's first activation or cast of a line
   piece that turn. StepRunner records carry no sequence number, so the
   attack is ordered against Forge's own entries; a line ends when its
   phase ends, so a hand-off in the phase where the line began comes before
   that turn's combat.

| Scenario | Stated state (step file `state`, the loop at `state_step`) | Outlet (`outlet_step`) |
|---|---|---|
| S1 | step 0: Kiki-Jiki copies Zealous Conscripts, each copy's trigger bound to untap Kiki-Jiki, until untapped power is at least the opponents' total life plus 15 (`power_vs_life`) | step 1: `pass`, the attack handed to the pilot |
| S2 | step 0: tap Gaea's Cradle, blink Derevi with Emiel, Derevi's trigger bound to untap the Cradle, until 476 mana floats (`mana_at_least`) | step 2: Walking Ballista's ping |
| S3 | step 0: Devoted Druid's mana and untap, until 476 mana floats | step 2: Walking Ballista's ping |
| S4 | step 2: 20 Clock of Omens untaps of Magda (`count`), each making a Treasure | step 3: Magda's five-Treasure search |
| S6 | step 0: rocks, then Isochron Scepter casting Dramatic Reversal, until 476 mana floats | step 2: Walking Ballista's ping |

This is stricter than the harness's own `state_then_outlet` column, which
does not check the turn or the order; that column is reported beside it.

**G1 success of a trial.** Exec arm: a kill, **or** the stated state
followed by the outlet (the primary reading: the plan's own words, "kills
(or the stated infinite state followed by the outlet)"). Stock arm: a kill.
Stock has no executor, so the executor's records cannot be read for it; the
harness's line activity on the scenario turn is reported beside it (week 3:
stock's loops did not run: the Conscripts copy's untap targeted Kiki-Jiki
in 0 of 39 triggers, and Derevi's trigger targeted Gaea's Cradle in 0 of
155). Every scheduled trial counts in its denominator of 20: a trial
that did not finish, whose line did not load, or whose game timed out is a
failure.

Why the primary reading counts S1's state and outlet: G1 asks of S1 and
S2 whether the executor can target a trigger inside a loop. S1's stated
state (arbitrarily many hasty copies, each copy's trigger bound to
Kiki-Jiki) exists only if that targeting works on every pass, and the step
file stated it and its outlet at `d1f5142`, before this file. What the
attack then does is combat: the `pass` outlet hands it to Forge's attack AI
and the pilot (combat work is frozen until G4, owner decision 1), and no
executor operation distributes attackers (Phase B's `hand_off_attack` is the
same hand-off). The kills-only reading is reported with its own verdict.

**A scenario passes** when exec G1 success is at least 16/20 **and** stock
kills are at most 2/20 on it.

**Unhandled exception** (per trial, any arm): (i) the JVM exited non-zero;
(ii) the shim printed `shim: fatal`; (iii) the result record carries an
error; (iv) the trial ran but wrote no result record; or (v) a stderr line
`Exception in thread`, an exception that escaped its thread. Caught
exceptions are not unhandled: an executor exception caught and logged as
`exec_abort` (counted below), and Forge's own caught and printed exceptions
(the `CompletionException`/`ConcurrentModificationException` pairs from its
parallel attack futures, `setGameOver threw` at the turn-cap kill, which
the shim catches); their printed lines are reported.

**Decision time.** The `ms=` field of every StepRunner record: the
executor's own wall time from entering a hook (`chooseSpellAbilityToPlay`,
`orderAndPlaySimultaneousSa`, `confirmTrigger`) to returning. Forge's
resolution and the other seats' decisions are outside it. The gated figure
is the median over every executor decision in the timing phase, all five
scenarios pooled (per-scenario medians, p95 and max are reported).

**Sub-chooser misbehaviour** (the plan's risk table measures it with "E1
exceptions and `exec_abort` reasons"): an `exec_abort` whose reason is
`not-played` (the executor returned a data-named action that had passed
`canPlay`, `canTarget` and `canPayCost`, and Forge did not put it on the
stack or add its mana, twice running) or `exception ...` (an executor hook
threw; caught, line handed back). `precondition ...` and `trigger-mismatch
...` aborts are the designed fallback for an unmet precondition and are
reported, not counted here. A resolution-time choice that raises no abort
(S2's known `chooseBinary` answer) shows in its scenario's success, not
here.

**Time budget.** A line that ended on its per-turn wall budget
(`exec_stop` reason `budget`) or a game that timed out (the result's
`timedOut`), exec arm, outcome phase; and the 2-core decision median.

**C1 not broken.** C1 is a positive control: 20 real boards that Forge
converts about half the time. The plan's own target (>= 17/20) cannot be
met by Forge itself on these boards (BASELINE.md; owner decision (d),
pending, recommends board-level agreement with the source games instead),
so G1 uses a paired, noise-based rule. C1 is not broken when all of:

- (a) exec C1 successes (a Godo win within 8 turns) are **not lower than
  stock's by more than 3**, on the same 20 boards and seed;
- (b) all 20 exec C1 trials finish with a result and load their line
  pieces (Godo, Helm attached) as written;
- (c) no StepRunner record appears in any exec C1 trial (no step data, so
  no executor);
- (d) the control itself works: stock's board-level agreement with the
  source games (success against the source game's own "won within 8
  turns") is at least 14/20.

Justification from week 3's review (10 stock trials on each board, 97/200):
the per-board rates give the difference between two independent
single-trial sweeps of the same pilot a standard deviation of 1.39 (1.81 if
every board's rate is clipped into [0.05, 0.95], since 0/10 and 10/10 are
not certainties); a sweep 4 or more lower than the other has probability
0.5% (2.6% clipped), 3 or more 3.3% (8.0%). The margin of 3 keeps the
false alarm from trial noise under 3% and leaves room for the plan pilot's
legitimate difference from stock (week 3: plan 11/20 against stock 10/20;
dev on this jar: 9 against 10); a jar that broke the pilot or woke the
executor without data would fall far below it, and (c) catches the second
directly. For (d), the same rates put one stock sweep's expected agreement
at 17.3 (SD 1.0); 13 or fewer has probability 0.01% (1.1% clipped); week 3
measured 18/20. (d) tests the harness, not the executor: if it fails, C1
cannot judge the executor and "C1 not broken" is not established.

**Java diff and lint.** Measured by `read_g1.py` in the shim repository:
`git diff --numstat 13eeed7..88e7564 -- '*.java'`, counted as added **plus
removed** lines (the strictest reading; the builder's added-only count is
reported beside it); it passes at 400 or fewer. Lint:
`tools/lint_card_names.py --cardsfolder <Forge 2.0.13 res/cardsfolder>` at
`88e7564` exits 0. Known before this commit: 395 added, 1 removed (396),
lint ok (10 Java files against 35,069 card names).

## The plan's decision rules (verbatim, `tasks/25-repair-plan.md` WS9)

> **Pre-registered go/no-go, G1 (Fri 10/23).** 20 trials per scenario, stock vs prototype.
> - **GO:**
>   - at least 16/20 kills (or the stated infinite state followed by the outlet) on at least 3 of S1, S2, S3, S4 and S6, including S1 or S2;
>   - stock at most 2/20 on the same scenarios, and C1 not broken;
>   - 0 unhandled exceptions;
>   - median decision time at most 2 s under 2-core affinity;
>   - Java diff at most 400 lines, lint clean.
>
>   Then: merge the generic path (WS6) and build Phase B.
> - **PARTIAL:** the activation scenarios pass (S3, S4, S6) but trigger targeting (S1, S2) fails. Then:
>   - build activation and cast-from-zone lines only;
>   - mark trigger-target lines `not_drivable` and say so in the product;
>   - spend 1 day testing bounded `GameSimulator.simulateSpellAbility` as a line check only (as a pilot it failed 2 of 2 games);
>   - file a Card-Forge issue about loop targeting.
> - **NO-GO:** forced abilities misbehave in sub-choosers, crash or blow the time budget, or success is at most 6/20 on most scenarios. Then:
>   - stop executor work. Phase B's slots (W9, W11, W13–W14) go to T2 and T3, readmission for spells, and UX phase 2;
>   - the product keeps "Forge's AI doesn't run combo loops, so these show chances, not results" and the floor label permanently;
>   - file an upstream issue (TapOrUntapAi and ControlGainAi pick opponents' permanents).

## The operational reading (what `read_g1.py` computes)

**GO** when all of:

- **G-a** at least 3 of S1, S2, S3, S4, S6 pass (exec G1 success >= 16/20
  and stock kills <= 2/20 on that scenario), S1 or S2 among them;
- **G-b** C1 not broken, (a) to (d);
- **G-c** 0 unhandled exceptions in every trial on the G1 jar (outcome, both
  arms; C1 `stock` and `exec`; timing);
- **G-d** the pooled 2-core median decision time is at most 2,000 ms (a
  timing phase that logged no executor decision fails this);
- **G-e** the Java diff is at most 400 lines and the lint passes.

**NO-GO** when any of:

- **N-a** sub-chooser misbehaviour in at least 5 of the 20 exec trials of
  any one scenario (outcome phase);
- **N-b** a crash: at least 1 unhandled exception in an exec-arm trial
  (outcome, C1 `exec`, timing);
- **N-c** the time budget blown: the pooled 2-core median above 2,000 ms,
  or at least 5 of the 20 exec trials of any one scenario ending on the
  line's wall budget or timing out (outcome phase). 5 is the count at which
  time alone takes a scenario below 16/20;
- **N-d** exec G1 success at most 6/20 on at least 3 of the 5 scenarios
  ("most").

**PARTIAL** when S3, S4 and S6 each pass, neither S1 nor S2 passes, and
G-b, G-c, G-d and G-e hold.

**Precedence:** NO-GO, then GO, then PARTIAL. Anything else is
**UNDECIDED**: RESULTS names the conditions that failed and the owner
decides. A phase with a missing trial (scheduled, no output) gives no
verdict until it is resumed.

## Consequence of each verdict (the plan's)

- **GO:** merge the generic path (WS6) and build Phase B.
- **PARTIAL:** activation and cast-from-zone lines only; trigger-target
  lines marked `not_drivable` and said so in the product; 1 day testing
  bounded `GameSimulator.simulateSpellAbility` as a line check only; file
  a Card-Forge issue about loop targeting.
- **NO-GO:** stop executor work (Phase B's slots go to T2 and T3,
  readmission for spells and UX phase 2); the product keeps "Forge's AI
  doesn't run combo loops, so these show chances, not results" and the
  floor label permanently; file the upstream issue.

## Reported, not gated

- **Sensitivity verdicts** under the same rules with two other success
  definitions for the exec arm: kills only; and the harness's looser
  `state_then_outlet` column (any turn, any order) or a kill.
- Per scenario and arm: kills, the strict state then outlet, the harness's
  column, Wilson 95% intervals, stops, aborts by reason, trigger binds,
  actions, executor decisions and their ms (median, p95, max), game
  seconds, timeouts, printed exception lines, lines loaded.
- C1: each arm's successes, successes on the scenario turn, agreement with
  the source games (owner decision (d)'s recommended criterion), the
  `plan017` reference arm, and a per-board table.
- Timing: per-scenario medians, p95 and max; game seconds pinned; outcomes
  pinned (4 trials per scenario in dev; 8 here, a timing check, not an
  outcome measurement).
- The load log, and whether the plans used equal the pinned ones.
- S2 on the evidence branch is not run: it is not the G1 jar, and the
  owner's `chooseBinary` decision rests on the builder's dev evidence.
