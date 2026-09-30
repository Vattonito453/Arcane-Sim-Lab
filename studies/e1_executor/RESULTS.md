# G1 results: the E1 combo executor go/no-go (experiment E1)

**Verdict under the pre-registered primary reading: GO.** Under the
kills-only reading, reported beside it as the PREREG requires, the same data
reads **PARTIAL**. Every rule, seed, hash and definition is in `PREREG.md`
(commit `889fb76`, 20:13:12 on 2026-09-29); the first gate game started at
20:13:35. `read_g1.py`, committed with the PREREG, produced every figure
below from the raw shim output.

In short: on fresh gate seeds the prototype drove S3, S4 and S6 to the kill
in 20 of 20 trials each, and S1 to its stated infinite state followed by
the outlet in 20 of 20, with stock at 0 of 20 on all five scenarios. S1
never killed on the scenario turn (0 of 20): the executor built 44 hasty
copies and handed the attack to the pilot, whose split left one opponent
alive; the seat won two turns later in 20 of 20. S2 failed (0 of 20) the
same way it failed in development: the Derevi trigger was bound to Gaea's
Cradle every time, and Forge's `chooseBinary` then tapped it. There were 0
unhandled exceptions and 0 executor aborts, C1 is not broken, the executor's
median decision under 2-core affinity was 0.362 ms against a 2 s limit, and
the Java diff is 396 lines with a clean lint. An independent review (last
section) confirmed the reading, reproduced every scenario's outcome on
fresh seeds and corrected the S1 attack split to 31 and 15.

## The verdict and what the plan does with it

| Condition (PREREG, "The operational reading") | Measured | Holds |
|---|---|---|
| G-a: at least 3 of S1, S2, S3, S4, S6 pass (exec >= 16/20, stock <= 2/20), S1 or S2 among them | S1, S3, S4, S6 pass (20/20 each, stock 0/20); S2 does not (0/20) | yes |
| G-b: C1 not broken, (a) to (d) | exec 8/20 against stock 9/20 (margin 3); 20/20 finished and loaded; 0 executor records; stock agreement with the source games 17/20 (floor 14) | yes |
| G-c: 0 unhandled exceptions on the G1 jar | 0 in 280 trials (outcome 200, C1 `stock` and `exec` 40, timing 40) | yes |
| G-d: pooled 2-core median decision time <= 2,000 ms | 0.362 ms over 24,306 decisions | yes |
| G-e: Java diff <= 400 lines, lint clean | 395 added + 1 removed = 396; lint ok | yes |
| N-a: sub-chooser misbehaviour in >= 5 of 20 exec trials of a scenario | 0 `not-played` or `exception` aborts (0 aborts of any kind) | no |
| N-b: >= 1 unhandled exception in an exec-arm trial | 0 | no |
| N-c: 2-core median > 2 s, or >= 5 of 20 exec trials of a scenario ending on the budget or timing out | 0.362 ms; 0 budget stops, 0 timeouts | no |
| N-d: exec success <= 6/20 on at least 3 of 5 | 1 of 5 (S2) | no |
| PARTIAL: S3, S4, S6 pass, neither S1 nor S2, and G-b to G-e | S1 passes | no |

No NO-GO condition holds and every GO condition does, so the verdict is GO.

**The plan's consequence for GO** (`tasks/25-repair-plan.md` WS9, section
4.4): merge the generic path (WS6) and build Phase B.

**What GO rests on, stated plainly.** GO needs S1 or S2. S2 fails outright.
S1 passes only through the plan's parenthetical, "kills (or the stated
infinite state followed by the outlet)", which the PREREG fixed as the
primary reading before the run, because S1 tests whether the executor can
bind a trigger's target inside a loop (it did, 880 of 880 times on the
scenario turn) and its outlet is a hand-off of combat, which is not an
executor operation and is frozen until G4 (owner decision 1). Read as kills
only, S1 is 0/20 and the verdict is PARTIAL, whose consequence would be
activation and cast-from-zone lines only, trigger-target lines marked
`not_drivable`, a one-day `GameSimulator` line-check spike and a Card-Forge
issue about loop targeting. The owner should know that the difference
between those two branches is S1's combat finish, and that no step data can
change it (see S1 below).

Three things G1 does not settle, each for the owner or Phase B:

1. **S2 needs `chooseBinary`.** Forge's `PlayerControllerAi.chooseBinary`
   answers Derevi's "tap or untap?" with tap every time, and that override
   is outside decision 4's API list. The builder's evidence branch
   (`exec-proto-binary`, 1a6c5d1, not run here) made S2 20/20 on dev seeds
   at 417 Java lines. Extending decision 4 is the owner's call.
2. **A trigger-target line whose payoff is combat reaches its state, not a
   kill.** The pilot's attack split sent 31 attackers at one opponent and
   15 at another (46 in all) in all 20 S1 trials; the third was never
   attacked. (First published as 33 and 17, which counted the `Ai(n)` seat
   prefixes as instance ids; corrected by the review below.) Phase
   B's `hand_off_attack` is this same hand-off.
3. **Long lines cost Forge's time.** S4's games took 603 to 737 s against
   the 900 s clock (the line alone 504 to 631 s, budget 780 s), 2.5 to 3
   times a typical 240 s game, none of it the executor's. G3's VM CPU check
   has to price such lines.

## What ran

| Phase | Trials | Seeds | JVMs | Started / finished | Wall |
|---|---|---|---|---|---|
| outcome: S1, S2, S3, S4, S6 x `stock`, `exec` x 20 | 200 | 2026102300..2026102319 | 8, unpinned | 20:13:35 / 20:58:39 | 2,704 s |
| c1: 20 boards x `stock`, `exec`, `plan017` x 1 | 60 | 2026102320 | 8, unpinned | 20:59:08 / 21:12:30 | 802 s |
| timing: S1, S2, S3, S4, S6 x `exec` x 8 | 40 | 2026102340..2026102347 | 8, each pinned to 2 logical CPUs | 21:12:44 / 21:27:08 | 864 s |

- **Provenance, checked by the runner before every phase and by the reader
  after:** the jar (`3795f534...a0a0a`), the five step files, the six plans files, the
  scenario runner, writer and scenario files and the C1 digest all matched
  their pinned hashes (every trial on the G1 jar reads shim commit
  `88e756456304` in its header); every invocation ran at repo
  `889fb76c88cc`, clean; every trial's seed was its pre-registered seed; every game started after
  the PREREG commit. The reader found no provenance problem and no missing
  trial.
- **No deviation from the protocol.** Each phase ran once, in one
  invocation, with 0 trials cached, interrupted or re-run. The runner, the
  reader and the step data are unchanged since `889fb76`.
- **Load.** The runner's once-a-minute log never saw a Java process on the
  box other than this study's 8. CPU load (whole box): outcome mean 47%,
  max 90%; C1 mean 55%, max 85%; timing mean 52%, max 100%. During timing
  the 8 pinned JVMs could use at most half the box (16 of 32 logical CPUs),
  so the 96% and 100% readings at 21:14 and 21:15 mean other processes
  were busy then; they were not controlled (as pre-registered), and the one
  timing outlier below falls in that window.
- Environment: Windows 10, Ryzen 9 7950X3D (16 cores, 32 logical CPUs), 63
  GB; Forge 2.0.13 desktop jar, JDK 17, `-Xmx3g`, 900 s game clock, each
  scenario's own horizon; plans from `<scratch>/g0a/cache_cedh`. Raw output
  stays in `<scratch>/g1/runs/`; `g1_summary.json` here is the reader's
  output without the per-trial rows.

## Outcome: 20 trials per scenario and arm

G1 success is a kill for stock, and a kill or the strict stated state
followed by the outlet for exec (PREREG, "Definitions"). Wilson 95%
intervals.

| Scenario | Stock kills | Exec G1 success | Exec kills | Exec state then outlet (strict) | Harness's looser column | Passes |
|---|---|---|---|---|---|---|
| S1 Kiki-Jiki + Zealous Conscripts (trigger target) | 0/20 (0.00-0.16) | **20/20** (0.84-1.00) | 0/20 (0.00-0.16) | 20/20 | 20/20 | yes |
| S2 Derevi + Emiel + Gaea's Cradle (trigger target) | 0/20 (0.00-0.16) | **0/20** (0.00-0.16) | 0/20 | 0/20 | 0/20 | no |
| S3 Devoted Druid (flagged activation) | 0/20 (0.00-0.16) | **20/20** (0.84-1.00) | 20/20 | 20/20 | 20/20 | yes |
| S4 Magda + Clock of Omens + Liquimetal Torque (activated loop) | 0/20 (0.00-0.16) | **20/20** (0.84-1.00) | 20/20 (by turn 12) | 20/20 | 20/20 | yes |
| S6 Isochron Scepter + Dramatic Reversal (activation loop, X outlet) | 0/20 (0.00-0.16) | **20/20** (0.84-1.00) | 20/20 | 20/20 | 20/20 | yes |

Every trial of both arms loaded its line pieces exactly and finished with a
result; no game timed out.

| Scenario (exec) | Armed | Trigger binds | Actions per trial | Stops | Aborts | Decisions | Decision ms, median / p95 / max | Game s, mean / max | Printed exception lines (stock; exec) |
|---|---|---|---|---|---|---|---|---|---|
| S1 | 20/20 | 1,200 | 60 | handoff x40; power_vs_life x40 | 0 | 2,520 | 0.292 / 1.791 / 46.7 | 29.8 / 33.3 | 0; 560 |
| S2 | 20/20 | 20 | 7 | done x20; exhausted x60 | 0 | 300 | 0.694 / 40.1 / 63.7 | 17.7 / 34.3 | 0; 0 |
| S3 | 20/20 | 0 | 1,192 | exhausted x20; mana_at_least x20 | 0 | 23,900 | 0.345 / 1.057 / 36.0 | 52.2 / 59.9 | 0; 0 |
| S4 | 20/20 | 0 | 213 | count x40; hold x20; no_progress x20; turn-or-phase-ended x20 | 0 | 10,120 | 0.047 / 10.98 / 46.8 | 647.0 / 736.6 | 1; 0 |
| S6 | 20/20 | 0 | 1,193 | exhausted x20; mana_at_least x20 | 0 | 23,920 | 0.506 / 1.047 / 37.9 | 47.4 / 56.9 | 0; 0 |

Pooled over the five exec arms (8 JVMs, unpinned): 60,760 executor
decisions, median 0.461 ms, p95 1.98 ms, max 63.7 ms.

Scenario by scenario:

- **S1.** In every trial the line armed on turn 9, Kiki-Jiki copied Zealous
  Conscripts 44 times, and every copy's enter trigger was bound to Kiki-Jiki
  (880 of 880 bound on turn 9; in one trial, trial 4, the pilot activated
  Kiki-Jiki once more after the hand-off, and that copy's trigger, outside
  the line, went where Forge chose, Thalia). The loop stopped on
  `power_vs_life` and the `pass` outlet handed combat to the pilot, which
  declared 31 attackers (Zealous Conscripts) at winota_ian and 15
  (Kiki-Jiki and 14 Conscripts) at winota_mike in 20 of 20 trials: all 45
  Conscripts and Kiki-Jiki. Two opponents died; the line armed again on turn 11 (16 copies,
  320 binds) and the seat won on turn 11 in 20 of 20, two turns after the
  scenario turn, so 0/20 kills by S1's rule. Stock never bound the untap to
  Kiki-Jiki: its Conscripts triggers targeted Thalia (turn 9, 20 times),
  Bartz Klauser (turn 13, 18) and Serra Ascendant (1). The 560 printed
  lines are 280 `CompletionException`/`ConcurrentModificationException`
  pairs from Forge's parallel attack futures with 46 attackers, caught
  by Forge; every game finished normally. They do not change the
  declaration: the pinned timing trials with no such line (4 of 8)
  declared the same 31 and 15.
- **S2.** On turn 9 the executor bound Derevi's trigger to the tapped
  Gaea's Cradle in 20 of 20 trials (stock: 0 of 155 Derevi triggers on the
  Cradle, which went to Ragavan, Birds of Paradise and Sol Ring), declined
  Emiel's optional trigger as the data says, and then the Cradle stayed
  tapped: `chooseBinary` answered "tap". The mana loop was `exhausted` after
  one pass (`canPlay Gaea's Cradle`), Ballista spent what little mana there
  was, and the line ended `done`. No abort: the binding worked, the
  resolution-time choice did not, and the plan counts that in S2's success
  (PREREG, "Sub-chooser misbehaviour").
- **S3.** Devoted Druid's untap (`AI:RemoveDeck:All`, never offered by
  Forge's AI) ran through the generic path until 476 mana floated
  (`mana_at_least`), Ballista took the counters, and the pings killed all
  three opponents on turn 9 in 20 of 20.
- **S4.** Torque, Sol Ring, 20 Clock of Omens passes (`count`, the stated
  state), three Magda searches (the outlet), then Station and Clock until
  the opponents' libraries stopped shrinking (`no_progress`) and the
  holding pass. The same 213 actions in every trial; the opponents lost
  drawing and the seat won on turn 12 in 20 of 20. The line took 504 to
  631 s of wall clock (budget 780 s) and the game 603 to 737 s (clock
  900 s): the closest trial had 149 s left on the budget and 163 s on the
  clock. The one printed line in the stock arm is Forge's `setGameOver`
  NullPointerException at the turn-cap kill, which the shim catches.
- **S6.** Sol Ring, Arcane Signet, Fellwar Stone and the Scepter's copy of
  Dramatic Reversal floated 476 mana; Ballista killed all three opponents on
  turn 9 in 20 of 20.

Against the development run (DEV seeds, `README.md`): the same outcome on
every scenario, the same attack split in S1, the same S2 failure, and
per-scenario executor medians within 0.04 ms of it.

## C1: the positive control

The 20 real boards, one trial each on seed 2026102320. C1 has no step file,
so the exec arm is the plan pilot on the G1 jar with no steps; `plan017` is
the same pilot on week 3's 0.17.1 jar (reported, not gated).

| Arm | Finished | Line loaded | Won within 8 turns (95% CI) | On the scenario turn | Agreement with the source game | Executor records | Unhandled / printed exception lines |
|---|---|---|---|---|---|---|---|
| stock | 20 | 20 | 9/20 (0.26-0.66) | 4/20 | 17/20 | 0 | 0 / 0 |
| exec | 20 | 20 | 8/20 (0.22-0.61) | 4/20 | 16/20 | 0 | 0 / 2 |
| plan017 | 20 | 20 | 7/20 (0.18-0.57) | 4/20 | 17/20 | 0 | 0 / 1 |

- (a) exec 8 against stock 9: one lower, inside the margin of 3. Board by
  board exec and stock differ on 3 boards (stock alone won 015_r0_g10 and
  015_r2_g08; exec alone won 016_r0_g06). Exec and `plan017`, the same
  pilot on the old and new jars, differ on 1 board (016_r0_g06, exec won on
  turn 25).
- (b) all 20 exec trials finished with their line pieces (Godo, Helm
  attached) loaded as written.
- (c) no StepRunner record in any exec C1 trial.
- (d) stock agreed with the source games on 17 of 20 boards (floor 14;
  week 3: 18/20). It disagreed on 015_r0_g10 (won in the harness, not in
  the game), 015_r0_g14 (the reverse, as in week 3) and 016_r2_g00 (the
  reverse).
- The printed lines are on one board, 016_r2_g00: a `StackOverflowError`
  inside a Java future, printed as an `ExecutionException`, in both the
  exec and the `plan017` trial (plus a `TimeoutException` in exec). It
  happens on the old jar too, the futures catch it, and both games
  finished with a result.
- Week 3 read stock 10/20 and plan 11/20 on seed 2026101400; the builder's
  dev run read stock 10/20 and exec 9/20. All of these sit inside one
  another's intervals.

## Timing under 2-core affinity

Eight JVMs at once, each started with `-XX:ActiveProcessorCount=2` and
pinned right after start to its own pair of logical CPUs (masks 3, C, 30,
C0, 300, C00, 3000, C000). Every timing trial's record carries its mask
and the flag, and no two trials ran on one mask at once. The record is the
mask the runner asked for: the runner does not read it back, and no saved
artifact shows the running JVMs' affinity. The review verified the same
code path live (below): every JVM held its own mask from about a second
after start, and the JVM itself read 2 active processors.

| Scenario | Trials | G1 success | Kills | Decisions | Decision ms, median / p95 / max | Game s | Printed exception lines |
|---|---|---|---|---|---|---|---|
| S1 | 8 | 8 | 0 | 1,010 | 0.274 / 1.50 / 19.0 | 29.6-240.1 | 12 |
| S2 | 8 | 0 | 0 | 120 | 0.584 / 28.7 / 49.7 | 14.8-22.8 | 0 |
| S3 | 8 | 8 | 8 | 9,560 | 0.287 / 0.768 / 30.3 | 41.0-49.9 | 0 |
| S4 | 8 | 8 | 8 | 4,048 | 0.041 / 9.45 / 25.5 | 577.5-628.6 | 0 |
| S6 | 8 | 8 | 8 | 9,568 | 0.396 / 0.822 / 24.6 | 38.1-43.8 | 0 |

**Pooled: 24,306 executor decisions, median 0.362 ms** (p95 1.65 ms, max
49.7 ms), against G1's limit of 2,000 ms. 0 unhandled, 0 timeouts, and the
same outcomes as the unpinned arm.

- One S1 timing trial (trial 2, CPUs 4 and 5) took 240 s of game where
  the other seven took about 30 s: its turn-9 line ran for 223.5 s instead
  of about 10.7 s, while the executor's own decisions in it had a median of
  0.28 ms and a maximum of 14 ms (trial 0: 0.36 and 15 ms). It ran from
  21:12:44 to 21:17:05, when the box read 96% and 100% CPU load although
  this study could use at most half of it, so the likeliest cause is other
  processes competing for its two pinned CPUs; either way the time was
  Forge's, not the executor's. It still reached its state and outlet and
  won on turn 11.
- S1 printed 12 lines pinned (6 of Forge's caught
  `ConcurrentModificationException` pairs in 4 trials); the builder's
  pinned dev run printed none in 4 trials, so fewer cores make the race
  rarer, not absent.
- S4 games pinned took 578 to 629 s, inside the unpinned range: the work is
  one game thread walking cards, as the builder's profile found.
- Eight trials per scenario is a timing check. The decision count is
  dominated by S3 and S6 (about 1,200 decisions per trial); each
  scenario's own median is under 0.6 ms.

## Java diff and lint

`git diff --numstat 13eeed7..88e7564 -- '*.java'` in the shim repository:
`StepRunner.java` 355 added (new), `PlanPlayerController.java` 30 added,
`DeckPlan.java` 5 added, `SimShim.java` 5 added and 1 removed (the version
string). 395 added and 1 removed, **396 in the strictest reading**, under
the cap of 400. `tools/lint_card_names.py` at `88e7564` against Forge
2.0.13's cardsfolder: ok, 10 Java files against 35,069 card names. Before
the PREREG, a fresh `javac` of `88e7564` gave 19 class files identical to
the G1 jar's.

## Sensitivity readings (reported, not deciding)

| Exec success counted as | S1 | S2 | S3 | S4 | S6 | Verdict |
|---|---|---|---|---|---|---|
| Kill or strict state then outlet (primary) | 20 | 0 | 20 | 20 | 20 | **GO** |
| Kills only | 0 | 0 | 20 | 20 | 20 | PARTIAL |
| Kill or the harness's looser column | 20 | 0 | 20 | 20 | 20 | GO |

## Reproduce

```bash
py studies/e1_executor/run_g1.py check      # provenance only
py studies/e1_executor/run_g1.py all        # outcome, c1, timing (about 73 min at 8 JVMs)
py studies/e1_executor/read_g1.py --json <scratch>/g1/g1_reading.json --md <scratch>/g1/g1_reading.md
```

Raw output (JSONL, stderr, cell records, the harness's reports, load logs)
is in `<scratch>/g1/runs/`, outside git. A re-run on the same seeds pairs
openings but is not byte-identical (CLAUDE.md, gotcha 10).

## Independent review (branch `r4/e1-review`)

An adversarial review of the prototype, its step data and this reading,
after the gate. Nothing the gate pinned changed: no Java, step file,
plans, runner, writer, reader or PREREG edit. The review corrected two
statements in this file and the README (the S1 attack split, the affinity
wording) and adds this section. **It confirms the verdict: GO under the
pre-registered primary reading, PARTIAL by kills only**, with the notes
at the end. Raw output: `<scratch>/e1_review/runs/`.

### What was checked

- **The jar.** A fresh `javac` of `exec-proto` at `88e7564` against Forge
  2.0.13 gives 19 class files byte-identical to the G1 jar's
  (`BUILD_COMMIT` `88e756456304`); the jar's SHA-256 is the pinned one.
- **The boundary** (decision 4's checklist, shim README "Boundary
  rulings"). `git diff --numstat 13eeed7..88e7564 -- '*.java'`: 395 added,
  1 removed (the version string), 396 strict; the card-name lint passes
  (10 files, 35,069 names). The `orderAndPlaySimultaneousSa` override binds
  a target only on a trigger whose host card the armed line's `triggers`
  data names, skips copies and Charm triggers, and hands every other
  trigger, a failed bind and a bound trigger `playStack` refuses to
  `super`; with no plan `steps` the hooks run the 0.17.1 code. Decisions go
  through `canPlay`, `ComputerUtilCost.canPayCost`, `canTarget` and
  `ComputerUtil.playStack`; the rest is reading public state and setting
  the chosen ability's own activating player and targets. No card name,
  and no scoring beyond the plan's closed vocabulary (`lowest_life`,
  `largest_library`, the five stop predicates). The override is 20 lines,
  91 with its helpers, against decision 4's 600. One widening is
  disclosed in the shim README and is load-bearing: a mana ability is
  returned as an action (WS9 Phase A item 1 says "a non-mana activation"),
  and S3's and S6's loops need it to float mana.
- **Gate integrity.** The PREREG commit is 20:13:12; all 300 gate cells
  started after it (first 20:13:35) and exited 0; no JSONL with a gate
  seed exists anywhere else in the scratch folder; the gate seeds
  (2026102300-347) are disjoint from the dev range (2026200000-999); the
  jar, step files, runner, writer and scenario files hash to their pins;
  the commits after the PREREG touch only README, RESULTS and
  `g1_summary.json`. `read_g1.py` re-run on a copy of the raw output
  reproduces `g1_reading.md` line for line (GO, no provenance problem).
  An independent tally from the raw result and StepRunner records (not
  the harness or the reader) gives the same kills, timeouts, aborts and
  per-scenario medians, and the same pooled 2-core median, 0.362 ms over
  24,306 decisions, computed as pre-registered (every StepRunner record's
  `ms=` in the timing phase, pooled).
- **The S1 finding itself.** On turn 9 every trial put exactly 44
  Conscripts copy triggers on the stack while the line was armed, and all
  44 carried Kiki-Jiki as their target (880 of 880); the one other
  Conscripts trigger that turn (trial 4) came from an activation the pilot
  made after the hand-off, and Forge's AI aimed it at Thalia, as the
  checklist requires once the line has ended.
- **2-core pinning.** Windows' own topology
  (`GetLogicalProcessorInformation`) puts logical processors 2k and 2k+1
  on one physical core for all 16 cores, so masks 3 to C000 are one
  core's two hardware threads each, as the PREREG assumed without
  checking. In the gate's timing phase no two JVMs held one mask at once
  (at most 8 ran together; the apparent overlaps are under a second, from
  start stamps cut to the second). Live, on the same code path (6 JVMs,
  masks 3 to C00, S3 exec, seeds 2026103160-165, polled every 5 s): every
  JVM held exactly its mask from the first poll, about a second after
  start, to its end, and `jcmd VM.info` read "CPU: total 32 (initial
  active 2)". 6/6 kills; executor median 0.252 ms over 7,170 decisions.
- **Step data.** Each file names its scenario and the line seat's deck;
  every card it names is on that board or, for S4's searches (Battered
  Golem, Grinding Station, Maskwood Nexus), in magda's library; Walking
  Ballista and Isochron Scepter are the harness's documented placements.
  Forge adjudicates every action, so nothing in the data can fake a kill.
  What is fitted to these boards is listed in the notes.

### Reproduction on fresh seeds

REVIEW seeds 2026103100-199 (outside the gate's and the dev range; no
other run used them), 6 JVMs unpinned, the G1 jar, step files and plans.

| Scenario | Stock kills | Exec kills | Exec strict state then outlet (`read_g1.py`) | Gate (20 trials) |
|---|---|---|---|---|
| S1 | 0/10 | 0/10 | 10/10 (440 of 440 line triggers bound on turn 9; in trial 0, as in the gate's trial 4, the pilot's one activation after the hand-off went to Thalia; split 31 and 15 in 10/10) | 0/20 kills, 20/20 |
| S2 | 0/10 | 0/10 | 0/10 (bound to the Cradle 10/10, then tapped) | 0/20 |
| S3 | 0/10 | 10/10 | 10/10 | 20/20 |
| S6 | 0/10 | 10/10 | 10/10 | 20/20 |
| S4 (exec only, 6 trials) | – | 6/6 by turn 12 | 6/6 | 20/20 |

Seeds 2026103100-109 (S4: 2026103170-175). 86 trials, every one exit 0,
no `Exception in thread`, no `shim: fatal`, 0 aborts, 0 budget stops, 0
timeouts; S1 exec printed 354 of Forge's caught attack-future lines.
Executor median 0.393 ms over 25,320 decisions (unpinned, S1 to S6
without S4). S4's line took 446 to 548 s and its game 528 to 625 s at 6
JVMs (gate, 8 JVMs: 504 to 631 and 603 to 737). The same outcome as the
gate on every scenario.

**C1**, 5 boards chosen by rule (every fourth board in sorted order from
the third: 015_r0_g14, 015_r2_g08, 016_r0_g06, 016_r2_g00, 016_r3_g01),
seed 2026103120, one trial each: stock 3/5, exec 3/5, `plan017` 3/5; exec
and `plan017` (the same pilot on both jars) finished alike on all 5
boards; 0 executor records; 0 non-zero exits. The gate read 2, 2 and 1 on
the same boards: one trial per board moves a board either way.

**No behaviour change without steps**, the builder's check repeated on
the final jar (theirs ran `aa91088`; the later commits touch only
`StepRunner`, which is never built without `steps`): pod 2iA_Jt0d6sM, no
`--scenario`, every seat the plan pilot on G0a's version-2 plans, 2 games,
`--max-turns 12`, seed 2026103150, 3 runs of 0.17.1 (967cb71) and 3 of
`88e7564`. Over turns 1 to 12, game 1 is byte-identical in all six runs
(`entry`, `zone`, `tap`, `agent` records); game 0 is identical in five and
in all six once the order of mana taps is forgiven (the odd one out is a
0.17.1 run). Headers differ only in `shim`, `shimCommit` and `planSteps`.
Runs of either jar split from turn 13, the turn-cap kill.

### Corrections made here

- **The S1 attack split is 31 and 15, not 33 and 17** (46 attackers: all
  45 Conscripts and Kiki-Jiki). The first count read every "(n)" in the
  declaration, including the `Ai(1)` and `Ai(2)` / `Ai(3)` seat prefixes,
  the confusion CLAUDE.md gotcha 5 warns about. Fixed above and in the
  README; no figure in the verdict used it.
- **Affinity.** "All eight masks were observed on the running JVMs" had no
  saved artifact behind it; reworded above and verified live here.

### Notes for the owner and Phase B (not fixed: none changes the reading)

1. **The GO rests on S1's reading, and that reading was chosen knowing
   the dev result.** The plan's parenthetical predates every E1 game, but
   S1's step file (its `pass` outlet and `state_step`, `d1f5142`, 16:00)
   followed the builder's first S1 runs (14:46), and the PREREG fixed the
   primary reading after the dev runs had shown 0/20 kills; both documents
   say so. The binding G1 asks about did work (880/880, 440/440): what
   fails is combat, which is frozen. PARTIAL's premise, "trigger targeting
   (S1, S2) fails", does not describe S1's data, which is why GO is the
   better reading, not only the pre-registered one.
2. **A broad reading of NO-GO would bite on S2.** Its failure is Forge's
   `TapOrUntap` sub-chooser (`chooseBinary`) defeating a forced trigger in
   20 of 20 trials. The PREREG counts only `not-played` and `exception`
   aborts as sub-chooser misbehaviour, which is the measure the plan's
   risk table names; read as "any sub-chooser defeats a forced ability",
   NO-GO's first clause would hold. Stopping the executor when three
   scenarios convert 20/20 is not what that clause is for, so the PREREG's
   reading stands, but it matters for Phase B: every "tap or untap target
   permanent" line (Derevi; Kiki-Jiki with Pestermite or Deceiver Exarch)
   is not drivable until the owner rules on `chooseBinary`.
3. **Latent executor defects**, none exercised by a G1 scenario, for
   Phase B's `StepRunner` (a shim change now would void the gate):
   - an armed line is closed only when its seat next gets priority, so in
     the next turn's untap step a named trigger could still be bound or
     answered (S4's holding line ended at turn 10's first priority with no
     record in between);
   - a bound trigger skips `prepareSingleSa`, and `bind` sets only the
     first targeting ability in the chain, so a trigger with two targeted
     parts would be played with the second unset instead of going to
     `super`;
   - `budget_ms` is checked only between actions, so a loop stopped
     through `confirmTrigger` has no wall budget;
   - a line is marked tried at the turn's first main-phase priority even
     when its pieces are missing, so pieces that arrive later that turn
     cannot arm it until the next turn;
   - `pieces` does not cover every card the steps name (S4's Sol Ring and
     its library targets); Phase B's arming should.
4. **Harness, left alone because `run_g1.py` pins `run_scenarios.py`:**
   `--affinity` ignores the result of the PowerShell call and records the
   requested mask, so a failed pin would be silent; a cached trial is
   reused without checking the jar. Fix both at the next harness change.
5. **What the step data fits to these boards.** `mana_at_least: 476` is
   exactly 119 Ballista counters, 120 damage with the one already placed,
   for three opponents at 40 life: no margin, and wrong on any other
   board. S4 taps Sol Ring for mana no later step spends (the step file
   and its commits do not say why; tapping it changes which artifacts
   Clock of Omens' cost can take), fetches Battered Golem and Maskwood
   Nexus to work with Forge's cost choosers (commit `321ef57`), relies on `plan_patch`
   search targets (no step op picks a search result), and ends with a
   holding pass so the pilot's own deliberation on a 50-Treasure board
   cannot run out the clock. None of it bypasses a rule, but Phase B's
   templates need a life-relative mana stop, a search-pick channel and
   arming that checks the library.
6. **Cost, not decision time, is the CPU risk.** The gated metric is the
   executor's own compute (under a millisecond); S4 spends 2 to 3 s of
   Forge's wall time per executor action, all of it the opponents' AI at
   priority. G3's VM check has to price lines like it.
