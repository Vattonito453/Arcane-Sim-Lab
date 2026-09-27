# Sim Lab repair plan: prove it, fix what users see, then build

*Final plan, 2026-09-26, for Vincent (owner) and Richard (playtester). It starts from the "prove first" draft, which the judges scored highest. It adds every item the judges marked must-graft and fixes every blocking issue they raised. It also applies all 32 items of the completeness critique. §2.6 settles where the drafts disagreed. The closing section says how each critique item was handled.*

**Sources.**
- "Diagnosis" means `diag_result.json`: root causes RC1 to RC10, and 30 findings that were each checked adversarially. Where a finding was corrected, this plan uses the corrected claim.
- "UX #n" means problem n in `ux_final.md` §2.
- "Richard's run" means production run `sim_20260925_003803`, in the `richard/` folder.
- Figures the diagnosis marks as unverified are marked **(unverified)** here too.

**Checks made while writing this plan** (Appendix A lists them all):
- The post-run hook swallows every exception. It runs inside `Engine.simulate`, before `worker.process_one` marks the job finished.
- It is **unverified** whether `record_run` ever completes in production. It completes locally on Richard's result file, but the production snapshot shows `games: 0`.
- Both Dockerfiles use `COPY engine/*.py`, which copies the top level only. A new `engine/qa/` package would not reach production.
- The API image contains no Forge.
- Forge's shuffles are unseeded.
- Agent events carry only turn, player, event and detail. They have no `seq`.
- The card cache does not store `layout`.
- Forge treats `ActivationPhases` as a legality restriction.
- `MTG_API_KEYS` is one flat set, so any key can start a sim.
- The precon prediction model was fit on "stock Forge" games, but every production run is piloted by our plan agent.
- In Richard's run, Kess made 16 searches that put a card in the graveyard, and the plan steered 12 of them:
  - 10 binned a reanimation target or a card Kess can cast from the graveyard: Hullbreaker Horror 5, Toxrill 2, Unexpected Windfall 2, Big Score 1.
  - 2 binned Sol Ring instead of Blasphemous Act.
- The diagnosis folder is 280 MB. It holds 600 Forge `.class` files, 10 javap dumps and copies of the shim's GPL Java.
- `studies/human_ceiling` has 8 pods. Only 4 of them can serve as a holdout.

---

## 1. What is actually wrong

1. **The computer player gets a shopping list, not a recipe.** For each deck it receives every combo Commander Spellbook knows, as a bag of card names. In the 32 competitive test decks, 168 of those 238 "combos" are engines, such as infinite mana. An engine only wins with a finishing card, and the list never names one.
2. **Once it has all the pieces, it stops.** Our code then hands control back to Forge's standard player, which cannot run a loop. Kiki-Jiki's loop untapped the wrong creature 8 times out of 8. 167 completed combos made of permanents led to 5 wins on the same turn. People usually win on the turn the last piece lands.
3. **Tutors ("search your library" cards) aim at "any combo piece", not at the card this deck wins with.** Richard's Kess put Sol Ring into the graveyard twice instead of Blasphemous Act. Our Magda passed over Portal to Phyrexia in 47 of 47 searches. It won 15% of its games instead of 33%.
4. **Tutors are often cast for cards they cannot legally find.** That happened in 44% of deliberate combo tutors. In Richard's pod, Nature's Rhythm, which only finds creatures, was cast "looking for" an artifact.
5. **Forge silently refuses to play about one card in eight in a competitive deck.** Forge is the free rules engine we build on. Its authors marked these cards "the computer can't play this", and the rule applies to every player at the table. Nobody here knew. In Richard's pod such cards reached a hand 45 times and were never cast.
6. **Some test decks were not the decks we thought.** Forge dropped double-faced cards written "Front // Back": 48 card slots, including both Ral commanders. A separate name bug made every precon look as if it had no combos.
7. **For two months, each change was judged by one average win rate against plain Forge.** Most of those games were precons, where the combo code never ran. A real 18-point gain on two decks and a 7-point loss on six others averaged out to "no change". So effort went into combat, which was never the problem.
8. **The website repeats these mistakes and looks like a template.**
   - It lists 37 Spellbook engines as Richard's "win conditions", and none of them can win alone.
   - It dates every knockout to the last turn.
   - It misreads the phase for deck names like "Skrat's Revenge".
   - Every page is see-through glass over storm art, the buttons glow in capitals, and "NaN:NaN" leaks onto the screen.
9. **Forge's rules engine itself is sound.** Most of the damage is in our data, our measurement and a few hundred lines of our code. The biggest unknown is whether a small add-on can make loops finish by playing a combo's steps in order. We can test that in about four days on boards where the combo is already set up. The answer is due Fri 10/23, before anything big is built.

---

## 2. Principles for this plan

### 2.1 What we measure
- **Mechanism first, outcome second.** Every AI change names the mechanism it should move, for example "tutor casts that can legally find their piece". That metric must move before anyone reads the change's win rate.
- **Overall win share is a footnote, never a gate.** It averaged a +17.7 pp gain and a −6.8 pp loss into "parity" (RC6).
- **Every AI PR attaches the combo scorecard (§3.0), per deck and per line class.** The comparison is against a control built from the same jar. Before the scorecard exists (G0b, Thu 11/5), a PR attaches the detector metrics that do exist.
- **Every "reduce bad X" target has a paired guard,** so the target cannot be met by simply not doing X (§3.0).
- **Conversion is measured the same way in every arm.** It comes from Forge's own log and the zone stream. The shim's self-logs (`exec_step`, `line_step`) are diagnostics only.
- **Standard errors are clustered by game,** because the four seats of a game are correlated. Per-deck shares use Wilson intervals. A test bed has only two pods, so we never cluster by pod.
- **Per-deck win share gates only against catastrophe,** meaning a fall of more than 2 SE. A non-inferiority margin is used only where a PREREG states it and powers it.
- **Win speed is the share of all games decided by round N.** Draws, timeouts and turn-capped games are censored, not averaged over winners.
  - "Round" means the table round, counted as the winner's own turns.
  - The human figure of 5.0 comes from 12 games chosen by their creators, so it skews fast. It is a soft floor, not a target.

### 2.2 Where we test (cheapest first)
1. Seeded-board scenarios: minutes per question.
2. cEDH pods where combos are live, on the 16-core dev box.
3. Richard's pod: the casual regression check, and what production users actually see.
4. Production, watched by QA layer A.

**Precons are for prediction calibration only.** Precon agent arms logged 0 to 4 combo casts per 768 games (RC6).

**A cEDH holdout is drawn on day 1** from the four eligible pods (§3.0). No template, tier or override is tuned on it before G3. Its acceptance lines are scored blind, once.

### 2.3 How we change the engine
- **One variable per arm.** New shim mechanisms ship behind plan-data flags. The control and the arm run the identical jar and differ only in JSON.
- **Every run records its provenance:** jar version and commit, plan hashes, flags and `overrides_version`.
- **Production deploys pin the shim version, and preflight checks it.** Richard's run used 0.15.0, which still has the attack re-ask loop that 0.16.0 fixed.
- **Pre-register every experiment.** `studies/<exp>/PREREG.md` states the hypothesis, metric, threshold, n, and what happens on pass and on fail. It is committed before the run starts, and the results file quotes it.
- **Legal boundary.**
  - Policy (values, lines, steps, windows, lists) is data produced by Python.
  - The shim gains only generic mechanisms that ask Forge's own public legality checks (`canPlay`, `canPayCost`, `isValid`, `canPlaySa`, `canTarget`). It contains no card names and no scoring.
  - A lint fails the shim build on card-name string literals.
  - We never patch or fork Forge and never edit its card scripts.
  - Nothing Forge-derived is committed to our repo. That covers card-script extracts, disassembly, class files and copies of the shim's Java, including inside evidence folders. Anything Forge-derived is computed at runtime in the worker or kept off-repo.
- **Harm-removal exception.** A change may ship before the full scorecard exists only if all of these hold:
  - it removes a behaviour Richard reported, **or** it turns a dial off to restore stock behaviour, **or** it is the 0.16.0 re-ask-loop fix;
  - each mechanism sits behind its own flag;
  - each has a metric set by the rules and checked against Forge's own record (for example, "did the search offer the piece");
  - it passes a pre-registered gate. Where two jars must be compared (0.15.0 against 0.16.0), the gate is an unpaired check that a jar-to-jar comparison can support; otherwise it is a same-jar control.

  This exception covers the week-2 tutoring hotfix, E8 (combat dials set to stock values), decision 8 (random block skips off) and R0's 0.16.0 pin. It covers nothing else.

### 2.4 How the system learns
- **Learning uses only ground truth that does not depend on who won in the sim:**
  - rules-determined facts, meaning what Forge legally offered or allowed;
  - scenario results;
  - judgements from Vincent, Richard and other playtesters;
  - human game traces.
- **Sim wins are outcomes, not labels.** Learning from them teaches Forge's combat bias: combat decided at most 2 of 12 human wins, against 80 to 90% of sim wins.
- **What Forge's AI chose to do is pilot behaviour, not ground truth.** Example: "Tainted Pact exiled at most 1 card in 168 of 168 resolutions" is the AI declining to repeat. It goes to the pilot-defect queue. It never justifies disabling a line.
- **Changes to plan data come in two classes:**
  - Compiler inputs change only by a PR with tests.
  - Overrides are bounded, validated and watched after merge.
- **Cold start.** A deck with no history plays the validated defaults (plan_feedback's cold-start invariant).
- **Richard's texts are ground truth.** Each verified complaint becomes a detector or a scenario, and the next run must pass it.

### 2.5 What we stop, from day 1
- No new combat, personality, hold or attack-targeting features or study arms before G4. The only exception is dials turned off under the harm-removal exception.
- No acceptance based on overall win share, and no combo or tutor study on precons.
- No Pilot's notes before the tutor-weight fix.
- No LLM output changes behaviour without a human merge.
- "Humanized" stops being a product claim.
- No `next build` while a dev server is running (CLAUDE.md).

### 2.6 Decisions this plan makes between the drafts

| Question | Drafts disagreed | This plan |
|---|---|---|
| Behaviour first or instruments first | trust_first shipped a 7-mechanism shim in week 1; prove_first held pilot fixes to week 4 or 5 | **Both, sequenced to capacity.** Week 1 fixes what is untrue on screen and in the decks. Week 2 builds the tutoring hotfix, one flag per mechanism, with only the detector that judges it. G0a is Tue 10/13, and the hotfix ships in R1 on Fri 10/16. Richard sees behaviour change in week 3. |
| Exile-destination guard | trust_first blocked steering into Graveyard **or Exile** | **Graveyard only.** In Richard's run the two exile steers were "exile it, you may play it" effects. There the plan's pick (Sol Ring over Island, Big Score over Mountain) was better than stock's. |
| KB name and location | `kb/` vs `simkb/` | **`simkb/` in the repo holds only compiler inputs, tools, scenarios and overrides,** all code-reviewed. Generated and human data (judgements, digests, deck profiles, Richard's texts, traces) lives in a **private data repo** that is never public and never merged. Per-run output lives at `$MTG_DATA_DIR/simkb/`. |
| Line model | per-run DeckLines file vs plan fields | **One `lines_<run>.json` per run,** referenced from `result.meta.lines_file`. The pilot, the product and QA all read it. A recompile never rewrites what a past pilot was given. |
| Step scripts | a grammar over Spellbook's English vs templates | **Templates plus scenario checks.** Spellbook's English is never parsed. A line becomes "executable" only when its scenario passes. |
| Tutor reach | a hand table of about 150 tutors vs Forge's own check | **Forge's own check.** From 0.17.0 the shim calls `Card.isValid` against the tutor's `ChangeType` at decision time and logs `reach=true/false`. The Python ChangeType reader is used only to backfill old runs. |
| Executor vs readmission | separate mechanisms | **One mechanism.** Returning a data-named SpellAbility from `chooseSpellAbilityToPlay` after `canPlay` and `canPayCost` bypasses Forge's RemoveDeck filter; that is how the shim already casts Consultation. E1 builds it once. Readmission is data classes on the same path. |
| Research baseline after readmission | replace stock vs keep stock | **Keep pure stock as the frozen control.** Add stock+readmit as an extra arm, defined with every dial at its stock value. It must pass an A/A check against stock before use. |
| Tutor timing mechanism | `putParam("ActivationPhases")` | **The shim's own tutor window first.** `ActivationPhases` is read by Forge's `SpellAbilityRestriction`, so changing it could change legality. It is used only if the harness proves it steers AI timing alone. |
| Where the QA hook runs | inside the sim call | **From `worker.process_one`, after `jobqueue.finish`,** as a detached, niced subprocess. A crash or a slow detector can never block or fail a run. |
| Standard-error unit | pod-clustered | **Clustered by game.** Two pods cannot give a cluster variance. |
| Holdout | 2 of the human_ceiling pods | **Drawn on day 1 by lot, from the 4 eligible pods.** At least 30 assembled drivable lines are required at G3; if short, we play more games. WS8 targets are computed on dev decks only. |
| Executor go/no-go date | week 2 vs week 3 | **Fri 10/23 (week 4).** Before it: the harness spike (Wed 10/14) and your sign-off on the adapter checklist (Fri 10/16). |
| Validation gate timing | week 4 vs week 9 | **Fri 11/20 (week 8).** It comes after the truth patch and the feel changes, and before any phase-2 build. It moved from week 4 because of the capacity re-total. |
| Detector trust bar | 80% vs 90% precision | **At least 26 of 30 judged flags correct** (Wilson lower bound about 0.70). Rules detectors are validated automatically against Forge's record, so human labels are spent only on judgement detectors. |
| Reviewer scope | flagged moments only | Flagged moments, plus a **blind random sample of unflagged decisions** (20% of the nightly budget) to estimate recall and find new kinds of mistake. |
| Evidence copy | copy everything | **An allowlist:** our own `*.py`, `*.md` and small JSON results, each at most 1 MB, with no Forge-derived content. Everything else goes to an off-repo archive. |

---

## 3. Workstreams

**Effort** is in developer-days: one Claude Code session supervised by Vincent. Sizes: S = 2 days or less, M = 3 to 6, L = 7 or more.

| WS | Name | Addresses | Effort | Weeks |
|---|---|---|---|---|
| WS0 | Day-one safety and production truth | blocking issues, RC4, RC6 | S, 2 | 1 |
| WS1 | Measurement and QA layer A analyzers | RC6, measurement list, UX #1, #2 | L, 14 | 1–2, 5–6, 10, 15 |
| WS2 | QA agent layer B, knowledge base, overrides | owner request, RC4, RC6, UX #12 | L, 10 | 3–4, 7–12 |
| WS3 | Seeded-board scenario harness | RC1 unknown, RC6 | M, 3 | 3 |
| WS4 | Input fidelity and the Forge index | RC9, RC3 disclosure | M, 3 | 1–2 |
| WS5 | Tutoring: reach, destination, targets, timing, Magda | RC4, RC5, RC7, Richard | L, 9 | 2, 6, 10, 17 |
| WS6 | Forge refusals (readmission data and E3) | RC3 | M, 3 | 8–9 |
| WS7 | Oracle sequencing and line protection | RC8, RC10 (protection) | M, 3.5 | 12 |
| WS8 | Combo data rebuild (DeckLines) + G-lines | RC2, RC4, RC8, UX #2 | M, 6.5 | 7–8 |
| WS9 | Combo executor and its go/no-go | RC1, RC8 | 4 + 9.5 | 4, 9–14 |
| WS10 | Combat clean-up; GPL constant audit | RC10, boundary drift | S, 3 | 6, 15–16 |
| WS11 | Product honesty (truth patch) | UX #1, #2, #4–#6, #10, #11; product problems | L, 8 | 1–5 |
| WS12 | UX phases | UX #2, #3, #7–#9, #12–#15 | 11.5 + 25 | 5–8, 10–12, 15–21 |
| – | Overhead: 9 PREREGs and write-ups, 8 releases, doc updates, precon calibration checks, baseline re-measure | – | 13 | throughout |

The total is about **128 developer-days**, or about 118 if the executor is a NO-GO. The core through G3, including UX phase 1 and the validation gate, is about 95. §4.5 gives the capacity rules and the cut order.

---

### 3.0 Shared definitions

**Test beds.** Wall times assume 8 parallel JVMs and the measured 240 s median game.

| Name | What | Per arm | Wall time |
|---|---|---|---|
| Scenario suite | S1–S9 plus control C1 (WS3) | 20 trials per scenario | about 25–50 min (measured at G-harness) |
| cEDH-A | agent_viability pods `n7WpsqsZtdQ` (magda, selvala, tymna_thrasios, rog_ishai) and `2iA_Jt0d6sM` (derevi, godo, nadu, rograkh_silas). Every seat is a plan seat for mechanism arms. | 64 games (512 plan seat-games) | about 35 min |
| cEDH-A/stock | The same pods: 1 plan seat vs 3 stock (or 3 stock+readmit), rotated | 96 games | about 50 min |
| cEDH-dev | `5A6o18Bra0Y`, `OuY6mdiXbHU` and the 2 eligible pods not drawn for the holdout; all plan seats | 8 games per pod | about 25 min |
| cEDH-holdout | 2 pods drawn by lot on Mon 9/28 from `B421mac67IE`, `Bq-nFi0f1jA`, `CxKMqO36DdM`, `sZA0KqXCGrY`. These are the only pods that share no deck with cEDH-A and are not used by the scenario suite. Recorded in `studies/holdout/HOLDOUT.md`. Untouched until G3. At G3 it must yield at least 30 assembled drivable lines. If it does not, play 16 more games per pod, up to 64. If it is still short, add Vincent's 8 fresh cEDH lists as a second holdout. | 16–64 games per pod | 20–80 min |
| Richard pod | Kess, Reanimator; Skrat's Revenge; Stella Lee, Wild Card; Krenko Goblins. All plan seats, as in production. | 16 games | about 10 min |
| Precon-8 | Existing precon pods | as today | calibration only |

**Pairing.** Library shuffles and stock seats use Forge's unseeded `MyRandom` (`SimShim.java:346-351`).
- Shim 0.17.0 adds a `seedForge` flag that calls `forge.util.MyRandom.setRandom(new Random(seed))` per game. This is one call to a public API.
- E2 checks that the same seed gives the same opening shuffles and hands. It runs within 0.17.0, because 0.16.0 cannot seed.
- Until E2 passes, every n is sized as unpaired. After it passes, arms share seed lists, which pairs opening hands. Games are expected to diverge after the first differing decision.

**Arm-neutral metric definitions** (implemented once, in `engine/qa/`):
- **Assembled.** At some zone record, every piece of a reference line is in the zone the line requires.
  - Pieces are keyed by cardId, so clones count.
  - Graveyard and exile zones count where the line needs them.
  - An Oracle whose enter-the-battlefield (ETB) trigger is already spent does not count.
- **Executed**, from Forge's log only. Any one of:
  - at least 5 activations or trigger resolutions of line pieces in one turn;
  - an extra combat;
  - a spell win that names a piece.
- **Converted same turn / within round.** A knockout whose cause matches the line's band, in the same own turn as assembly or within one table round.
  - Finisher band causes: spell win, drain, non-combat damage, poison, mill.
  - Combat finisher band cause: combat damage.
- **`won_after_assembly`** is kept only as an unbadged correlation column.
- **Same reference for both arms.** Both arms of an experiment are scored against the same reference lines file and the same drivable classification. For G3 that classification is frozen at G-lines.

**The combo scorecard** (`studies/scorecard/scorecard.py`) is computed per deck and per line class. The classes are: completed by casting, activated loop, needs a trigger target, graveyard loop, flagged piece, no payoff.

| Block | Metric | Today (source) |
|---|---|---|
| Funnel | sighted → pursued → assembled → executed → converted | Permanent completions: 167 → 5 same-turn wins (3.0%). Spell completions: 49 → 24 same-turn (RC1). |
| Speed | Share of all games decided by round 6 (draws censored); mean win round (winner's own turns) | Plan wins by round 6: 15/93. That is a share of plan wins, not of games; it is recomputed in the target's unit at G0b. Stock: 6/308. Mean win round: plan 13.1, stock 12.7, humans 5.0 (12 creator-picked games). Upper bound if every line fired: 8.8 (RC1, RC6). |
| Method | Lethal event: combat, non-combat damage, drain, poison, commander, alternate win, deck-out. "Timed out while looping" is kept separate. | On the newest run, 7 of 15 "combat" finals were not combat, and 13 deck-outs were unclassified (measurement). |
| Tutors | Legal reach (shim `reach=` from 0.17.0); destination use; cast before main phase 2; pick type; fetched card used the same turn; early engine fetches; overrides of a closer | Unreachable: 316/718 (44%). Stock library-top tutors cast before main phase 2: 0/269. Stock generic fetches were creatures 95% of the time (unverified). Stock hand-tutored cards unused that turn: 51/72. Early engine fetches: plan 0/175 vs humans 9/18 (unverified). Steers onto non-drivable lines that override stock's closer pick: Magda 47/47 (68/68 across 5 arms) (RC4, RC5, RC7). |
| Refusals | Flagged cast rate; flagged activation rate; unsupported cards | Flagged cast rate: stock 5.2% (178/3430), plan 24.6%. Printed flagged permanents activated: 1/459 (RC3). |
| Self-harm | Self-decks; losses to one's own spell | 14 Consultation self-decks (RC8). Own-spell losses: plan 8/256 vs stock 1/768 (unverified). |
| Interaction | Share of assembled lines that faced a response within a round | 31–39% faced one (unverified). |
| Lines | Share of shipped lines that can win; decks with at least one win line; human combo wins whose line is in the plan | 70/238. 25/32. 5/11, where 3 of the misses are missing outlets (RC2; verified finding 20, corrected). |
| Outcome | Per-deck win share with Wilson interval; pooled share with game-clustered SE (footnote) | Oracle decks +17.7 pp; the other six −6.8 pp (RC6). |

**Guards (anti-gaming).** Every "reduce bad X" target carries its guard:

| Target | Guard |
|---|---|
| Unreachable tutor casts ↓ | Tutor casts per tutor drawn on plan seats ≥ 50% (stock casts 67%: 594/892) |
| Graveyard steers onto cards with no graveyard use ↓ | Graveyard-destination searches still pick a card. Steers onto reanimation targets and cards castable from the graveyard are reported as expected behaviour, not penalised. |
| Counters on mana rocks cast after round 3 ↓ | Counters cast per seat-game ≥ 80% of control. Counters on line pieces and commanders not down. Early fast-mana counters are not counted. |
| Needless chumps ↓ | Blocks that kill the attacker and survive ≥ 90% (96.3% today). Deaths below dangerLife not up. |
| Moved attackers dying ↓ | Combat damage dealt per seat-game ≥ 90% of control |
| Self-harm ↓ | Flagged cards cast ≥ 50% of those held |
| Self-decks ↓ | Oracle wins per Consultation cast ≥ control. Consultation casts down by no more than 25%. |
| Win round ↓ | Floor at the human 5.0. "Faced a response" reported. An opponent arm with readmission. |

---

### WS0: Day-one safety and production truth

**Goal.** Nothing we build on is silently broken, at risk of being wiped, or quietly vendoring Forge.

**Addresses.** The blocking issues: evidence in Temp, the dead hook, the shim version, the nudge. Also RC4 (plan_feedback nudge) and RC6.

**Tasks**
1. **Copy the evidence, by allowlist.** The scratchpad lives in `AppData\Local\Temp` and can be wiped.
   - **Commit to `studies/diagnosis_2026-09/`:**
     - the 276 prototype `*.py` and `*.md` files;
     - small JSON results we produced;
     - `diag_result.json`, `ux_final.md`, `ux_result.json`, `verified_dump.txt`, `syn.txt`;
     - `ux/` files of 1 MB or less.
   - **Never commit:**
     - Forge `.class` files (`forge_leverage/jarx/`);
     - javap dumps (`*.javap.txt`, `AiController.javap.txt`, `ChangeZoneAi.txt`);
     - Forge card-script caches and indexes (`scripts_cache.json`, `forge_card_index.json`, `fidx.json`, `allai.txt`);
     - `forge_leverage/shimcopy/`;
     - `.pyc` and `.pkl` files;
     - `gs/` and `gs2/` (extracted Forge classes);
     - any file over 1 MB.
   - **Archive the full folder off-repo:** `C:\Users\Vatto\simlab-archive\diagnosis_2026-09.zip`, with its SHA-256 recorded in the README.
   - **Richard's folder** (their decklists and the 2.4 MB result) goes to the archive now, and to the private data repo once it exists (W9).
2. **Draw the holdout** (`studies/holdout/HOLDOUT.md`), before any template or tier work.
3. **Read-only production checks.** Put them in a script and copy it over with scp; PowerShell eats `$(...)` when commands are inlined over gcloud ssh.
   - `preflight.py --files`
   - the deployed shim version and `/opt/simlab-forge-shim/COMMIT`
   - summary statistics of `/data/plan_feedback.json`
   - a count of " // " names in `/data/decks`
   - `record_run` reproduced **inside the worker container**, against a copy of the real `/data/plan_feedback.json`, capturing the traceback
   - when, and from which container, `richard/cache/plan_feedback.json` was taken, if that can be established

   Locally, `record_run` completes on Richard's exact result file. So a production failure would be environmental (imports, data dir, permissions), or the snapshot was taken before the run finished. The finding stays unverified until this check reports.
4. **Hook hardening.** The `record_run` block (`mtg_engine.py:259-268`) logs its traceback to stderr; the process runs with `-u`. A test forces it to raise and asserts two things: the error is logged, and the result is still returned.
5. **Nudge off.** Gate `plan_feedback.apply_to_plan` (`deck_plan.py:495-501`) behind `MTG_PLAN_FEEDBACK_APPLY`, default 0. A test checks that the plan is byte-identical with and without a synthetic store.
6. **Pin production to 0.16.0 in R0.** Its dials default to 0.15.0 behaviour, and it fixes the attack re-ask loop.
   - **Gate:** a Wednesday-night Richard pod run, 16 games on 0.15.0 and 16 on 0.16.0. Pass means re-ask events at 0, no crashes, and the other agent-event rates within 2 SE.
   - **Preflight asserts** the shim is at least the pin and `MTG_PLAN_FEEDBACK_APPLY` is off. From R1.1 it also asserts that the latest finished run has a `qa.json`.
7. **Freeze note.** Record the freeze in `tasks/README.md` and park follow-ups to tasks 21, 23 and 24.
8. **Correct the refuted claims.**
   - "Stock never casts tutors" in `SIM_CALIBRATION.md` becomes "stock casts about 67% of the tutors it draws, in main phase 2".
   - "Zero precon variants": `deck_plan.py:160-163` and `:395-397`, `tasks/20:323-326`, `run_pilot.py:4-5`, `agent_viability/RESULTS.md:10-11`.
   - "Forge cannot pilot storm" (`human_ceiling/RESULTS.md:15`) becomes "untested: Ral ran without its commander".
   - Stock mean win round 10.9 becomes 12.7. Fix the human_ceiling round unit.
   - Annotate task 21's fourth criterion and the cc8c446 results as "measured on pre-0.16.0 arms (attack re-ask loop present)".
9. **Do not commit or use `studies/precon_predict/model_runs_agent.json`.** It was fit on pre-0.16.0 arms.

**Boundary.** Python and ops only.

**Effort.** S, 2 days.

**Depends on.** Nothing.

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| Evidence in the repo | 0 files | scripts and our results committed; the allowlist check passes; archive hash recorded | `check_allowlist.py` |
| Forge-derived or shim Java files committed | – | 0 | allowlist check (extension, size, content markers) |
| Silent post-run hook failures | all (bare `pass`) | 0; traceback in container logs | VM logs |
| Cause of any `record_run` failure | unverified | named, or "completes in the worker container", in `prod_check_0928.md` | VM |
| Production shim version | 0.15.0 | 0.16.0 in R0, then the release pin; asserted by preflight | preflight |
| Nudges applied | on (store empty) | 0; flag asserted | preflight |

---

### WS1: Measurement and QA layer A analyzers

**Goal.** The numbers we read are true. They can see combos, tutors, refusals and board state. One package computes them, and the product, the scorecard and the QA agent all share it.

**Addresses.** RC6; the diagnosis's measurement problems; product problems 1, 3 and 4; UX #1 (knockout dating) and UX #2 ("converted").

**Tasks**
1. **New `engine/qa/` package, stdlib only.**
   - Each detector exposes `detect(ctx) -> (metrics, flags)`.
   - `ctx` is built once per run from:
     - the result file and, when present, the raw shim JSONL;
     - the plans and `lines_<run>.json`;
     - `board.build`;
     - the warm card cache (no fetch);
     - the Forge index (WS4).
   - Each detector is ported from a diagnosis prototype and marked either rules-determined or judgement.

   | Detector | Ported from | Kind | Week |
   |---|---|---|---|
   | `knockouts`: `[{player, turn, round, cause, by, card, seq, basis}]`, including deck-outs ("has lost trying to draw cards from empty library"); plus the turning point | `product_surface/lethal*.py`, `research_meta/kill_method.py`, `win_round.py` | rules | 1–2 |
   | `tutors`: reach (the shim's `reach=` on new runs; ChangeType index plus Forge's `search_seen` offers for backfill); destination use; X=0; phase; pick type; used the same turn; overrides of a closer | `combo_execution/tutor_reach.py`, `tutoring/parse_tutors.py`, `miss_reason.py`, `gate_state.py`, `forge_leverage/scripts/tutorphase.py`, `tutorpick.py` | rules | 2 |
   | `funnel`: the §3.0 definitions | `combo_execution/funnel.py`, `conversion_audit.py`, `verify/vfunnel.py`, `verify/conv/*` | rules | 5 |
   | `lines`: band, drivable, flagged or unsupported pieces, duplicates | `verify/resource_lines/classify.py`, `outlets_check.py` | rules | 5 |
   | `refusals`: flagged cards held, cast and activated; unsupported cards | `combo_data/forge_ai_flags.py`, `castrate.py`, `removedeck_audit.py` | rules | 5 |
   | `self_harm`: self-deck, loss to one's own spell, Oracle ETB spent | `play_logic_general/selfkill.py`, `combo_execution/oracle_audit.py` | rules | 5 |
   | `runaway_loop`: at least 200 stack items in a turn, or a clock-out while looping | `research_meta/loop_bias.py` | rules | 5 |
   | `response`: the assembled line faced a response within a round | new | rules | 5 |
   | `timeline`: board state per turn and seat (see WS2 schema); a board snapshot at each knockout; `board_accuracy` | `board.py` | rules | 5 |
   | `misplays`: needless chump; suicide move; counter on a mana rock after round 3; assembled engine left idle for 2 own turns; cleanup discard of a line piece; castable permanent held with unspent mana; bouncing one's own key piece; wasted ritual | `play_logic_general/detect*.py`, `combat_death.py`, `counters.py`, `ritual.py`, `verify/vloops.py` | judgement | 15 |

2. **`analysis.py` switches to `qa`** (W6).
   - Line 282 uses `board.build` whenever `zones` exist.
   - `converted_games` (:336) is replaced by `executed` and `converted_same_turn`. `won_after_assembly` stays as an unbadged column.
   - The note at :389 becomes path-aware.
   - `win_method` comes from `knockouts`.
   - `scorecard._death_rounds()` (`scorecard.py:62-71`) uses `knockouts`.
3. **Loop timeouts** get their own flag, `timed_out_looping`, reported separately from draws.
4. **`studies/scorecard/scorecard.py`** covers the §3.0 blocks plus the guards. It has a `--control`/`--arm` diff that outputs markdown and JSON.
5. **Port test (G0a for `tutors`, G0b for the rest).** 219 of the 276 prototype scripts hard-code study paths.
   - Each figure gets a manifest, `studies/scorecard/manifests/<figure>.json`, naming its exact run files and their md5s.
   - Each ported detector must reproduce its figure within ±5% relative, or its results are held:
     - 316/718 unreachable tutor casts;
     - 167 → 5 same-turn wins;
     - Magda 47/47 overrides;
     - stock flagged casts 178/3430;
     - 14 self-decks;
     - 19/86 text-vs-zone flips.
   - Publish `studies/scorecard/BASELINE.md`. It includes the speed baseline recomputed as a share of all games.
6. **Falsification clause.** If the recomputed baseline contradicts the diagnosis's ranking (for example, conversion is not the largest gap), the weeks after G0b are re-planned before building.
7. **Seq stamping** (W10). The shim stamps `seq` on zone records, **`agent_events` and `search_seen`**, and `readapt.py` carries it through.
   - Until then, flags anchor by `(game, turn, player, agent_event_index)`.
   - Old runs keep that anchor.
8. **Budget test.** Analyzer p95 under 10 s on the largest local result (5.7 MB), niced, as a stand-in for the 2-vCPU VM.

**Boundary.** Python only. Seeding and seq stamping are shim logging and one public-API call.

**Effort.** L, 14 days: skeleton and knockouts 1.5, tutors 1.5, funnel and lines 1.5, refusals/self-harm/runaway/response 1.5, timeline 1, misplays 2, analysis switch and scorecard 1.5, manifests and BASELINE 1.5, seq stamping 2.

**Depends on.** WS4's Forge index (for `tutors` backfill and `refusals`).

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| Port test | – | every listed figure within ±5%, each with a manifest | corpus backfill |
| Text-vs-zone disagreements on shim runs | 19/86 | 0 | 128 cEDH games |
| "Converted" readings with no execution evidence | 79 of 115 badged rows are pure engines | 0 (field removed) | cEDH corpus |
| Non-combat finals labelled combat | 7/15 | 0 | newest product run |
| Knockout hand audit (before the R1 UI) | – | ≥ 95% agreement on 40 knockouts across 3 runs | W3 audit |
| Turning-point hand audit (before the R1 UI) | – | ≥ 16/20 games agree with a human reading; otherwise it ships as "biggest swing" or is held | W3 audit |
| Deck-outs classified | 0/13 | 13/13 | corpus |
| Detector precision | unknown | rules detectors ≥ 98% agreement with Forge's record; judgement detectors ≥ 26/30 before any acceptance or UI use | `mistakes/*/stats.json` |
| Analyzer runtime p95 | – | under 10 s | largest result |
| Same seed gives the same opening hands (E2, within 0.17.0) | not seeded | 10/10 pairs identical up to the first decision | dev box |

---

### WS2: QA agent, knowledge base and overrides (the owner's request)

**Goal.** Every sim is analysed automatically, directly from the sim data: board state, moves and outcomes. Flagged moments get a player's judgement. Confirmed judgements become reviewed, bounded plan data and regression scenarios. The engine gets smarter from ground truth, not from sim wins.

**Addresses.** The owner's request; RC6; RC4; product problem 11 ("misplays unflagged"); UX #12 ("Flag this play").

#### Layer A: deterministic, server-side, every finished run (R1.1, Fri 10/23)

1. **Hook.**
   - In `worker.process_one`, **after** `jobqueue.finish`, the worker launches `python3 -u engine/qa/run.py <result>` as a detached subprocess. It is niced and has a 120 s timeout.
   - It never raises into the worker and never delays "finished".
   - It handles salvaged, partial and killed runs.
   - It writes `$MTG_DATA_DIR/simkb/runs/<result_stem>/qa.json`.
   - Each detector has its own time budget, and detector errors go into `qa.json.errors`.
   - An idle-loop sweeper in `worker.py` re-runs QA for any finished run that has no `qa.json`. This makes QA idempotent.
2. **Images.**
   - `Dockerfile.worker` adds `COPY engine/qa/ /app/engine/qa/`, `COPY simkb/linec/`, `COPY simkb/lines/` and `COPY simkb/overrides/`.
   - `Dockerfile.api` adds `COPY engine/qa/` and `COPY simkb/linec/`.
   - `engine/*.py` copies the top level only; this is the same trap the Dockerfile comment records for `engine/models/`.
   - Preflight imports `qa` and `combo_bands` in both containers and checks that `band_map.json` exists.
3. **Read routes.**
   - `GET /results/{file}/qa` is public, with the same filename validation as the sibling routes. It contains no human flag notes.
   - `GET /qa/queue?since=<cursor>` requires an API key.
4. **Review queue.**
   - Flags above a severity threshold are written to `$MTG_DATA_DIR/simkb/review_queue/auto/<flag_id>.json`.
   - The cap is 30 per run, stratified by detector, so one noisy detector cannot fill the queue.
   - Human flags rank first.
5. **"Flag this moment"** (R1).
   - `POST /flags` writes `review_queue/human/<id>.json` with `{run, game, anchor, turn, player, note, reporter}`.
   - It accepts keys from a new **flags-only key set, `MTG_FLAG_KEYS`**. Today `MTG_API_KEYS` is one flat set, and a key there could also start 4 GB sims.
   - Vincent generates Richard's flags key.
6. **Preflight.** `preflight.py --files` fails if the latest finished run has no `qa.json`, or its `qa.json` has `errors`.
7. **Backfill CLI.** `py engine/qa/run.py --all` works on the dev box and on the VM.

**`qa.json` (key fields)**
```jsonc
{ "schema": "simlab.qa/1", "analyzer": "qa/0.1.0", "run": "<result file>", "basis": "shim-zones|stdout",
  "board_accuracy": {"basis": "shim-zones", "exit_match_rate": 1.0, "assumed_share": 0.0},
  "pilot": {"agent": "simlab-forge-shim/0.17.0", "commit": "<sha>", "flags": {"fix.tutorReach": true},
            "plan_hashes": {"<deck>": "<sha1>"}, "lines_file": "lines_<stamp>.json", "overrides_version": "2026-12-09.1|null"},
  "fidelity": {"unsupported": [{"deck","card","reason"}], "commander_missing": [], "commander_flagged": []},
  "games": [{"n": 1, "method": "poison", "timed_out_looping": false,
             "knockouts": [{"player","turn","round","cause","by","card","anchor","basis",
                            "board": {"<seat>": {"life","poison","creatures","power","commander_zone"}}}],
             "turning_point": {"turn": 8, "card": "Ezuri's Predation", "basis": "zones|inferred", "audited": true},
             "timeline": [{"turn": 8, "seat": "Skrat's Revenge", "life": 31, "poison": 0, "cmdr_dmg": {"Kess, Reanimator": 0},
                           "hand": 4, "lands": 7, "mana_sources": 9, "creatures": 6, "power": 14,
                           "commander": "battlefield", "basis": "zones|inferred"}]}],
  "decks": {"<deck>": {
     "funnel":   {"sighted": 9, "assembled": 3, "executed": 1, "converted_same_turn": 1, "faced_response": 1, "by_class": {}},
     "tutors":   {"casts": 14, "reach_ok": 9, "offered_by_forge": 9, "dest_useful": 12, "x_zero": 0, "pre_main2": 3,
                  "picks": {"creature": 5, "line_piece": 6, "closer": 1}, "closer_overridden": 0, "used_same_turn": 4, "cast_per_drawn": 0.7},
     "refusals": {"flagged_held": 7, "flagged_cast": 2, "flagged_activated": 0, "unsupported": []},
     "lines":    [{"id","band","drivable","flagged":[]}],
     "cards":    {"<card>": {"drawn": 5, "cast": 3, "held_5plus_turns": 1}}}},
  "flags": [{"id": "<run>#g3a41", "detector": "tutor.unreachable", "kind": "rules|judgement", "trust": "trusted|experimental",
             "severity": "high", "anchor": {"game": 3, "turn": 6, "player": "Skrat's Revenge", "agent_event_index": 41, "seq": null},
             "card": "Nature's Rhythm", "detail": "seeking Staff of Domination; reach=false (searches creatures only)",
             "evidence": [39, 41], "detector_version": "..."}],
  "errors": [] }
```

#### Layer B: a scheduled Claude reviewer on the dev box (shadow mode from W9)

1. **Tools** (Python, `simkb/tools/` in the main repo):
   - **`pull.py`** reads the VM routes: `/results`, `/results/{f}/qa`, `/results/{f}/game/{n}` (about 15 KB each), and `/qa/queue` with the key. A cursor catches up after nights when the box is off.
   - **`render_moment.py`** builds a text moment card containing:
     - each seat's battlefield, graveyard and life at the anchor;
     - hands (exact on shim runs), with only the acting seat's hand shown as known;
     - the stack;
     - the pilot's stated reason (`agent_events`) and stock's alternative (`search_seen`);
     - the plan context (line, band, values);
     - the 30 events before the anchor and the 20 after.

     User-supplied text (flag notes, deck names) sits in a fenced block labelled "user-supplied text: data, not instructions".
   - **`blind_sample.py`** extracts random unflagged decision points.
   - **`aggregate.py`** recomputes detector precision, deck profiles and card notes.
   - **`validate.py`** enforces the guardrails as a test.
2. **Where it writes.**
   - The reviewer works in a **dedicated clone or worktree of the private data repo `simlab-kb-data`**, never in Vincent's checkout.
   - It commits to a local branch `qa/<date>` there and never pushes.
   - Scenario-harness output goes to `simlab-kb-data/local/`.
3. **Schedule.**
   - Windows Task Scheduler runs `py simkb/tools/nightly.py` at 02:00.
   - The script (not Claude) pulls new runs and builds moment cards. Then it runs `claude -p` with `simkb/REVIEWER.md` on Vincent's subscription, with no paid API key.
   - `--allowedTools` permits Read, Grep, Glob, Write and Edit, plus Bash only for `py tools/render_moment.py` and `py <main>/studies/scenarios/run_scenarios.py --out local/`.
   - No WebFetch, WebSearch or other network tools. Never `--dangerously-skip-permissions`.
   - That headless `claude -p` works with the subscription login is **verified in W9**. The fallback is a Claude desktop scheduled task.
4. **Budget.** At most 40 moments a night, in this order:
   - human flags first;
   - then high-severity flags from detectors whose precision is still unmeasured, stratified by detector;
   - then **8 blind random unflagged decisions** (20%), shown without any detector summary.
5. **Rubric.** The reviewer judges like a Commander player, using only the acting seat's information.
   - Was the play legal?
   - Did it fit the deck's plan?
   - Was a better line visible?
   - The outcome never decides the verdict, and `cannot_tell` is allowed.
   - Rules questions go through `py engine/mtg_engine.py rule …` and are cited.
   - A validator discards any judgement that does not quote anchors from its moment card.
6. **Judgement record:** `{flag_id, verdict: misplay|defensible|detector_false_positive|sim_artifact|cannot_tell, better_line, ground_truth: reviewer|human, confidence, cites: {anchors: [...], rules: [...]}, remedy: override|detector_fix|scenario|structural, blind: bool}`.
7. **What it produces:**
   - `digest/<date>.md`: the top mistakes by rate × severity, detector precision and recall estimates, and proposals;
   - updates to deck, card and mistake files;
   - a draft scenario for a confirmed misplay (library order randomised), which it may run locally and attach;
   - an override proposal (`overrides/proposed/`) only when at least 3 **human-confirmed** judgements share a root cause.
8. **May / may not.**
   - **May:** write inside its data-repo worktree; mark detector false positives; draft scenarios; run the local harness.
   - **May not:**
     - touch the main repo, `engine/`, `web/`, `deploy/`, the shim repo or `plan_overrides.json`;
     - push or merge;
     - call any production POST route;
     - start production sims;
     - install anything;
     - use a sim win or loss as evidence;
     - judge from hidden information.
   - **Enforcement.** After each run, `nightly.py` checks that `git status --porcelain` on the main repo is unchanged, and that data-repo changes stay inside the allowed folders. If either check fails, it disables the job.
9. **Calibration before trust.**
   - Vincent labels 20 moments (W11). Richard labels 30 (W12–W14), asynchronously, as a list of links they answer by text.
   - The reviewer's judgements count in digests only when Cohen's kappa is at least 0.6 on those 50 (G5, Fri 1/8).
   - After that, 20 blind moments are re-labelled each month.

#### Knowledge base layout

```
MAIN REPO: simkb/                         code-reviewed; no user data; baked into images where noted
  README.md  SCHEMA.md  REVIEWER.md
  tools/            pull.py  render_moment.py  blind_sample.py  aggregate.py  validate.py  nightly.py  trace_entry.py
  linec/            COMPILER INPUTS (PR + tests): band_map.json (incl. expert band overrides)  shapes.json
                    suppressors.json  protection.json  readmit.json  outlets.json (only if measured useful)   -> API + worker images
  lines/<line_id>.json   COMPILER INPUTS: step script + scenario evidence (study decks only)                   -> worker image
  scenarios/<id>.json    COMPILER INPUTS: seats, zones, life, phase, expected result
  overrides/plan_overrides.json  overrides/CHANGELOG.md   BOUNDED OVERRIDES (PR + validator)                    -> worker image

PRIVATE DATA REPO: simlab-kb-data/          never public, never merged into main; the reviewer's worktree lives here
  runs/<run>/qa.json                 pulled copies
  decks/<deck_hash>/profile.json     plan-hash history, funnel history, knockout causes, refused cards, open mistakes
  cards/<card_slug>.json             readmit class notes, finisher tier notes, observed misuse, judgement ids
  mistakes/<detector>/stats.json     rate per 100 seat-games by shim version, judged precision (n), recall estimate, trust
  mistakes/<detector>/examples.jsonl
  judgements/<run>/<flag_id>.json
  human/richard/<date>.md            their texts verbatim; each claim -> detector/scenario id + status
  human/vincent/<date>.md
  human/traces/<game>.json           human game traces (schema in SCHEMA.md)
  overrides/proposed/<id>.json
  digest/<date>.md
  local/                             gitignored: moment cards, scenario-harness output

SERVER: $MTG_DATA_DIR/
  simkb/runs/<run>/qa.json
  simkb/review_queue/{auto,human,done}/<id>.json
  forge_index/<forge_version>/       generated by the worker at startup (WS4), never committed
  decks/<deck>.annotations.json      owner win-con tags and band notes (WS8)
```

**Other key schemas**
```jsonc
// review_queue item
{"id": "rq-20261019-0007", "source": "detector:tutor.dest_waste|flag_this_play|feedback:richard|blind_sample",
 "run": "...", "anchor": {"game": 1, "turn": 13, "player": "Kess, Reanimator", "agent_event_index": 22},
 "deck": "Kess, Reanimator", "priority": 1,
 "question": "With Unmarked Grave, was binning Hullbreaker Horror better than stock's Blasphemous Act (castable from the graveyard with Kess)?"}

// detector stats
{"detector": "tutor.dest_waste", "kind": "rules", "by_shim": {"0.17.0": {"runs": 12, "instances": 9, "per_100_seat_games": 5.1}},
 "judged": 30, "correct": 27, "precision": 0.90, "recall_est": {"blind_n": 64, "missed": 2}, "trust": "trusted"}

// plan_overrides.json
{"schema": "simlab.overrides/1", "version": "2026-12-09.1", "entries": [{
  "id": "ovr-0003", "scope": {"line_id": "..."} /* or card, deck_hash, deck_name */,
  "kind": "target_value|graveyard_value|finisher_tier|keycard_pin",
  "field": "search.targets.Portal to Phyrexia", "op": "delta|set", "value": 2, "bounds": [1, 9],
  "mechanism": {"metric": "qa.decks.<deck>.tutors.picks.closer", "expect": "up", "watch_runs": 5},
  "basis": {"type": "rules|scenario|expert_judgement|playtester|human_trace", "refs": ["rq-...", "simkb/scenarios/..."]},
  "gates": {"scenario_suite": "pass", "scorecard_nonregression": "studies/overrides/ovr-0003.md"},
  "status": "active", "expires": "2027-03-31", "added_by": "PR #..."}]}
```

**Two classes of plan input.**
- **Compiler inputs** (`simkb/linec/`, `simkb/lines/`, `simkb/scenarios/`) are code. They change only by PR, with tests, and Vincent merges.
- **Overrides** (`plan_overrides.json`) are the only thing the learning loop proposes. They are bounded, validated, watched after merge and removable.

**Guardrails** (enforced by `validate.py` in `engine/tests/test_overrides.py`):
- **Evidence.** Allowed basis types are `rules` (what Forge legally offered or allowed), `scenario`, `expert_judgement`, `playtester` and `human_trace`. `sim_win` is rejected. What the Forge AI chose is rejected as a basis for any change to lines or bands; it goes to the pilot-defect queue.
- **Numeric bounds.** A `delta` stays within ±2, clamped to [1, 9]: plan_feedback's own `MAX_NUDGE = 2`. A `set` needs a human basis.
- **Mechanism and gates.** Every override states the metric it should move. Before merge it must pass the scenario suite and show no regression on the scorecard.
- **Post-merge watch and rollback.** QA watches the next `watch_runs` runs in scope. If a guard trips, or the stated effect does not appear, it opens a removal proposal, and Vincent turns that into a PR.
- **Structural changes are compiler-input PRs.** Examples: turning a line's steering off, changing a band, a readmit class, a new script. `executable` is set only by scenario evidence in `simkb/lines/`.
- **No automatic apply for at least 6 weeks** after the loader lands. Bounded automatic nudges are revisited only after detector precision holds.
- **Expiry and provenance.** Every entry expires. Unknown kinds, a bad schema or a missing file mean no overrides are applied, and that is logged.
- **Cold start.** An empty file produces a byte-identical plan (tested).
- **No user data in the main repo.** `validate.py` rejects deck lists, notes or names from production decks under `simkb/`.

**How deck_plan consumes plan inputs.**
- New `engine/plan_overrides.py`, called in `build_plan` after the static plan is built. That is where `apply_to_plan` sits today, `deck_plan.py:495-501`.
- It resolves scope in the order line_id → card → deck_hash → deck_name, validates each entry, applies it, and writes `plan.overrides.applied = [ids]`.
- The shim echoes that list in its log header, and `qa.json` records it.
- `MTG_PLAN_OVERRIDES` can point to another file.
- plan_feedback's combat-nudge branch is deleted when the loader lands (W11).

**Feedback loop into the engine.**
- A confirmed kind of mistake becomes three things: a regression fixture in `engine/tests/fixtures/qa/`, a scenario if it can be reproduced, and a task file if the fix is structural.
- Each of Richard's claims is listed in `human/richard/<date>.md` with the detector or scenario that now covers it.

**Human traces** (decision 14).
- `SCHEMA.md` defines a trace: seat, turn, plays, tutor targets and why, keeps and mulligans, and the kill.
- `py simkb/tools/trace_entry.py` prompts turn by turn and writes `human/traces/<game>.json` (W12, 1 day).
- Vincent owns it: first 2 games over the holidays, 10 by W20.

**Boundary.** Python and files only. Only plan JSON that includes the overrides reaches the shim.

**Effort.** L, 10 days: layer A plumbing and images 1.5, flags and the flags-only key set 0.75, layer B tools 2, blind sample 0.5, reviewer prompt, scheduling and data-repo worktree 1.5, calibration set and Richard's link list 0.5, overrides loader, validator and post-merge watch 2, trace schema and tool 1.

**Depends on.** WS1; seq stamping (W10) for exact anchors; WS3 for scenarios.

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| Finished production runs with `qa.json` | 0 | 100% within 5 min of finish from R1.1; 0 run failures caused by QA | VM, preflight |
| QA modules present in both images | not copied | preflight import check passes | preflight |
| Richard regressions detected on their run | 0 detectors | 4 fire: engine rows shown as win cons; Sol Ring binned (2); unreachable `tutor_cast` (4/5); flagged cards never cast (0/45). Each clears after its fix. | `sim_20260925_003803`, then reruns |
| Richard's text to a queue item | no channel | 1 day or less | `human/richard/` |
| Human flags triaged | no channel | weekly, with a written verdict | queue timestamps |
| Reviewer kappa vs humans | – | ≥ 0.6 on 50 labelled moments before its judgements count (G5) | calibration set |
| Reviewer writes outside its allowed folders | – | 0 | `nightly.py` diff check |
| Overrides citing `sim_win`, lacking a mechanism, or lacking provenance | – | 0 | validator test |
| Overrides whose stated effect did not appear | – | removal proposal opened within `watch_runs` | digest |
| Recall estimate per judgement detector | none | reported monthly from the blind sample | digest |

---

### WS3: Seeded-board scenario harness

**Goal.** Answer "does this mechanism work?" in minutes, on a board where the line is already assembled, instead of waiting for it to come up in a 15-turn game.

**Addresses.** RC1's key unknown; RC6 (there is no harness); regression coverage for WS5 to WS9.

**Mechanism.**
- Forge 2.0.13 ships a public `forge.game.GameState` with `parse(List<String>)` and `applyToGame(Game)`. Puzzle mode uses it (367 files in `res/puzzle`).
- **Unverified:** that it seats 3 or 4 players inside the shim's headless Match.
- `applyToGame` replaces zones and must run on the game thread. So every scenario specifies all zones for every seat, including libraries; otherwise the seeded seat decks itself on its next draw. Commanders are marked `|IsCommander`.
- The state is applied once, after mulligans, from the first controller callback, which runs on the game thread.

**Tasks**
1. **Spike (half a day, Wed 10/14):** apply a 4-player state and log the board. Fallbacks, in order:
   - 2-player states, which the puzzles prove work and which are enough for loop mechanics;
   - moving named cards between zones at game start through public GameAction methods (+1 day; G1 moves to Tue 10/27).
2. **Shim flag `--scenario <file>`,** a thin adapter: read the file, apply it once, make no decisions.
3. **`studies/scenarios/`:** scenario JSON, a writer for Forge's state format, and `run_scenarios.py` (arm × N trials, 8 in parallel, `--out`). The report covers kill on the scenario turn, turns to the kill, activations, iterations, ms per decision and exceptions.
4. **Initial suite:**

   | ID | Setup | Tests |
   |---|---|---|
   | S1 | Kiki-Jiki + Zealous Conscripts (winota decks, `OuY6mdiXbHU`) | trigger target on every pass; stock untapped Kiki 0/8 |
   | S2 | Derevi + Emiel + Gaea's Cradle, with Walking Ballista as outlet | trigger target; stock untapped Cradle 0/216 |
   | S3 | Devoted Druid + an untapper, with an outlet | flagged activation through the generic data-named path |
   | S4 | Magda + Clock of Omens + Liquimetal Torque | activated loop with a flagged piece; the human Magda g2 win |
   | S5 / S5b | Thassa's Oracle + Demonic Consultation in hand; S5b adds an opposing Torpor Orb | the one converting line; suppressor |
   | S6 | Isochron Scepter with Dramatic Reversal + rocks + Ballista | activation loop with an X outlet |
   | S7 | Underworld Breach + Brain Freeze + LED | graveyard loop; expected to fail in every arm for now (negative control) |
   | S8 | Kess with Unmarked Grave in hand; Blasphemous Act, Sol Ring and Hullbreaker Horror in library | tutor destination (Richard regression) |
   | S9 | Magda with Portal to Phyrexia reachable | tutor target (Magda regression) |
   | C1 | Godo + Helm of the Host | **positive control:** stock converts 28/32 in games once Helm is attached; the harness must not distort Forge |

5. **The suite grows from confirmed misplays** once a human accepts the draft. It runs before every shim release.

**Boundary.** Scenario content is data. The Java is one generic "apply this state" call.

**Effort.** M, 3 days.

**Depends on.** Nothing. It blocks E1.

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| Scenarios that load and play | 0 | 10/10, or 8/10 via the 2-player fallback | dev box |
| C1 positive control | 28/32 in games | ≥ 17/20 | harness |
| Stock reproduces its in-game failures on S1 and S2 | – | ≤ 2/20 each | harness |
| Suite wall time, one arm | – | under 50 min | dev box |

---

### WS4: Input fidelity and the Forge index

**Goal.** The sim and the combo lookup get exactly the deck the user pasted. Any gap is visible before a one-hour sim.

**Addresses.** RC9; product problem 6; UX #2 (missing precon combos); the blocking issues on API-side Forge data and DFC layout.

**Tasks**
1. **`engine/forge_index.py`,** run by the worker at startup when the index is missing. It reads `/opt/forge/res/cardsfolder/cardsfolder.zip` with stdlib `zipfile` and writes `$MTG_DATA_DIR/forge_index/<forge_version>/`:
   - `cards.json`: every card name with its `AlternateMode` (DoubleFaced, Modal, Split, Flip, Adventure);
   - `flags.json`: cards scripted `AI:RemoveDeck:All`, and whether each flagged item is a spell, a non-mana activation, a mana ability or a commander;
   - `tutors.json`: `ChangeType`, `Origin` and `Destination` per search ability. This file is used only to backfill QA on old runs.

   The API container has no Forge, so it reads these files from the shared volume. The index is regenerated per Forge release and never committed.
2. **`convert_decklist.py`: normalise "Front // Back".** Transform, modal and battle cards go to the front face; split cards stay "A // B".
   - The primary source is `cards.json`, because Forge decides what Forge loads.
   - The fallback, if the index is missing, is a `layout` field added to the `cards.py` cache. `_slim()` has none today, so this needs a batched refresh that follows Scryfall etiquette.
   - Test fixtures: Ral, Monsoon Mage; Birgi; a modal land; a split card.
3. **Import pre-check.**
   - "Forge doesn't know these cards: …". If the unknown card is the commander, the deck is rejected with that message.
   - "Forge's AI doesn't cast these cards on its own: …" (wording per the 2026-09-27 decision). This covers a flagged commander such as Winter, Cynical Opportunist, until readmission ships.
   - If the index is missing, the checks are skipped and the response says so.
4. **`run_sim.py`** keeps Forge's stderr on success and writes `meta.unsupported_cards`. Per the 2026-09-27 decision, a run is marked polluted only when a seat's commander was refused at load (or the deck lists none); a commander that loaded but was never cast gets a visible, non-polluting note (`commander_never_cast`).
5. **`combos.parse_dck`** (`:61`) strips `|SET|art`. Purge the 38 poisoned cache entries (identity "C", 0 included) and re-query, batched and cached.
6. **Studies.** Apply the same normalisation in `studies/human_ceiling/tools/make_dck.py:53-56`, regenerate the 32 decks, and map plan line names to Forge's names in `deck_plan.py`.
7. **Reruns.**
   - E7: both Ral decks, 8 + 8 games. **Fidelity read only** (does the commander leave the command zone?), so it can touch a holdout deck without tuning on it.
   - The 14 precons that gain Spellbook variants.
   - Re-convert any production deck with " // " names (the count comes from WS0).

**Boundary.** Python only. The worker reads Forge files at runtime.

**Effort.** M, 3 days.

**Depends on.** Nothing. It lands before any study in this plan, because it changes the decks.

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| DFC slots silently dropped | 48 slots in 23/32 cEDH decks | 0 | stderr scan of re-converted decks |
| Ral commander leaves the command zone | 0 times in 30 games | cast in ≥ 70% of games | E7 |
| Precons with included Spellbook variants | reported 0/66 | 14/66 (26 variants) | re-query |
| Runs carrying `unsupported_cards` | none | every run (empty when clean) | all runs |
| Flagged share of cEDH nonland cards in the index | – | 12.1% (285/2362) ±0.5 pp, which proves the index matches the diagnosis | index vs corpus |

---

### WS5: Tutoring (reach, destination, targets, timing, Magda)

**Goal.** Tutors are cast only for cards they can legally find. They put cards where the deck can use them. They go for cards this pilot can actually win with, and they are cast at the times a human would cast them.

**Addresses.** RC4, RC5, RC7; Richard's complaint; UX #12 (Pilot's notes wait on this fix).

**T1: harm-removal hotfix** (shim 0.17.0, branched from 0.16.0).
Built in week 2, gated at G0a (Tue 10/13), shipped in R1 (Fri 10/16). Each mechanism has its own flag, and with all flags off the jar behaves like 0.16.0.

1. **`fix.tutorReach`.** `tutor_cast` (`PlanPlayerController.java:1155-1180`) requires two things:
   - the missing piece is in the library;
   - it passes the tutor's own search restriction, checked with the public `Card.isValid` against the ability's `ChangeType`/`ValidTgts`.

   The shim logs `reach=true|false` on every candidate. Today `lineOfSight` (`:1047-1085`) treats every plan tutor as able to fetch anything.
2. **`fix.commanderTutorZone`.** A commander counts as a tutor only in the zone where its search works. Magda opened pursuit from the command zone in 32 of 37 games.
3. **`fix.noForcedChoices`.** `tutor_cast` skips four kinds of tutor. Forge's own AI still casts them, with its own choices.
   - X-cost tutors. All 18 shim-forced X tutors resolved at X=0, because `castableSpell` (`:1249-1262`) hands Forge a raw SpellAbility.
   - Transmute cards (Dizzy Spell, Muddle the Mixture were cast as spells).
   - Activated searches.
   - Any tutor whose SpellAbility needs targets or choices the raw SpellAbility cannot set. Intuition and Gifts failed to target.
4. **`fix.graveyardDest`.**
   - When `destination == Graveyard` (`rankSearch`, `:1897`; the destination is already passed in at `:1773`), the shim ranks by `plan.search.graveyardTargets`.
   - deck_plan emits those targets: reanimation targets (for decks that reanimate); flashback, escape and unearth cards; and instants and sorceries the commander can cast from the graveyard (Kess).
   - Cards with no graveyard value score 0, so stock's pick stands.
   - Exile destinations are unchanged (§2.6).
5. **`tutor_skip reason=` logging** for every eligible tutor left in hand. Today 237 of 502 are unexplained (unverified).
6. **Data** (deck_plan, behind `planVersion`):
   - **One classifier.** The win-band classifier is written as **`engine/combo_bands.py` v0**, and WS8 extends the same module. It uses the lenient win set from `verify/resource_lines/classify.py`: "Win the game", infinite damage, life loss or mill to opponents, infinite combat phases, infinite hasty tokens or power.
   - **Pilot lines.** Only win-band lines go into `plan.lines`, which drives pursuit and value 8. Engine pieces lose the blanket 8 (`deck_plan.py:323-336`, `:375-376`) and fall back to their role tier.
   - **Opponent lines.** **All** lines go into a new `plan.threatLines`. The shim's opponent logic reads that list instead (`:928-950`, `:965-1004`, `:2084-2093`), so narrowing `plan.lines` does not blind other seats.
   - **`_FINISHER` fix.** Remove "loses? the game" and saboteur text from `_FINISHER` (`:124`).
   - **Consequence: some decks lose line pursuit until WS8.** This affects the decks with no win line, which regain pursuit when WS8 adds composed lines. Magda + Clock + Liquimetal Torque also leaves `plan.lines`, because Spellbook gives it no win feature. That is intended: it removes the combo steer that overrode Portal in 33 of 47 cases. WS8 restores the line in DeckLines as an expert-banded finisher, with `steer: false` until S4 passes. Permanent lines convert at 3% today, so little is lost.
7. **Explicitly deferred:**
   - keep-weight ties at `:1167-1168`;
   - the one-piece-short gate. Corrected figures: 36–41% of tutor turns are two pieces short, and 42–54% are one short with the gate open. So the gate is one blocker among several (verified finding 29).

**T2: targets by pilotability** (W10, on WS8's DeckLines).

| Tier | Cards |
|---|---|
| 9 | Owner-tagged win con, or a proven closer (Portal-class, Craterhoof) |
| 8 | Missing piece of a **drivable** win line |
| 7 | Outlet of a composed line |
| 6 | Engine piece of a composed line; piece of a non-drivable win line |
| 5 | Opener engines (Rhystic Study, Mystic Remora, Necropotence, Seedborn Muse), decaying after round 3; ramp before round 5 |

- Absolute combo-steer priority (`:1792`) applies only to lines with `steer: true`, meaning drivable. That is one flag read.
- Owner tags (WS8 sidecar) feed tier 9 directly.
- Today Richard's plans put line pieces at 8 (Hullbreaker Horror, Sol Ring), above Craterhoof and Archon of Cruelty at 6 (`plans_rebuilt.json`).

**T3: timing** (W17, experiment E4).
1. **KeyCards, no Java.** Write `KeyCards=` (closers and drivable win pieces first) into a **separate plan-seat copy** of the staged `.dck`. It has a distinct filename and the same `Name=`, and we check that player keys are unchanged. Stock seats of the same deck stay a clean control.
2. **Tutor window.** The shim casts a library-top tutor it holds (Vampiric, Mystical, Worldly, Enlightened, Imperial Seal) at an opponent's end step or in its own upkeep, when plan data names a target.
   - It goes through `canPlay` and `canPayCost`.
   - The existing `chooseSingleCardForZoneChange` steers the resolution.
   - No parameter is changed.
3. **`ActivationPhases`** is used only if a harness test proves it changes AI timing alone and leaves legality untouched.

**Magda (E6, W6).** Pod n7, Magda as the single plan seat, rotated, 48 games per arm:
- (a) current;
- (b) T1 + Portal pinned at tier 9, all data only;
- (c) search steering off.

In the same weekend, the −11 pp that rog_ishai and selvala show even with lines off is broken down by toggling mulligan, holds and plan-mode steering one at a time.

**plan_feedback.** Off from day 1 (WS0). The nudge code is deleted when the overrides loader lands (W11).

**Boundary.** Reach, zone and window checks are shim mechanisms that ask Forge's rules. Values, tiers, graveyard targets, KeyCards, windows and band flags are Python data.

**Effort.** L, 9 days: T1 3.5, T2 2, T3 3, Magda 0.5.

**Depends on.**
- T1: the WS1 `tutors` detector and the WS4 index.
- T2: WS8.
- T3: G2c.

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| `tutor_cast` that cannot find the sought piece | 316/718 (44%); 4/5 in Richard's run | ≤ 5% | cEDH-A all-plan; Richard pod |
| Casts seeking a piece already in graveyard or exile / X at 0 / failed to target | 98 / 18 of 18 / 26 | 0 / 0 / 0 | cEDH-A |
| Plan graveyard steers onto a card with no graveyard use | 2 of Kess's 12 steers (Sol Ring ×2 over Blasphemous Act) | 0 | Richard pod + S8 |
| Steers onto reanimation targets or cards castable from the graveyard | 10 (Hullbreaker 5, Toxrill 2, Unexpected Windfall 2, Big Score 1) | reported as expected; the Hullbreaker vs Blasphemous Act choice goes to Richard as a review question | Richard pod |
| Guard: tutor casts per tutor drawn | stock 67% | ≥ 50% | cEDH-A |
| Steers onto non-drivable lines that override a stock closer pick | Magda 47/47 (68/68 across 5 arms) | 0 | cEDH-A after T1; E6 |
| Magda fetches Portal when its search offers it | 0/72 library fetches | ≥ 80% | E6 arm (b) |
| Plan-piloted Magda win share | 7/48 (15%) vs stock 47/144 (33%) | ≥ 28%, reported with a Fisher test; directional only (15% vs 33% is about 2 SE at n=48) | E6 |
| Losses to own spell | 8/256 (unverified) | ≤ 2/256 | cEDH-A |
| Early (rounds 1–3) engine fetches | plan 0/175 (unverified); humans 9/18 | ≥ 25% | cEDH-A after T2 |
| Library-top tutors cast before main phase 2 (plan) | stock 0/269 | ≥ 50% where the plan names a target | cEDH-A after T3 |
| Fetched card used the same turn (plan) | stock 21/72 | ≥ 50% | cEDH-A after T3 |

---

### WS6: Forge refusals (readmission data and E3)

**Goal.** The pilot plays flagged cards wherever plan data says how. The product names the cards that are still dead.

**Addresses.** RC3; "the stock baseline is itself crippled"; product problem 5.

**One mechanism with the executor.** E1 builds the generic path: return a data-named SpellAbility after `canPlay` and `canPayCost`. Returning it straight from `chooseSpellAbilityToPlay` bypasses Forge's `removeIf` filter; that is how the shim already casts Consultation. WS6 is the data classes and the experiment on that path. If E1 is a NO-GO because forced activations misbehave, readmission ships for spells only (`forge_ai` class).

**Decision on opponent seats (owner decision 2).**
- **Production:** every seat readmits. Every production seat is already a plan seat (Richard's run: `agents: plan ×4`), and users want their opponents' decks played as written.
- **Studies:** stock seats stay unreadmitted, as the frozen "Forge 2.0.13 as shipped" control.
- **Stock+readmit arm:** a shim seat with **every dial at its stock value** (holds off, stock mulligan, `splitAttacks` 0, block skips off, kingmaker off, no steering, no plan-mode) plus the readmit list.
  - It is used only after an A/A check. The same seat with an empty readmit list is compared against pure stock over 96 games: casts per drawn, flagged cast rate and per-deck win share must be within noise.
  - If the A/A check fails, the arm is dropped and claims cite only the frozen stock control.
- **Never without plan data.** No seat readmits a card without plan-data preconditions. Consultation, Ad Nauseam and the Pacts fire suicidally without timing rules.

**Tasks**
1. **Readmit classes,** from `flags.json` plus the curated `simkb/linec/readmit.json` (a compiler input):
   - `forge_ai`: take the card when `canPlaySa` says WillPlay. Examples: Signets, Beast Within, Toxic Deluge, Windfall, Clock of Omens activations, and flagged commanders such as Winter, Cynical Opportunist.
   - `line_bound`: only as a line step (Consultation, Tainted Pact, LED).
   - `window`: Vampiric Tutor at an opponent's end step or in its own upkeep.
   - `deny`: Final Fortune, Ad Nauseam and Pact of Negation, unless bound to a line.
2. **Merge the E1 path into mainline** (0.18.0, W8). After `super.chooseSpellAbilityToPlay`, if stock returned nothing or a lower-weight choice, the shim:
   - gathers the seat's data-named flagged spells and non-mana activations;
   - checks `canPlay`, `canPayCost`, the public `getAi().canPlaySa()` (for the `forge_ai` class; it does not read the flag) and the data precondition;
   - takes the best by plan weight and logs `readmit`.

   `res/` is never edited.
3. **E3** (W8–W9), on cEDH-A/stock:
   - (a) plan seat vs 3 stock;
   - (b) plan seat readmits;
   - (c) plan seat readmits vs 3 stock+readmit.

   Plus the Richard pod, all plan seats, control vs readmit, 16 games each.
4. **Product.**
   - "Cards Forge's AI won't play (N)" appears per deck from R1.1. Those cards are excluded from "cold" or "cut" verdicts in `coach.py` and `deck_telemetry.py`.
   - After readmission ships, the line becomes "N cards are played by Sim Lab's pilot because Forge's AI skips them".
5. **Flagged mana abilities** (LED: 0 mana uses) are measured only. No fix unless E3 shows they matter.

**Boundary.** The readmit list and its preconditions are data. The Java generically offers data-named flagged abilities that Forge's own checks accept.

**Effort.** M, 3 days: data classes and path merge 1, E3 1, product 1.

**Depends on.** E1's path (G1); WS1; WS4; WS7 for Consultation.

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| Plan seats cast flagged cards they hold | 24.6% cEDH; 0/45 in Richard's pod | ≥ 50% (unflagged cards: 63–73%) | E3 (b); Richard pod |
| Printed flagged permanents activated where a line needs them | 1/459; Clock of Omens 0 in 135 | ≥ 50% of assembled-line games | E3 + S3, S4 |
| Self-harm | 8/256 (unverified); 14 self-decks | not above control, and ≤ 2/256 | E3 |
| Stock-seat flagged cast rate in the control arm | 5.2% | unchanged (control integrity) | E3 (a) |
| Stock+readmit A/A | – | within noise, or the arm is dropped | A/A run |
| Decks with an undisclosed dead card | all | 0 | product |

---

### WS7: Oracle sequencing and line protection

**Goal.** Keep the one converting line converting, stop it decking its own pilot, and make the winning window intentional. Protect our own line pieces whether or not the executor ships.

**Addresses.** RC8. The guard at `:1094` checks `getStackZone()` (spell cards), not the MagicStack where triggers sit. Stock's bare Oracle casts pass through at `:1107`, and Consultation's named card is not steered. It also addresses the protection gap in RC10: the sim responded 1 time in 39.

**Tasks** (E5, W12, each behind a flag):
1. **Data.** Oracle is `fireLast`, and its zone is hand. The exiler needs a pending Oracle trigger. A suppressor list (Torpor Orb, Hushbringer, …) is a compiler input.
2. **Explicit stack rule.** Allow the exiler in response to **my own** pending Oracle trigger, read from the real MagicStack. Otherwise require an empty stack. Do **not** simply switch `:1094` to `getStack().isEmpty()`: the diagnosis shows that turns the line into a guaranteed self-deck.
3. **Oracle discipline.**
   - Cast Oracle only when the exiler is castable in the same window (`canPayCost` on both).
   - An Oracle whose ETB trigger is spent never counts as online.
   - Veto stock's bare Oracle casts while the line can still be completed.
   - Abort if a listed suppressor is on the battlefield.
4. **Named card.** Override `chooseCardName` to follow a data policy: name a card known to be outside the library. 3 of the 31 in-response Consultation casts failed because Forge named a card still in the library.
5. **Protection response** (flag `fix.protect`). When one of my line pieces or my commander is targeted and I hold a free counterspell, respond through `canPlay` and `canPayCost`. Which cards count as protection is data (`protection.json`). This item is independent of G1.
6. **Tainted Pact.** Its repeat (`confirm_repeat`) belongs to the executor. Until then the line is marked *not drivable (needs repeat)*. That is a statement about the pilot, not about the line.
7. **Explicitly deferred:** the plan-weighted cleanup-discard fix.

**Boundary.** Flags and lists are data. The Java is the explicit stack rule, a data-driven name choice and a generic "respond with a data-named protection spell".

**Effort.** M, 3.5 days: Oracle 2, protection 1.5.

**Depends on.** Nothing (hand-written v2 flags).

**Acceptance** (tymna_thrasios and rograkh_silas, 64 plan games per arm; protection on cEDH-A):

| Metric | Today | Target | Where |
|---|---|---|---|
| Consultation self-decks | 14 | ≤ 1 per 64 plan games | E5 |
| Oracle wins per Consultation cast (guard) | 25/49 | ≥ control | E5 |
| Oracle cast with ETB spent and no attempt | 53/92 | ≤ 10% | E5 |
| Consultation naming a card still in the library | 3 | 0 | E5 |
| Protection responses when holding a free counter and a line piece is targeted | 1/39 | ≥ 50% | E5 arm on cEDH-A |
| S5 / S5b | – | S5 ≥ 18/20; S5b 0 self-decks | harness |

---

### WS8: Combo data rebuild (DeckLines), with the G-lines gate

**Goal.** Each deck ships a short, structured list of real ways to win. It covers band, family, pieces with zones and order, the payoff, prerequisites, and whether this pilot can run it. The pilot, the product and QA all read that one list.

**Addresses.** RC2; RC4 (values depend on it); RC8 (order and zone); product problem 2; UX #2 (five bands; roadmap §9.1 prerequisites 7 and 9).

**Scheduling.** WS8 comes ahead of the E3 and E5 code (W7–W8). T2, Phase B and the product's win cons all wait on it.

**Tasks**
1. **`combos._slim` (`combos.py:90-101`) keeps more of Spellbook's record:**
   - `uses[]` with zone locations, card states, `mustBeCommander` and `usedFace`;
   - `requires`, `of` (family), `includes`, `bracketTag`, `manaNeeded`, prerequisites, `description` and `produces`.

   Bump the cache schema and refresh the 102 lists, one batched POST per deck.
2. **`engine/combo_bands.py` v1 + `simkb/linec/band_map.json`.** This extends T1's v0 module; there is one classifier.
   - The five bands: Finisher; Combat finisher; Lock, extra turns or extra combats; Engine needing a payoff; Commander loop.
   - A test fails on any unmapped feature (343 exist today). Unmapped features go to "Other", never to Finisher or Engine.
   - **Expert band overrides** live in the same file, each with a basis. Day one: Magda + Clock of Omens + Liquimetal Torque becomes a Finisher (basis: the table conceded to it in human Magda g2).
   - The product (analysis) and the pilot (deck_plan) import the same module.
3. **Families, dedupe and cap.**
   - One line per Spellbook family (`of`). Skrat's 28 Squirrel Girl variants become one row.
   - No exact duplicates (isaac_yisan ships 3).
   - At most 8 pilot lines per deck, drivable win lines first.
   - A commander loop is the commander plus its prerequisites. It is never "together" merely because the commander is on the battlefield.
4. **Composition from Spellbook's own data first.** An engine is paired with a larger included variant in the same 99 that contains the engine's cards and produces a win.
   - A curated outlet table comes later (+2 days), and only if measured useful.
   - The investigator's 151/168 outlet count could not be reproduced: an independent list gave 126/168, with 107 matched by type.
5. **Per-run DeckLines file.** `lines_<stamp>.json` (schema `simlab.deckLines/1`) is written next to the plans file and referenced from `result.meta.lines_file`. Key fields:
   - `families[{family_id, band, band_basis: feature_map|expert|owner}]`
   - `lines[{line_id, family_id, band, produces, pieces[{card, forge_name, zone, order, fireLast, role}], prereqs, mana_needed, composed{outlet, basis}, executability{class: drivable_now|needs_runner|script_verified|forge_blocked|not_drivable, reason, script}, steer, in_pilot}]`
   - `refusals[]`, `owner{win_cons, band_overrides}`, `coverage{}`

   `plan.lines` is the `in_pilot` subset, and `plan.threatLines` is the full set. `steer` is true only for `drivable_now` or `script_verified`.
6. **Owner annotations.** `$MTG_DATA_DIR/decks/<deck>.annotations.json` holds `{win_cons, band_overrides}`, written with the API key. It is compiler input (owner decision 12).
7. **Acceptance set,** from verified finding 20 as corrected:
   - 11 human engine or combo wins. The line is present for 5: Cabbage g1, Winota g2, Ral g1, Dallas g1, Magda g2.
   - 3 are outlet misses by the line builder: Derevi's Nadu + Blind Obedience, Sisay's Deadpool / Mount Doom finish, and Cabbage g2's Walking Ballista.
   - 1 is decklist drift (Rog/Thras g3, where Six is missing). It is documented, not patched with data.
   - 2 cannot be scored: Kinnan (wrong build), and Magda g1 (line cut by the editor).
   - **Targets are computed on dev decks only.** Acceptance lines in holdout decks are scored blind once, at G-lines. A failure there is recorded, not fixed, until after G3.

**G-lines gate (Thu 11/19).**
- **Pass:** the static acceptance table below holds on dev decks. Then T2 and the five-band product section build on DeckLines, and Phase B scripts come from it.
- **Fail:** ship the families and bands that pass. Lines that fail stay out of `plan.lines` and show as "not yet classified". Phase B runs on hand-written step JSON for the scenario lines only. T2 uses only lines that passed.

**Boundary.** Data only. The shim ignores keys it does not know. New piece flags are read only once the WS7 or WS9 code that uses them exists. That honours the diagnosis's warning that adding Oracle as a line piece today would get it cast early.

**Effort.** M, 6.5 days (including the gate).

**Depends on.** WS4 and T1's `combo_bands` v0. It feeds WS5 T2, WS9 and WS12.

**Acceptance** (static checks on the dev cEDH decks, 66 precons and Richard's 4 decks):

| Metric | Today | Target |
|---|---|---|
| Pilot lines that produce no win and have no composed payoff | 168/238 | 0 (shown in the product as "engines that need a payoff") |
| Decks with no win line (dev decks) | 7/32 overall; the dev count is fixed at the draw | at most half the dev count, each with a stated reason |
| Human wins with the line present (dev decks) | 5/11 overall | every present line kept, plus every outlet miss that falls in a dev deck |
| Holdout acceptance lines found | – | reported blind at G-lines; no rework before G3 |
| Magda + Clock + Torque | stripped by T1 v0 | in DeckLines as Finisher (expert), `steer: false` until S4 passes |
| Lines per deck / exact duplicates | up to 29 / 3 | ≤ 8 / 0 |
| Richard's combo section | 37 variant rows, 0 win alone | ≤ 6 family rows in correct bands (Hullbreaker + Sol Ring = engine; Stella alone = commander loop) |
| Band map coverage | – | 343/343 features (test) |

---

### WS9: Combo executor, and its go/no-go test

**Goal.** When an assembled drivable line's preconditions hold, the pilot runs it the way a human would: activations, loop targets, iterations, a stop condition and the payoff. Everything goes through Forge's own legality and cost checks.

**Addresses.** RC1, ranked first: the shim casts only spells from hand (`:1251`), treats "assembled" as done (`:1068`) and chooses no targets. Also RC8 generalised, and runaway loops scored as draws.

**Before E1.** You sign off (owner decision 4, Fri 10/16) a written thin-adapter checklist, committed to the shim README:
- The `orderAndPlaySimultaneousSa` override may bind targets only on triggers that match an armed, data-named step. It delegates to `super` for everything else and on any mismatch.
- No card names and no scoring in Java; the card-name lint passes.
- Public APIs only: `chooseSpellAbilityToPlay`, `orderAndPlaySimultaneousSa`, `confirmTrigger`, `chooseCardName`, `canPlay`, `ComputerUtilCost.canPayCost`, `sa.canTarget`, `ComputerUtil.playStack`.

#### Phase A: prototype E1 (4 days, Mon 10/19 to Thu 10/22, branch `exec-proto` in the public shim repo)

Step JSON for S1, S2, S3, S4 and S6 is written by hand.

1. **Generic data-named path.** Return the named SpellAbility (a spell from any zone, or a non-mana activation, flagged or not) after `canPlay` and `canPayCost`, with targets set through `canTarget`. This is also WS6's readmission path.
2. **Trigger targets.** Bind through `orderAndPlaySimultaneousSa`, then call `playStack`. `chooseTargetsFor` is reached only when a TargetingPlayer param exists, which is why this hook is needed.
3. **Stop.** Decline the optional loop trigger in `confirmTrigger` at the step's cap or stop predicate: `count`, `power_vs_life`, `opponents_out`, `mana_at_least` or `no_progress`, plus a per-turn wall budget.
4. **Payoff and fallback.** Fire the outlet step. On any exception or unmet precondition, hand back to stock and log `exec_abort` with the reason.

**Timing without Docker.** The dev box has no Docker, so the 2-CPU timing runs pin JVMs to 2 cores with Windows CPU affinity and pass `-XX:ActiveProcessorCount=2`. The G1 PREREG says so.

**Pre-registered go/no-go, G1 (Fri 10/23).** 20 trials per scenario, stock vs prototype.
- **GO:**
  - at least 16/20 kills (or the stated infinite state followed by the outlet) on at least 3 of S1, S2, S3, S4 and S6, including S1 or S2;
  - stock at most 2/20 on the same scenarios, and C1 not broken;
  - 0 unhandled exceptions;
  - median decision time at most 2 s under 2-core affinity;
  - Java diff at most 400 lines, lint clean.

  Then: merge the generic path (WS6) and build Phase B.
- **PARTIAL:** the activation scenarios pass (S3, S4, S6) but trigger targeting (S1, S2) fails. Then:
  - build activation and cast-from-zone lines only;
  - mark trigger-target lines `not_drivable` and say so in the product;
  - spend 1 day testing bounded `GameSimulator.simulateSpellAbility` as a line check only (as a pilot it failed 2 of 2 games);
  - file a Card-Forge issue about loop targeting.
- **NO-GO:** forced abilities misbehave in sub-choosers, crash or blow the time budget, or success is at most 6/20 on most scenarios. Then:
  - stop executor work. Phase B's slots (W9, W11, W13–W14) go to T2 and T3, readmission for spells, and UX phase 2;
  - the product keeps "Forge's AI doesn't run combo loops, so these show chances, not results" and the floor label permanently;
  - file an upstream issue (TapOrUntapAi and ControlGainAi pick opponents' permanents).

#### Phase B: the build (9.5 days across W9, W11, W13–W14, only on GO or PARTIAL)

1. **`StepRunner.java`,** at most 600 lines, in the GPL shim repo.
   - Closed operation vocabulary: `cast, cast_from(zone), activate, resolve_trigger, name_card, confirm_repeat, decline_trigger, hand_off_attack`.
   - Closed bind vocabulary: `own_piece(card), own_piece_tapped(card), self_player, opponent(policy), any_legal`.
2. **Arming.**
   - The pieces are in their required zones, the first step passes `canPayCost`, and the data predicates hold. Predicates cover untapped, not summoning sick, a minimum number of mana sources, and a window: `own_main | opp_end_step | on_trigger`.
   - An armed runner outranks `comboPriority`. A step that fails `canPlay` twice aborts the line for that turn.
   - The runner is wired in at `:1068` (currently `continue; // assembled — done here`).
3. **Scripts: `engine/combo_steps.py` + `simkb/linec/shapes.json` templates.**
   - Templates: copy-untap loop, blink loop, persist loop, activated self-loop, untap-artifact loop, graveyard recast loop, mana engine + X outlet, spell completion, equip-combat.
   - Scripts are drafted first for the lines behind human wins in dev decks and the most frequent lines in the dev pods. Each ships a scenario in `simkb/scenarios/`.
   - "Executable" requires at least 18/20 in its scenario.
   - On a G-lines fail, scripts cover the hand-written scenario lines only.
4. **A cap on every loop.** This ends "loop until the 900 s clock, scored as a draw". A data dial, `maxOptionalTriggerRepeatsPerTurn` (off by default, measured), covers runaway stock loops such as Felidar's 3,018 triggers.
5. **Logging.** `line_step` events are diagnostics only. Conversion is scored from Forge's log (§3.0).

Phase B no longer depends on WS6 (the path is shared) and no longer carries the protection response (it moved to WS7).

**Boundary.** Scripts, templates, windows, caps, stops, targets and drivability are data. The Java is a generic interpreter over public APIs. It is published in the public shim repo at the commit the image is built from. When it lands, CLAUDE.md is updated: Forge still adjudicates every action.

**Effort.** Phase A 4 days; Phase B 9.5 days.

**Depends on.** WS3 and owner decision 4. Phase B also depends on WS8, or on its fail branch.

**Acceptance at G3 (Mon 1/11).**
- Arms: cEDH-A all-plan (64 games per arm), cEDH-dev, **cEDH-holdout** (at least 30 assembled drivable lines), Richard pod, and an **all-plan + readmit opponents** arm.
- Each is the runner on vs the same jar with the runner flag off.
- Timing is checked on the **2-vCPU VM while the queue is idle** (8 games per arm).
- Targets marked "PREREG" are set in the G3 PREREG (W14): scenario success at G1 × the arming rate measured on cEDH-dev.

| Metric | Today | Target |
|---|---|---|
| Scenario suite, every `executable` line | – | ≥ 18/20 each |
| Same-turn conversion of assembled drivable permanent lines (arm-neutral) | 5/167 (3%) | PREREG (provisional ≥ 40%); dev and holdout reported separately |
| Share of all games decided by round 6 (draws censored), decks with a drivable line | recomputed at G0b (15/93 is a share of wins) | PREREG (provisional ≥ 30%) |
| Mean win round, decks with a drivable line | plan 13.1 | ≤ 10; **red flag if below 5.0** (the human soft floor) |
| Assembled lines that faced a response | 31–39% (unverified) | reported; red flag if under 20% in the readmit-opponent arm |
| Draws from runaway loops | 13/45 timeouts (unverified) | 0 |
| Median game time on the VM (idle queue) | 240 s (dev box) | ≤ +25% vs control; no game hits the clock because of the runner |
| Unhandled exceptions | – | 0 per 500 games; `exec_abort` rate reported |
| Richard pod and precon sanity | – | no mechanism guard trips; win share reported with game-clustered SE |

---

### WS10: Combat clean-up; GPL constant audit

**Goal.** Stop spending time on combat. Remove the errors the shim itself introduces, which make replays look illogical. Stop the GPL module from accumulating policy.

**Addresses.** RC10 (every number below is unverified by the adversarial pass); the boundary drift that already exists.

**Tasks**
1. **Freeze (day 1).** No new combat, attack-target, block or personality code, dials or study arms before G4 (Fri 1/22), except the stock-value dial settings below. They fall under the harm-removal exception and each gets a same-jar gate.
2. **Re-verify first.** Run the WS1 detectors on the current jar before changing anything.
3. **Data defaults, E8** (W6, same jar):
   - `splitAttacks` 0;
   - `chumpiness` 0 outside dangerLife;
   - `kingmakerRatio` high enough to disable re-aims;
   - random block skips off (owner decision 8);
   - a threat list built separately from opening-hand keep-weights (`deck_plan.py:430`), so mana rocks stop scoring 8.

   Richard's 8 games logged 43 `block_skip`, 41 `split` and 17 `kingmaker_reaim` events.
4. **Mulligan by mana sources, not lands.** A small data list, after G3 (W16).
5. **GPL constant audit** (W15, 1.5 days). Move the scoring constants hard-coded in `PlanPlayerController.java` (2,179 lines) into plan data, keeping the same defaults:
   - `threatOf` weights 0.5 / 0.75 / 0.15;
   - `THREAT_EYEBALL_CAP` (`:2058`);
   - the 10% "twitchy" counter roll (`:906`).

   A same-seed log-equality test proves behaviour is unchanged. Extend the card-name lint to the whole shim.

**Boundary.** Data defaults, plus moving constants out of Java.

**Effort.** S, 3 days.

**Depends on.** WS1.

**Acceptance** (E8: cEDH-A all-plan + Richard pod, same jar):

| Metric | Today (unverified) | Target | Guard |
|---|---|---|---|
| Moved attackers that die for nothing | 9.4% split, 7.7% kingmaker (unmoved 2.8%) | ≤ 3% | combat damage per seat-game ≥ 90% of control |
| Needless chumps per seat-game | 0.30–0.63 (stock 0.08–0.09) | ≤ 0.10 | kill-and-survive blocks ≥ 90% (96.3% today) |
| `counter_fire` on mana sources cast after round 3 | 73/209 across all rounds | ≤ stock's rate for the same window; early fast-mana counters not counted; reviewer-confirmed misfires tracked | counters cast ≥ 80% of control |
| Shipped hands with ≤ 1 land but 3+ sources | 69/228 | ≤ 20/228 (after G3) | mulligans to 5 not up |
| Scoring constants left in Java | ≥ 5 | 0 | same-seed logs identical |

---

### WS11: Product honesty (the truth patch)

**Goal.** Nothing on screen claims what the data does not show. This is the UX review's "fix what's untrue", merged with the diagnosis's product findings.

**Addresses.** UX #1, #2 (stopgap), #4, #5, #6, #10 (in part), #11; product problems 1 to 12.

**Verification.** UI is verified locally with `npm run verify` once Node is installed (decision 7, Mon 9/28). Until then, it is built on the VM while the queue is idle.

**Tasks**
1. **Game story (UX #1).**
   - Parse phase lines against the known player keys, longest first (`web/lib/replay.ts:245`), and check the same pattern in `forge_log_adapter.py`.
   - Add a "Skrat's Revenge" fixture. Re-run `board.py` on the stdout fixture and on a shim result; neither `exit_match_rate` may regress.
   - Per-knockout cause, killer and turn come from `qa.knockouts`. They ship only after the W3 hand audit.
   - Out seats are greyed and cleared, dated by Forge.
   - The **turning point** replaces "the deciding turn": the largest board-power shift toward the winner. It is read from zones on shim runs and labelled inferred on stdout runs. It ships only if its audit passes; otherwise it is labelled "biggest swing" or held.
2. **Combo section stopgap (UX #2)** (`results/[file]/page.tsx:438-633`).
   - Rename it "Combo lines (from Commander Spellbook)" and show `produces` as chips.
   - Delete "AI can fire this; results meaningful" (`:568`) and the contradictory import copy.
   - Fold variants with the same `produces` that share all but one card. Fold lines that never came together.
   - Show description and prerequisites on expand.
   - Add one line: "Forge's AI doesn't run combo loops, so these show chances, not results."
   - WS12 later replaces this with five-band families.
3. **Win method from the lethal event.** Until knockouts land, say "life reached 0 (combat or life loss)" (`DeckScorecards.tsx:19-23`).
4. **Disclosure.** "Cards Forge could not load" (WS4) and "Cards Forge's AI won't play" (WS6) appear on the run page, the deck page and at import.
5. **Duration (UX #4).**
   - `GET /estimate` wraps `estimate_sim_seconds`; delete `SECONDS_PER_GAME` (`web/lib/format.ts:118-124`).
   - Offer whole rotations only, with the played count on the button.
   - Add "you can close this tab", and make the `/runs` copy match the job's real state.
6. **Names (UX #5).** Commanders from `.dck [Commander]` go into the run summary, the results index and the game payload, followed by a readapt. Fix the shortName rule.
7. **Machine strings (UX #6).**
   - No NaN:NaN, "T36", "Draw (draw)" or raw Forge strings.
   - Ops copy goes behind `NODE_ENV !== 'production'`.
   - Coaching and "Ask" are hidden while `health.llm` is false.
   - The ui-review skill gains a rule: no NaN, ids, braces, env vars or file names in rendered text.
8. **Telemetry (UX #11).** `_commander_of` goes through `_find_deck()` (`mtg_engine.py:866`, `deck_telemetry.py:68-91`). Delete the universal charge-counter and proliferate rows.
9. **Win rates (UX #10, in part).**
   - Decided games are the one denominator, and the engine publishes the rate.
   - Whole percents below 30 decided games.
   - "Leader", not "Winner". Status glyphs come off deck results.
   - No baseline ticks until baselines are re-measured (decision 13).
   - **The leaderboard groups runs by pilot and version** and never pools across them (`SIM_CALIBRATION.md:86`).
10. **Pilot disclosure.**
    - Show the pilot and shim version on every run.
    - `validity.py:165` stops calling an all-stock run a "Mixed pod".
    - "Humanized" is replaced by "some choices are random on purpose" while any random dial remains.
11. **Prediction model honesty** (decision 19).
    - `/results/{file}/prediction` compares the run's pilot with the model's `arm` ("stock Forge, decided games").
    - Where they differ, which is every production run today, the page says "fit on stock Forge games; this run used Sim Lab's pilot". If the latest rank check failed, the prediction is suppressed.
    - At each release that changes the pilot (R1, R2, R2.1, R3), an overnight Precon-8 run checks rank correlation. If it holds, the label stays. If it breaks, the prediction is suppressed until a refit after G3.
12. **`predict.py` avg_cmc explanation:** fix the inverted sign (product problem 12).

**Boundary.** Python and TypeScript.

**Effort.** L, 8 days.

**Depends on.** WS1 (knockouts), WS4, WS6 (disclosure data).

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| Game 1 of Richard's run | "poison"; every knockout at turn 10; out seats still seated; "deciding turn" = turn 10 untap | The UX review's first-pass reading: "Skrat's Revenge, turn 10. Out: Stella and Krenko (poison, turn 9), Kess (combat, turn 10). Turning point: turn 8, Ezuri's Predation." The analyzer confirms or corrects it. | readapted `sim_20260925_003803` |
| Wrong phase labels on possessive names | every Skrat's turn | 0 | fixture + their run |
| Combo rows called win conditions | 37 | 0 outside the Finisher band | their run |
| "AI can fire this" | every "converted" row | 0 | grep + page |
| Estimate vs actual | "about 14 min"; the job took 55 min 56 s for 8 games | engine range shown; the next 10 production runs finish inside it | production |
| Imported decks with "No commander could be identified" | Kess, Skrat's | 0 | telemetry page |
| Predictions shown on runs whose pilot differs from the model's arm without a label | all | 0 | page audit |
| Leaderboard rows pooling pilots or versions | pooled | 0 | page audit |
| Em-dash grep; ui-review | – | clean; pass | repo |

---

### WS12: UX phases

**Goal.** The look stops reading as a template. The report is about the user's deck. The replay is watchable. The work follows the review's order (truth, then feel, then validate, then build), resequenced to capacity as explained below.

**Addresses.** UX #2 (full), #3, #7, #8, #9, #12, #13, #14, #15.

**Resequencing, with reasons**
- **Truth ships in R0 and R1 (weeks 1–3).** The engine items it needs (knockouts, commander names) are built anyway, because the QA agent needs the same analyzers.
- **"Flag this moment" moves from phase 2 to R1.** It costs about half a day, it feeds the review queue, and being heard is the fastest trust signal.
- **Feel lands in weeks 5–7,** after design-system amendment A is approved from screenshots (Wed 10/28).
- **The validation gate stays before any phase-2 item** (Fri 11/20). Richard's session there also collects their win-con tags.
- **Phase-2 items wait for their engine dependencies,** as the review itself requires:
  - five bands wait for WS8;
  - Pilot's notes wait for T2;
  - the replay theatre waits for seq stamping (W10).

**Phase 1 remainder (weeks 5–10, 11.5 days)**
1. **DS amendment A (owner decision 5):**
   - an opaque `.page` (`globals.css:325-335`);
   - the backdrop only on home, empty, running and 404 screens, re-encoded to about 200 KB (`layout.tsx:25-27`);
   - sentence-case 15px primaries with no glow at rest (`globals.css:398-415`).
2. **Home rewrite (UX #3).**
   - A computed two-sentence lede and one primary.
   - Sims running from this browser, and recent sims with commander avatars.
   - Loading, empty and error as three separate states. No pips as ornament.
3. **Type adoption (UX #14).**
   - Map the 141 raw `font-size` declarations onto the tokens, plus a 26px title step.
   - Mono only for figures.
   - Restore the focus ring on typed fields (`globals.css:522, 574, 577`) and add `--control-edge` at 3:1.
   - A `.btns` gap, per-route titles, `<main>` and a skip link.
4. **Instrumentation.** Aggregate server counters: replay opens, furthest step reached, turning-point clicks, report sections reached. No personal data.
5. **Replay basics (UX #8, part of #9)** (W10, after G-UX).
   - One viewport with a sticky transport; bookkeeping steps skipped in playback.
   - Clickable log rows; runs of damage and didn't-block lines collapsed.
   - CardPreview on tiles, `?seq=` deep links, and Home, End and ? keys.

**Validation gate G-UX (Fri 11/20, 2.5 days including logistics).**
- **Recruit** 2 or 3 Commander players besides Richard by Fri 10/23.
- **Two builds are served from the VM during the sessions:** the R1.1 web image on a second port (old) and R2 (new). Sessions are remote screen shares, since the dev box serves nothing publicly.
- **Four scripted tasks:**
  - "How did Skrat's Revenge do?"
  - "Why did it lose game 3?"
  - "Find the turn game 1 was decided."
  - "Which of your win cons got cast?"
- **We record** time to answer, wrong answers, and where people looked.

**Phase 2 (W11 onward; default order, re-ordered by the gate)**
1. **Five-band combo section** from DeckLines (W11–W12, after G-lines).
2. **Report v1 (UX #7, #10)** (W15–W16).
   - The focus deck is recorded on the job.
   - Sections: Record, Knockouts, Win cons, Mana, Commander, and "Worth a look" (trusted detectors only, as aggregate facts, never blame for a single play).
   - Story rows, the pod comparison table and the rotation grid.
3. **Win cons (UX #2)** (W17–W18).
   - Owner-tagged cards, with deck_plan suggestions marked as suggestions, and per-card cast and won counts.
   - An "executable" chip only for lines that passed their scenario and G3.
4. **Pilot's notes whitelist and study-mode default (UX #12),** after T2 (W18–W19).
5. **Replay theatre and pacing (UX #8, #9),** after seq stamping (W19–W21).
6. **Deck page (UX #13), running-sims rows, DS amendment B (UX #14 remainder).**

**Phase 3 (after R5).**
- Deck hub and "Run 8 more games"; one `/sims/[id]` page.
- Model honesty with re-measured baselines; exact elimination records from the shim.
- Playtest to the Moxfield baseline (UX #15).
- Coaching relaunch when the key is set; accounts (tasks 04 and 06).
- **Explicitly deferred:** partner commanders in `convert_decklist` (UX §9.4), task 12 (gallery), task 13 (import), and the rules-search golden set.

**Effort.** Phase 1 remainder 9 days; gate and logistics 2.5; phase 2 about 25 (five bands 2, report 6, win cons 4, notes 3, theatre and pacing 8, deck page 3, palette 1, less overlap).

**Acceptance**

| Metric | Today | Target | Where |
|---|---|---|---|
| "Find the turn game 1 was decided" | the app points to turn 10 untap (wrong) | 3/3 testers correct | G-UX |
| Scripted tasks correct per participant | baseline at the gate (old build) | ≥ 3/4 on the new build; median time halved | G-UX |
| "Which of your win cons got cast?" | not answerable | 3/3 in under 60 s after Win cons ships | follow-up session |
| Raw `font-size` outside tokens | 139 of 141 | 0 (lint) | CI |
| Results-page text in mono | 48% | figures and ids only (under 20%) | page audit |
| Richard names a "template tell" | "jank", "AI slop" | none named | G-UX and the W12 check-in |

---

## 4. Timeline

The plan starts Monday 2026-09-28. There are two tracks, each a Claude Code session in its own worktree:
- **Track A:** engine, shim, QA analyzers.
- **Track B:** product, web, QA plumbing and the reviewer.

Vincent reviews both. **Capacity is about 7 reviewed developer-days per week** in total (decision 0 confirms or changes this). Holiday weeks count as 2 days each, and Thanksgiving week as 5. Experiments run unattended overnight on the dev box.

### 4.1 Week 1, day by day (7 days)

| Day | Track A | Track B | Overnight | Decisions / ships |
|---|---|---|---|---|
| Mon 9/28 | Evidence copy by allowlist, and the off-repo archive; holdout draw; production check script written and scp'd (runs in the worker container) | Phase-parse fix + Skrat's fixture + `board.py` on both paths | – | Decisions 0, 1, 2, 7, 8, 17, 18 (30-min session); Node installed |
| Tue 9/29 | Hook logging + test; nudge flag + test; freeze note; doc corrections | Combo section stopgap | – | |
| Wed 9/30 | `forge_index.py` + flagged-share check; `parse_dck` suffix strip + cache purge | Stopgap finish; machine strings | 0.16.0 vs 0.15.0 Richard pod (16 + 16), the R0 gate; precon re-query | |
| Thu 10/1 | DFC normalisation + fixtures; import pre-check | `GET /estimate`, whole rotations, `fmtClock` | – | Read the R0 gate |
| Fri 10/2 | `run_sim` unsupported cards + commander fidelity; production check readout | R0 build and deploy (with Vincent) | – | **R0**; decision 13 |

**Cut line for week 1.** If the week slips, the import pre-check moves to week 2. The phase-parse fix, the combo stopgap and the production shim pin never slip.

### 4.2 Week 2, day by day (7 days)

| Day | Track A | Track B | Overnight | Decisions / ships |
|---|---|---|---|---|
| Mon 10/5 | `make_dck`, regenerate 32 decks, deck name map; `qa` skeleton | Knockouts analyzer | E7 Ral fidelity (8 + 8) | |
| Tue 10/6 | `qa/tutors` + port test with manifest (316/718 ±5%) | Knockouts: deck-outs; check Richard's game 1 | Tutor backfill over the corpus | |
| Wed 10/7 | Hotfix plan data: `combo_bands` v0, `plan.lines` vs `threatLines`, `graveyardTargets`, `_FINISHER`; byte-identity test | Turning-point computation (zones / inferred) | – | |
| Thu 10/8 | Shim 0.17.0: `fix.*` flags, `reach=` logging, `threatLines` read | – (review) | – | |
| Fri 10/9 | `seedForge`, lint, 2-game smoke; **G0a PREREG committed**; launch | – | **G0a arms** Fri–Sun; E2 determinism within 0.17.0; flags-off 0.17.0 vs 0.16.0 rate comparison | Decisions 11, 19 |

### 4.3 Weeks 3 to 21

| Week | Track A | Track B | Overnight | Gates / releases |
|---|---|---|---|---|
| 3 (10/12) | G0a read (Tue); WS3 spike (Wed) → route; `--scenario` flag; writer; S1–S9 + C1 files | Knockout and turning-point hand audit (Mon); payload + commander names + readapt; knockout UI, out seats, turning point; `POST /flags` + `MTG_FLAG_KEYS` + button; prediction label; R1 | Stock baselines on the suite (Fri); Precon-8 rank check for R1 | **G0a Tue 10/13**; **G-harness Wed 10/14**; decision 4 Fri; **R1 Fri 10/16** |
| 4 (10/19) | **E1 prototype** Mon–Thu (generic path, trigger binding, stop, outlet; S1–S4, S6; 2-core timing) | Richard's before/after pack (Mon); layer A plumbing + Dockerfile COPYs + preflight; disclosures; pilot/validity/telemetry | E1 scenario runs Wed–Thu | **G1 Fri 10/23**; **R1.1 Fri 10/23** (qa.json on every run; disclosures); testers recruited |
| 5 (10/26) | Detectors: funnel, lines, refusals, self_harm, runaway, response; timeline + board_accuracy | Amendment A screenshots → decision 5 (Wed); amendment A CSS; G-UX logistics; `predict.py` sign; leaderboard split | Backfill the new detectors | |
| 6 (11/2) | Analysis switch + scorecard; manifests + `BASELINE.md`; PREREGs for E3, E5, E6, E8; E6/E8 configs | Home rewrite; type adoption, part 1 | E6 Magda + E8 combat data (Fri–Sun) | **G0b Thu 11/5** |
| 7 (11/9) | WS8: slim fields, band map (+ expert overrides), families, cap, composition | Type adoption, part 2 (focus ring, skip link); layer B tools (pull, render_moment, aggregate, validate) | – | **G2a Mon 11/9** (E6, E8); **R2 Fri 11/13** |
| 8 (11/16) | WS8: DeckLines per run, owner sidecar, acceptance; merge the generic path as 0.18.0 + readmit classes; stock+readmit config | G-UX sessions Thu–Fri; instrumentation; blind-sample extractor | Stock+readmit A/A (Tue); E3 (Wed–Sun) | **G-lines Thu 11/19**; **G-UX Fri 11/20** |
| 9 (11/23, holiday; 5 days) | G2b read; Phase B: StepRunner core, arming, wiring at `:1068` (on NO-GO: T2) | REVIEWER.md, `nightly.py`, `claude -p` check, scheduling; private data repo + worktree; calibration set + Richard's link list | Reviewer shadow mode starts | **G2b Mon 11/23** (E3) |
| 10 (11/30) | Seq stamping (zones, agent_events, search_seen; readapt); T2 tiers on DeckLines | Replay basics | T2 arms (Thu–Sun) | – |
| 11 (12/7) | G2c read; Phase B: templates, scripts + scenarios for the top dev lines | Overrides loader, validator, post-merge watch; delete the plan_feedback nudge; five-band section, part 1; Vincent labels 20 moments | Scenario suite nightly | **G2c Mon 12/7** (T2) |
| 12 (12/14) | WS7: Oracle sequencing + protection response | Five-band section finish; human trace schema + `trace_entry.py`; R2.1 | E5 (Fri–Sun); Precon-8 rank check | **R2.1 Wed 12/16** |
| 13 (12/21, holiday; 2 days) | G2d read; Phase B: loop caps, logging | – | – | **G2d Mon 12/21** (E5 + protection) |
| 14 (12/28, holiday; 2 days) | Phase B finish; **G3 PREREG** (conversion and speed targets from G1 × arming rate) | Richard labels 30 moments (async, over W12–W14) | – | |
| 15 (1/4) | G3 arms prep; misplay detectors; GPL constant audit | Report v1, part 1 | **G3 arms** Fri–Sun (dev, holdout, Richard, readmit opponents); VM idle-queue timing on Sat | **G5 Fri 1/8** |
| 16 (1/11) | **G3 read Mon**; fixes; executor production flag + VM CPU check; mulligan data | Report v1, part 2 | Precon-8 rank check | **G3 Mon 1/11** |
| 17 (1/18) | T3: plan-seat KeyCards copy + tutor window | Win cons, part 1 | E4 (Thu–Sun) | **R3 Wed 1/20**; **G4 Fri 1/22** |
| 18 (1/25) | Baselines re-measured under the new pilot; first override PRs from human-confirmed patterns | Win cons finish; Pilot's notes | Baseline runs | **G2e Mon 1/25** (E4) |
| 19 (2/1) | From here, Track A capacity moves to product; curated outlet table only if measured useful; human baseline scored | Pilot's notes finish; theatre starts | – | **R4 Fri 2/5** |
| 20–21 (2/8–2/19) | Product support | Theatre and pacing; deck page; palette B | – | **R5 Fri 2/26** |

### 4.4 Critical path and gates

**Engine critical path:**
1. WS0 and WS4 (week 1)
2. `tutors` port test + hotfix → **G0a (Tue 10/13)**
3. Harness spike (Wed 10/14) → your adapter sign-off (Fri 10/16)
4. E1 → **G1 (Fri 10/23)**
5. Detectors and scorecard → **G0b (Thu 11/5)**
6. WS8 → **G-lines (Thu 11/19)**
7. Phase B (W9, W11, W13–W14)
8. **G3 (Mon 1/11)** → R3 (Wed 1/20)

A slip at the harness, G1 or WS8 moves G3 day for day.

**Product critical path:**
1. Phase parse, stopgap, strings → R0 (10/2)
2. Knockouts (audited) → R1 (10/16)
3. Amendment A approval (10/28) → feel (weeks 5–7) → R2 (11/13)
4. **G-UX (11/20)**
5. Five bands (W11–W12) → Report v1 (W15–W16) → Win cons (W17–W18)

WS5 T2 and T3, WS6, WS7 and WS10 fill the days when an overnight run is pending.

| Gate | When | Measured on | Pass | Fail branch |
|---|---|---|---|---|
| **R0 gate** | Thu 10/1 | 0.16.0 vs 0.15.0, Richard pod 16 + 16 (unpaired) | Re-ask events 0; no crashes; other agent-event rates within 2 SE | Stay on 0.15.0; R0 ships the UI only |
| **G0a: hotfix ships** | Tue 10/13 | cEDH-A all-plan + Richard pod, same jar, flags off vs on; `tutors` port-tested | Unreachable `tutor_cast` ≤ 5%. 0 graveyard steers onto cards with no graveyard use (baseline: Sol Ring ×2). 0 forced X or failed-target casts. Guards: tutor casts per drawn ≥ 50%; Oracle alternate wins ≥ 70% of control; `counter_fire` within ±25% of control (`threatLines` check); no deck down by more than 2 SE (game-clustered). Flags-off 0.17.0 matches 0.16.0 agent-event rates within 2 SE. | R1 ships the truth patch with the hotfix flags off. Each flag alone overnight (5 arms); re-decide Thu 10/15. |
| **G-harness** | Wed 10/14 | spike | 4-player GameState works | 2-player states; otherwise GameAction zone moves (+1 day; G1 moves to Tue 10/27) |
| **G1: executor** | Fri 10/23 | S1, S2, S3, S4, S6, C1 × 20 | GO → merge the generic path; Phase B | PARTIAL: activation-only build + 1-day GameSimulator line-check spike. NO-GO: stop the executor; Phase B slots go to tutoring, spell readmission and UX phase 2; file an upstream issue. |
| **G0b: detectors trustworthy** | Thu 11/5 | full port test with manifests | Experiments may be read. If the ranking changes, re-plan W7 onward. | Fix the detector; experiments may run, but results are held |
| **G2a–e: cheap levers** | 11/9 (E6, E8); 11/23 (E3); 12/7 (T2); 12/21 (E5); 1/25 (E4) | per PREREG | Each lever that meets its PREREG ships behind a flag in the next release | The lever is dropped and its RESULTS.md says why. If readmission self-harm is over its bound, ship the `forge_ai` class only. |
| **G-lines** | Thu 11/19 | WS8 static acceptance (dev decks); holdout lines scored blind | T2, the five-band section and Phase B scripts build on DeckLines | Ship the families and bands that pass; Phase B on hand-written scenario scripts; T2 on passing lines only |
| **G-UX** | Fri 11/20 | validation sessions (two builds on the VM) | Phase-2 order as measured | Fix the failing phase-1 item first |
| **G5: reviewer counts** | Fri 1/8 | kappa on 50 labelled moments | ≥ 0.6: its judgements count in digests and it may propose overrides | Advisory only; humans judge; re-sample monthly |
| **G3: executor ships** | Mon 1/11 | WS9 table; dev and holdout side by side; holdout ≥ 30 assembled drivable lines | Production flag on for plan seats after the VM CPU check | Too fast (mean win round < 5.0, or responses < 20%): ship behind a "ceiling" label and do interaction work first. CPU over budget: lower the caps; ship only lines verified on the VM. Conversion under target: ship only the templates that pass, per deck. |
| **G4: combat unfreeze** | Fri 1/22 | scorecard + QA digest | Only if the WS9 and WS5 targets are met and a combat detector ranks in the top 3 by rate × severity | Stays frozen |

**Pre-registered experiments** (each gets `studies/<name>/PREREG.md` before it runs):

| ID | Question | Arms | n | Pass |
|---|---|---|---|---|
| E0 | Does the hotfix remove the harms without collateral? | 0.17.0 flags off / on | 64 × 2 cEDH-A + 16 × 2 Richard | G0a row |
| E1 | Does a thin step interpreter convert? | stock / prototype | 20 trials × 6 scenarios (incl. C1) | G1 row |
| E2 | Does seeding pair opening hands? | same seed twice, within 0.17.0 | 10 pairs | 10/10 identical up to the first decision |
| E3 | Does readmission play flagged cards without self-harm? | (a) control, (b) plan-seat readmit, (c) (b) + stock+readmit opponents; plus Richard pod | 96 per arm; Richard 16 × 2; A/A 96 | Flagged use ≥ 50%; self-harm ≤ control and ≤ 2/256; control integrity unchanged; A/A within noise |
| E4 | Do KeyCards and the tutor window fix tutor timing and picks? | control / plan-seat KeyCards copy / + tutor window | 64 per arm | Library-top tutors before main phase 2 ≥ 50%; used the same turn ≥ 50%; creature share of generic fetches ≤ 50% |
| E5 | Does the Oracle fix stop self-decks without losing wins? Does protection respond? | flags off / on | 64 plan games per Oracle deck per arm; cEDH-A for protection | ≤ 1 self-deck per 64; wins per Consultation cast ≥ control; protection ≥ 50% |
| E6 | Is Magda's loss the Portal override? | (a) current, (b) T1 + Portal tier 9, (c) steering off | 48 plan-Magda games per arm | Arm (b): Portal fetched when offered ≥ 80% (firm); win share ≥ 28% (directional) |
| E7 | Do the Ral decks now load their commander? | Ral decks after DFC normalisation | 8 + 8 | Commander cast in ≥ 70% of games (fidelity read only) |
| E8 | Do stock-value combat dials cut self-inflicted errors? | defaults / cleaned | 64 cEDH-A + 16 Richard | WS10 table with guards |

### 4.5 Capacity, the re-total and the cut order

**Re-total** (developer-days):

| Item | Days |
|---|---|
| WS0 | 2 |
| WS1 | 14 |
| WS2 | 10 |
| WS3 | 3 |
| WS4 | 3 |
| WS5 | 9 |
| WS6 | 3 |
| WS7 | 3.5 |
| WS8 | 6.5 |
| WS9 | 13.5 (4 + 9.5) |
| WS10 | 3 |
| WS11 | 8 |
| WS12 | 36.5 (11.5 phase 1 and gate + 25 phase 2) |
| Overhead: 9 PREREGs and write-ups (4.5), 8 releases (3), doc updates to CLAUDE.md, DESIGN_SYSTEM and SIM_CALIBRATION (1.5), precon rank checks (2), baselines re-measure (2) | 13 |
| **Total** | **about 128** (about 118 on a NO-GO) |

At 7 days a week, holidays included, the core through G3 (about 95 days) lands at Mon 1/11. Everything else lands by late February.

**The capacity decision (decision 0)** sets the calendar:
- **At about 10 reviewed days a week,** G3 moves to about 12/14 and R5 to late January.
- **With one session only (about 4.5 days a week),** keep the engine gates in order and let the product slip, in this order:
  1. R0 (W1)
  2. R1 with the hotfix and knockouts (W3)
  3. G1 (W5)
  4. G0b (W7)
  5. WS8 (W8–W9)
  6. Feel + G-UX (W10–W11)
  7. Phase B (W12–W17)
  8. G3 (about early February)
  9. UX phase 2 after G3
- **At 2 to 3 days a week,** multiply every interval by 7 divided by your weekly reviewed days. The order and the gates stay the same.

**Cut order** (first to go):
1. Replay theatre and pacing
2. Deck page
3. Palette B
4. Curated outlet table
5. KeyCards and the tutor window (E4)
6. Pilot's notes
7. Misplay detectors beyond the four highest-rate ones
8. The reviewer's blind sample (reduce to 10%)

**Never cut:** WS0 (including the evidence allowlist), WS4, QA layer A, the port test, the harness, E1/G1, the truth patch, the validation gate.

---

## 5. What ships to users when, and what we show Richard

| Release | Date | Users see | What Richard sees |
|---|---|---|---|
| **R0** | Fri 10/2 | Production on shim 0.16.0 (fixes the attack re-ask loop), if the R0 gate passes. Correct phase labels on possessive names. The combo section renamed and folded, with "AI can fire this" gone. No NaN, T36 or "Draw (draw)". Honest duration and whole rotations. Warnings at import for cards Forge can't load. | A short note and a link to their run, re-rendered. The phase labels are right, and the combo section no longer calls 37 engines their win conditions. |
| **R1** | Fri 10/16 | Shim 0.17.0 hotfix, if G0a passes: tutors only chase findable cards, no Sol Ring into the graveyard, no forced X or failed-target tutors. Every knockout with cause, killer and turn (audited). Out seats cleared. "Watch the turning point", if its audit passed. DFC cards load. "Flag this moment". The pilot and shim version on every run. Predictions labelled as fit on stock Forge. | **Mon 10/19, the before/after pack, on their own pod:** a production rerun of 8 games plus a dev-box rerun of 16. It is built from the exact agent events in their run:<br>• `steer=Sol Ring over=Blasphemous Act`<br>• `Nature's Rhythm seeking Staff of Domination`<br>• `Solve the Equation seeking Stella Lee, Wild Card`<br>Each is shown next to the same moment after the fix. Mechanism counts only: **Sol Ring binned 2 → ?**, unreachable tutor casts 4/5 → ?. No win rates, because 8 games cannot show them.<br>One question for them: with Unmarked Grave, is binning Hullbreaker Horror better than stock's Blasphemous Act?<br>An explicit **"not fixed yet"** list: loops, flagged cards, tutor targets by pilotability, tutor timing.<br>They get a flags-only key and are asked to flag up to 5 plays per run. |
| **R1.1** | Fri 10/23 | A `qa.json` for every run. "Cards Forge's AI won't play" on runs and decks. | – |
| **R2** | Fri 11/13 | Opaque reading pages, calm sentence-case buttons, a home page that says what the product does, readable type. The Magda fix and stock-value combat dials, if they passed G2a. | The G-UX session on 11/20 (old build vs new). Their win-con tags for their decks, for example Skrat's: Craterhoof, Triumph of the Hordes, Ezuri's Predation. They are recorded as owner annotations. |
| **R2.1** | Wed 12/16 | Combo lines as five-band families from DeckLines. Tutor targets by pilotability, with owner-tagged win cons at tier 9, if G2c passed. Readmission, if G2b passed. Replay basics. | "Kess cast its flagged cards X of Y times (was 0 of 45)." "The pilot now tutors for the win cons you tagged", with their decks' compiled line model and the question "Right?". 30 moments to label, by text, over the holidays. |
| **R3** | Wed 1/20 | Report v1, focused on the chosen deck. The executor runs verified lines, if G3 and the VM CPU check pass; lines the pilot can run say so. Oracle fix and protection response, if G2d passed. | Report v1 with Skrat's Revenge as the focus deck. Seeded-board clips (Kiki-Jiki + Conscripts; Magda + Clock + Torque) and 3 cEDH replays: "Is this how the line is played?" Their verdicts enter the queue as expert judgements. |
| **R4** | Fri 2/5 | Win cons as owner-tagged cards with cast and won counts. Pilot's notes (whitelist). Tutor window, if G2e passed. | "Which of your win cons got cast?" answered on their own deck. |
| **R5** | Fri 2/26 | Theatre and pacing, deck page, re-measured baselines. | Baselines beside win rates. |

**Expectation to set now.** Richard's pod is four casual decks with engine lines only. The executor will change little there. Their visible gains come from the truth patch, tutoring, readmission and lean combat. The executor shows mainly on cEDH pods.

**Vincent sees:** `studies/scorecard/BASELINE.md` from Thu 11/5, and a weekly QA digest from W10.

---

## 6. Owner decisions needed

| # | Decision | Recommendation | Needed by |
|---|---|---|---|
| 0 | Reviewed developer-days per week | State it. The calendar assumes about 7 (two sessions most weekdays). §4.5 scales everything else. | Mon 9/28 |
| 1 | Freeze combat, personality, hold and attack-targeting work until G4 | **Yes.** Nine combat and personality arms ended at parity, and combat decided at most 2 of 12 human wins. Stock-value dial settings are allowed under the harm-removal exception. | Mon 9/28 |
| 2 | Readmission scope | **Production: every seat** (all are plan seats). **Studies:** the frozen pure-stock control plus a stock+readmit arm with stock dials, after an A/A check. Never without plan data. | Mon 9/28 |
| 3 | KeyCards scope | A plan-seat staged copy in studies. All seats in production, if E4 passes. | W17 |
| 4 | Is the `orderAndPlaySimultaneousSa` override a thin adapter? | **Yes, under the written checklist:** data-named triggers only, delegate to `super` otherwise, no card names or scoring, lint, at most 600 lines. Recorded in the shim README. | Fri 10/16 |
| 5 | DS amendment A: opaque reading surfaces, backdrop only on ceremony screens, sentence case, no resting glow, home §5-6 removed | **Approve from screenshots.** Reversible, and the cheapest fix for the "jank". | Wed 10/28 |
| 6 | DS amendment B: violet retired, monochrome status shapes, `--combat` and `--warn` tokens | Defer until after G-UX. | W9 |
| 7 | Install Node LTS on the dev box | **Yes, on day 1.** Track B's early work is almost all UI. VM builds compete with sims on 2 vCPU, and `next build` kills a running dev server. | Mon 9/28 |
| 8 | Retire random block skips and the "humanized" claim | **Yes.** You chose play quality on 08-26, and random skips read as bugs to an expert. Applied through E8. | Mon 9/28 |
| 9 | Where the knowledge base lives | Compiler inputs, tools, scenarios and overrides in the main repo's `simkb/`. Generated and human data in a **private data repo** (a private repo in your existing GitHub account, or local-only with backup). Per-run output on the VM. Add the data repo and `studies/diagnosis_2026-09/local/` to the strip-before-public list. | W9 |
| 10 | Reviewer schedule and authority | Nightly, proposals only, in its own data-repo worktree, never pushes. Every override is a PR you merge for at least 6 weeks. | W9 |
| 11 | Flag queue owner, and a key for Richard | You triage for 30 minutes a week. You generate a **flags-only** key (`MTG_FLAG_KEYS`), so Richard's key cannot start sims. | Fri 10/9 |
| 12 | Where owner data (win-con tags, band notes) lives before accounts exist | A deck sidecar in `$MTG_DATA_DIR/decks/`, editable with the API key. The UI says "saved for this deck". | W8 |
| 13 | Archetype baselines (CLAUDE.md "show them" vs SIM_CALIBRATION "re-measure first") | **Re-measure after G3 (W18).** Until then show only the labelled pod average. **Amend CLAUDE.md and SIM_CALIBRATION in the same commit** as the decision, so the invariant is not silently broken for months. | Fri 10/2 |
| 14 | Human ground truth | 50 labelled moments (you 20 in W11, Richard 30 over W12–W14). Human traces with `trace_entry.py`: you own it, first 2 games over the holidays, 10 by W20. Supply 8 fresh cEDH lists if the holdout falls short. | Mon 10/19 |
| 15 | Flat cost-glyph commission | Defer. Use painted pips at 18px or larger meanwhile. | W18 |
| 16 | Executor in production | Off until G3 plus the VM CPU check, then on for plan seats. | W16 |
| 17 | Precons for calibration only; `model_runs_agent.json` stays uncommitted | **Yes / yes.** Refit on clean arms after G3. | Mon 9/28 |
| 18 | Capacity: two sessions or one | Two sessions through R2. Then you choose; the §4.5 order and cut list apply. | Mon 9/28 |
| 19 | Prediction model on plan-piloted runs | Label it "fit on stock Forge games" from R1. Run a rank check at each pilot-changing release; suppress if it fails; refit after G3. It is the asset shown to investors, so its conditions must be visible. | Fri 10/9 |

---

## 7. Risks, and how each is caught early

| Risk | Early signal | Response |
|---|---|---|
| The evidence copy commits Forge-derived or shim Java files | Allowlist check (extension, 1 MB cap, content markers) | The file goes to the off-repo archive; the commit is blocked |
| New packages miss the images (`COPY engine/*.py`) | Preflight import check in both containers | Dockerfile COPY lines added in the same PR as the package |
| The ported detectors are wrong | G0a (tutors) and G0b (all) port tests, with manifests | Results held until the detector is fixed |
| The hotfix costs wins (the win-band classifier drops Oracle or Godo lines) | G0a guards: Oracle alternate wins, SE; classifier tests on "Win the game" and infinite-combat lines | Ship the truth patch only; per-flag ablation overnight |
| The QA hook fails silently like `record_run` | Preflight requires a `qa.json` for the latest run; the sweeper backfills | Traceback in logs; errors field |
| GameState cannot seed a 4-player board, or must run on the game thread | Wed 10/14 spike | 2-player states; GameAction zone moves |
| Forced abilities misbehave in Forge's sub-choosers | E1 exceptions and `exec_abort` reasons | PARTIAL or NO-GO branch; every failure aborts to stock |
| The executor overrates combo decks against passive tables | G3 red flags: mean win round < 5.0; responses < 20% in the readmit-opponent arm | "Ceiling" label; interaction work first |
| CPU per game rises on the 2-vCPU VM | 2-core affinity timing at G1; VM idle-queue timing at G3 | Loop caps; +25% budget; the existing 120-turn cap |
| Paired comparisons are not really paired | E2 | Size every n as unpaired |
| Goodhart: a metric met by not acting | Guards table (§3.0) on every target | The change fails its gate |
| Overfitting to the dev decks and Richard's pod | Holdout reported beside dev at G3; holdout lines scored blind at G-lines | Ship only what holds on the holdout |
| The holdout is too thin to judge conversion | Assembled-line count at G3 | More games, up to 64 per pod; then Vincent's fresh lists |
| The stock+readmit arm is not stock | A/A check | Drop the arm; cite only the frozen control |
| The learning loop learns Forge's combat bias or AI choices | Validator rejects `sim_win` and AI-choice evidence for structural kinds | Pilot-defect queue instead |
| A merged override does not do what it claimed | Post-merge watch on the stated mechanism | Removal proposal; expiry |
| The reviewer hallucinates or drifts | Judgements without anchors discarded; kappa gate; monthly blind re-label | Advisory only; job disabled on a write outside its allowed folders |
| Prompt injection through flag notes or deck names | User text fenced as data; no network tools; Bash limited to named scripts; diff check | Job disabled; the item is triaged by hand |
| `claude -p` headless does not work with subscription login | W9 check | Claude desktop scheduled task |
| Subscription limits stall nightly reviews | Queue growth in the digest | 40-moment cap; severity order; human flags first |
| The tutor-timing mechanism changes legality | `ActivationPhases` is read by `SpellAbilityRestriction` | Use the shim's tutor window; `ActivationPhases` only after a harness legality test |
| Opponent threat logic changes when `plan.lines` narrows | G0a `counter_fire` guard | `threatLines` superset |
| The prediction model is shown on runs it was not fit for | Pilot vs `arm` check; rank check per release | Label, then suppress; refit after G3 |
| User or playtester data lands in a repo that may go public | Validator; strip list | Private data repo |
| The GPL module accumulates policy | Card-name lint; W15 constant audit; 600-line budget | Move policy to data; reject Java heuristics in review |
| A public image ships without published source | Release checklist | Shim repo public at the built commit before any image leaves the VM |
| The schedule slips further (G3 is already in January) | Weekly slip against §4.3 | Decision 0; the §4.5 order and cut list; G1 on 10/23 answers the biggest question early |
| Richard disengages | Slow replies | Short sessions; concrete before-and-after from their own games; every flag answered |
| Docs drift | Numbers changing weekly | Same-commit doc updates; refuted claims fixed on day 1 |

---

## 8. What we will NOT do

- No new combat, personality, hold or attack-targeting features or study arms before G4, beyond stock-value dial settings under the harm-removal exception. The 0.16.0 solver stays off.
- No acceptance based on overall win share. No combo or tutor study on precons. No per-deck win-share gates at sample sizes that cannot decide anything. No clustering by pod with two pods.
- No Forge patch or fork. No edits to Forge's card scripts: the RemoveDeck flags stay, and we route around them through public APIs.
- Nothing Forge-derived committed, including evidence folders: class files, disassembly, card-script extracts, shim Java copies. No vendoring, no in-process bridges.
- No card names, heuristics or scoring in shim Java.
- No Forge lookahead as the pilot (it failed 2 of 2 games). At most, a bounded line check after G1.
- No parsing of Spellbook's English into step scripts. A line with no template stays non-drivable, and the product says so.
- No hand-maintained second rules model, such as a curated tutor-reach table. Forge answers reach; the Python ChangeType reader only backfills old runs.
- No learning from sim wins, win methods or the Forge AI's choices. No reviewer change applied without a human merge. No paid API calls. No LLM inside the sim loop.
- No user decklists, playtester texts, judgements or digests in the main repo.
- No "won with this combo" statistic, no "executable" chip without a scenario pass, and no rules verdicts ("lethal", "summoning sick") in product copy.
- No bands or win cons derived from oracle text in the product: Spellbook, expert overrides with a stated basis, and the owner's word.
- No Pilot's notes before the tutor-weight fix. No replay theatre before seq stamping. No phase 2 before the validation gate. No new disclaimer paragraphs, and no LLM-written ledes.
- No baselines shown until re-measured. No power score, letter grade or one-decimal composite.
- No revival of the precon "synergy lines" fallback.
- No gameplay creep: no opponent, no adjudication and no declared outcomes in Playtest.
- No new infrastructure (Postgres, accounts, object storage). No extra API replicas. No public push of the worker image without the shim source published at the built commit.

---

## Appendix A: evidence map

The diagnosis file is `studies/diagnosis_2026-09/diag_result.json` after day 1; today it is in the scratchpad.

| Claim | Evidence (file → figure) |
|---|---|
| **RC1** no combo executor | `synthesis.root_causes[0]`: `PlanPlayerController.java:1068` "assembled, done here"; `:1251` spells only. 167 permanent completions → 5 same-turn wins; 49 spell completions → 24 same-turn. Kiki copy untapped Kiki 0/8; Emiel untapped Cradle 0/216. 18/235 deck-lines (10 of 122 piece sets) drivable. Godo + Helm 28/32 once attached (59 same-turn wins). Human mean win round 5.0 vs stock 12.7; plan 13.1 → 8.8 upper bound. |
| **RC2** catalogue as flat sets | `root_causes[1]`, `verified: resource-only-lines`: 168/238 (71%) produce no win (93% strict); 17/238 say "Win the game"; 7/32 decks with no win line; outlets at value 1 picked 0 times in about 2,100 searches; 529/866 steers onto engine-only pieces; outlet count 126/168 or 107/168 (151 not reproducible). Verified finding 20, corrected: human line present 5/11, 3 outlet misses, 1 decklist drift, 2 unscorable. |
| **RC3** RemoveDeck hard filter | `root_causes[2]`: `AiController.getSpellAbilityToPlay` removeIf at offsets 258-264. Flagged cards 12.1% (285/2362) of cEDH nonland cards; stock casts 178/3430 (5.2%) vs unflagged 63.1%; plan 24.6%; printed flagged permanents 1/459; Clock of Omens 0 in 135; 91/238 lines contain a flagged piece; one precon commander (Winter, Cynical Opportunist) never cast. |
| **RC4** values by membership; absolute steer | `root_causes[3]`; verified finding 23, corrected: Magda 47/47 overridden (68/68 across 5 arms): 33 by combo steer (`:1792`), 14 by plan-mode value 8 vs Portal's 6. 0/72 Portal fetches; Portal landed 10% vs 53%; wins 7/48 (15%) vs 47/144 (33%), Fisher p=0.016. plan_feedback combat nudge (`plan_feedback.py:169-208`). Richard: `plans_rebuilt.json` values Hullbreaker and Sol Ring at 8 over Archon and Craterhoof at 6. |
| **RC5** tutor_cast has no reach, zone or mode model | `root_causes[4]`: 316/718 (44%) unreachable (221/222 confirmed by Forge's offers); 285/498 undeliverable; 98 sought pieces already in graveyard or exile; 18/18 X tutors at X=0; 26 failed to target (Dizzy Spell, Muddle the Mixture, Intuition, Gifts); Magda gate from the command zone in 32/37. Verified finding 29, corrected: two pieces short 36–41%; one short with the gate open 42–54%. Richard's run: 4 of 5 `tutor_cast` unreachable. |
| **RC6** blind research system | `root_causes[5]`, `measurement_problems`: Oracle decks +17.7 pp (20/96 vs 9/288), the rest −6.8 pp, pooled into parity; 6,135-game corpus, 7–12% combo-focused; 0 of about 10 gates measured conversion or win round; precon arms 0–4 combo casts per 768 games. |
| **RC7** Forge tutor timing and pick | `root_causes[6]`: `ChangeZoneAi.hiddenOriginCanPlayAI`; stock library-top tutors 0/269 before main phase 2; 51/72 hand-tutored cards unused that turn; creatures 186/195 of generic fetches (unverified); KeyCards unused. `ActivationPhases` appears in `SpellAbilityRestriction.class` (a legality parameter). |
| **RC8** Oracle by accident | `root_causes[7]`: `:1094` checks `getStackZone()`; 49 Consultation casts, 31 into the trigger (25 won, 3 named a card still in the library, 2 countered); 14 self-decks; 53/92 Oracle casts spent the ETB. |
| **RC9** input fidelity | `root_causes[8]`: 16 DFC names, 48 slots, 23/32 decks; joseph_ral 0 command-zone exits in 30 games; `parse_dck` suffix → 38/39 precon cache entries empty; a clean re-query finds 14/66 precons with 26 variants. |
| **RC10** non-combo shim layers | `root_causes[9]` (all unverified): moved attackers die 9.4% split / 7.7% kingmaker vs 2.8% unmoved; chumps 0.30–0.63 vs 0.08–0.09; `counter_fire` on mana sources 73/209; 69/228 hands with ≤ 1 land and 3+ sources; protection 1/39. Richard's run (checked): 43 `block_skip`, 41 `split`, 17 `kingmaker_reaim` in 8 games. |
| Measurement: "converted" is correlation | `measurement_problems`: 79 of 115 badged rows are pure engines; 19/86 text-vs-zone flips (`analysis.py:282`); 7/15 "combat" finals were not combat; 13 deck-outs unclassified; runaway loops 13/45 timeouts (unverified); human baseline is 12 creator-picked games. |
| Refuted claims | `synthesis.refuted`: "stock never casts tutors" (it casts 594/892); "precons have no combos"; "Forge cannot pilot storm" (Ral had no commander); the 151/168 outlet count. |
| Product: Richard's combo table | `richard/plans_rebuilt.json`: 37 lines; UX review §2 #2: 0 of 37 win alone; Stella alone listed as a combo. |
| Richard: Kess graveyard steering (checked for this plan) | Result file agent events: 16 Kess `search_seen` with `dest=Graveyard`, 12 with `agree=false`. Plan picks: Hullbreaker Horror 5, Toxrill 2, Unexpected Windfall 2, Big Score 1, Sol Ring 2. Both Sol Ring steers were over Blasphemous Act. The 2 exile-destination steers picked Sol Ring and Big Score over basic lands. |
| Post-run hook placement (checked) | `mtg_engine.py:259-268`: `record_run` in a bare `except: pass` inside `Engine.simulate`. `worker.process_one` calls `jobqueue.finish` after `simulate` returns. |
| `record_run` in production (unverified) | `richard/cache/plan_feedback.json`: four decks, `games: 0`, no `_runs` key. The critic's local run of `record_run` on Richard's result file completed and recorded 7 games each. |
| Images copy the top level only (checked) | `Dockerfile.api:7` and `Dockerfile.worker:70`: `COPY engine/*.py /app/engine/`; `engine/models/` copied separately. |
| Flat key set (checked) | `mtg_engine.py:620`: `API_KEYS = {k.strip() for k in os.environ.get("MTG_API_KEYS", "")...}`. |
| Prediction model arm (checked) | `engine/models/precon_predict.json`: `"arm": "stock Forge, decided games"`. Richard's run is plan-piloted. |
| Agent events have no seq (checked) | Richard's result: `agent_events` records hold `turn`, `player`, `event`, `detail` only. |
| Evidence folder contents (checked) | `scratchpad/diagnosis`: 280 MB; 600 `.class`, 8 `.java`, 10 javap files, 31 files over 1 MB, 276 `.py` and `.md` files. |
| Holdout eligibility (checked) | `studies/human_ceiling/decks/`: 8 pods. n7 and 2iA are cEDH-A; 5A6o shares rog_ishai; OuY6 is used by S1. That leaves B421, Bq-n, CxKM, sZA0. |
| Unpaired seeds | `SimShim.java:346-351`: stock seats use Forge's unseeded RNG; `PlanPlayerController.java:76` seeds only the plan controller. |
| API has no Forge | `deploy/Dockerfile.api`: `python:3.12-slim`, copies `engine/*.py`, `engine/models/` and `rules/kb`. |
| Cache has no layout | `engine/cards.py:147-172` `_slim()`: no `layout` field. |
| Production shim 0.15.0 | Richard's result meta: `simlab-forge-shim/0.15.0`; shim `62fe295` (0.16.0) fixes the re-ask loop with dials off by default. |
| Opponent logic reads plan lines | `PlanPlayerController.java:946` `line_completion_seen`; `:2084-2093` `lineProximity`. |
| Scoring constants in Java | `PlanPlayerController.java` 2,179 lines; `THREAT_EYEBALL_CAP` `:2058`; "twitchy" `:906`. |
| UX problems | `ux_final.md` §2 #1–#15; §9.1 engine prerequisites 1–9; §9.2 phase 1; §9.3 validation gate; §9.4 deferrals. |

---

## Appendix B: first two weeks task list

Each task fits in one sitting. On the dev box, use `py`, not `python3`.

**Week 1**
1. **Owner memo** for decisions 0, 1, 2, 7, 8, 17 and 18.
   - Touch: `tasks/README.md`, adding a "Decisions 2026-09-28" section.
   - Verify: Vincent's answers are recorded in the file.
2. **Node on the dev box** (if decision 7 is yes).
   - Verify: `cd web && npm run verify` passes locally.
3. **Copy the evidence by allowlist.**
   - Touch: new `studies/diagnosis_2026-09/` with `README.md`, a `.gitignore` covering `local/`, and `check_allowlist.py`.
   - Verify:
     - `py studies/diagnosis_2026-09/check_allowlist.py` passes. It checks that every tracked file is `.py`, `.md`, `.json` or `.txt`, is at most 1 MB, and has no class-file magic, "Compiled from" javap headers or `package forge`/`package simlab` Java.
     - The zip exists at `C:\Users\Vatto\simlab-archive\diagnosis_2026-09.zip`, with its SHA-256 recorded in the README.
     - `gs/`, `gs2/`, `jarx/`, `shimcopy/` and `richard/` are absent from git.
4. **Holdout draw.**
   - Touch: new `studies/holdout/HOLDOUT.md` recording the rule, the 4 eligible pods, the lot (seeded from the commit hash of this file's parent), the draw and a hash.
   - Verify: committed before any template or tier work.
5. **Production check script.**
   - Touch: new `deploy/checks/prod_check.sh`, scp'd and run over gcloud ssh. It runs `preflight.py --files`, prints `COMMIT` and the version, summarises `plan_feedback.json`, counts " // " in `/data/decks`, and runs `record_run` **in the worker container** against a copy of the real `/data/plan_feedback.json`.
   - Verify: the output is saved as `studies/diagnosis_2026-09/prod_check_0928.md`, with the traceback or "completed" recorded, and the snapshot's provenance noted.
6. **Hook logging.**
   - Touch: `engine/mtg_engine.py:259-268`; new `engine/tests/test_post_run_hook.py`, which monkeypatches `record_run` to raise.
   - Verify: the test prints ALL ASSERTIONS PASSED, and the full engine loop passes.
7. **Nudge gate.**
   - Touch: `engine/deck_plan.py:495-501` (`MTG_PLAN_FEEDBACK_APPLY`, default 0); new `engine/tests/test_plan_feedback_gate.py`.
   - Verify: a synthetic store with the flag at 0 gives a byte-identical plan.
8. **Freeze note and doc corrections.**
   - Touch: `tasks/README.md`, `engine/SIM_CALIBRATION.md`, `engine/deck_plan.py` (comments at 160-163 and 395-397), `tasks/20-*.md:323-326`, `studies/agent_viability/run_pilot.py:4-5`, `studies/agent_viability/RESULTS.md:10-11`, `studies/human_ceiling/RESULTS.md:15`, plus the task 21 and cc8c446 results annotations.
   - Verify: `grep -rn "never casts tutors\|ZERO combo\|cannot pilot storm"` returns nothing outside the correction notes.
9. **Phase-parse fix** (Track B).
   - Touch: `web/lib/replay.ts:245`, `engine/forge_log_adapter.py` (same pattern), and a new Skrat's fixture under `engine/tests/fixtures/`.
   - Verify: `py engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch` gives an unchanged `exit_match_rate`; the same holds on one shim result; the fixture test passes.
10. **Spellbook suffix strip.**
    - Touch: `engine/combos.py:61` `parse_dck`; purge the poisoned `combo_cache.json` entries; re-query overnight.
    - Verify: 14/66 precons with 26 included variants.
11. **Forge index.**
    - Touch: new `engine/forge_index.py`; worker startup call in `engine/worker.py`.
    - Verify:
      - The flagged share of cEDH nonland cards is 12.1% ±0.5 pp.
      - Demonic Consultation, Vampiric Tutor, Clock of Omens and Winter, Cynical Opportunist are flagged. Thassa's Oracle and Tainted Pact are not.
      - No generated file is under git.
12. **DFC normalisation and import pre-check.**
    - Touch: `engine/convert_decklist.py`; `engine/tests/test_convert_decklist.py`, with fixtures Ral, Monsoon Mage; Birgi; a modal land; one split card.
    - Verify: the test passes; the split card keeps " // "; a flagged commander produces the warning.
13. **Unsupported cards and commander fidelity.**
    - Touch: `engine/run_sim.py:214-251`.
    - Verify: a 2-game run of the old joseph_ral deck reports the refusals. The re-converted deck reports none, and its commander appears in zones.
14. **Combo section stopgap** (Track B).
    - Touch: `web/app/results/[file]/page.tsx:438-633`, and the import page copy.
    - Verify: grep for "AI can fire this" returns 0; Richard's run shows folded rows; the ui-review skill passes.
15. **Machine strings and estimate** (Track B).
    - Touch: `web/lib/format.ts:118-124` (delete the table), a new `GET /estimate` in `engine/mtg_engine.py`, the `/new` page (whole rotations, played count), `fmtClock`.
    - Verify: `smoke_test.py` passes; no "NaN" on 8 audited routes.
16. **R0 deploy** (with Vincent).
    - Touch: `deploy/` (pin 0.16.0 via `SIMLAB_SHIM_REF` or the vendored jar), `deploy/preflight.py` (assert the shim is at least the pin and the nudge flag is off).
    - Verify:
      - The Wednesday R0 gate passed.
      - `sudo docker exec deploy-api-1 python3 /app/deploy/preflight.py --files` passes.
      - `smoke_test.py --sim` passes.
      - Richard's run renders with the correct phase labels and the renamed combo section.

**Week 2**

17. **Study decks.**
    - Touch: `studies/human_ceiling/tools/make_dck.py:53-56`; regenerate the 32 decks; map line names in `deck_plan.py`; queue E7 overnight.
    - Verify: a stderr scan finds 0 DFC refusals. E7 reads only whether the commander was cast.
18. **Tutor detector and port test.**
    - Touch: new `engine/qa/__init__.py`, `engine/qa/tutors.py`, `studies/scorecard/manifests/tutor_unreachable.json`.
    - Verify: 316/718 ±5% on the manifest's run set. On Richard's run: 4 of 5 `tutor_cast` unreachable, and the Kess steers classified as 2 with no graveyard use and 10 reanimation or castable-from-graveyard.
19. **Knockouts analyzer and turning point** (Track B).
    - Touch: new `engine/qa/knockouts.py`; `analysis.win_method` reads it.
    - Verify: on Richard's game 1, Stella and Krenko are out on turn 9 (poison) and Kess on turn 10 (combat), or a documented correction. 13/13 deck-outs are classified on the corpus.
20. **Hotfix plan data.**
    - Touch: new `engine/combo_bands.py` (v0); `engine/deck_plan.py` (`plan.lines` vs `plan.threatLines`, `graveyardTargets`, the `_FINISHER` fix at `:124`), all behind `planVersion`; new `engine/tests/test_plan_hotfix.py`.
    - Verify:
      - Flags off gives a byte-identical plan.
      - Oracle + Consultation stays in `plan.lines`.
      - Hullbreaker + Sol Ring moves to `threatLines` only.
      - Magda + Clock + Torque leaves `plan.lines`, a documented, intended change.
21. **Shim 0.17.0.**
    - Touch: `simlab-forge-shim/src/simlab/shim/PlanPlayerController.java` (`fix.tutorReach` with `reach=` logging, `fix.commanderTutorZone`, `fix.noForcedChoices`, `fix.graveyardDest`, `tutor_skip` logging, `threatLines` read at `:928-1004` and `:2084-2093`); `SimShim.java` (`seedForge`); README version notes; the card-name lint.
    - Verify:
      - `build.sh` passes.
      - A 2-game smoke run echoes the flags and plan provenance in the log header.
      - E2: the same seed within 0.17.0 gives identical opening hands in 10/10 pairs.
      - Flags-off 0.17.0 matches 0.16.0 agent-event rates per seat-game within 2 SE.
22. **G0a PREREG and launch.**
    - Touch: new `studies/hotfix_g0/PREREG.md` (hypotheses, metrics, thresholds and guards from §4.4, n, pass and fail actions); arms config.
    - Verify: the PREREG commit timestamp is earlier than the run's `meta.started`.

---

## Appendix C: judges' blocking issues and where each is handled

| Blocking issue | Handled in |
|---|---|
| The post-run hook swallows errors; whether `record_run` completes in production is unknown | WS0 tasks 3–4 (repro in the worker container, against real data); WS2 layer A (launched after `jobqueue.finish`, errors field, sweeper, preflight) |
| Evidence and detectors live in Temp | WS0 task 1 (allowlist, off-repo archive); Appendix B task 3 |
| Production on 0.15.0; releases unpinned | WS0 task 6 (with the R0 gate); §2.3; R0 |
| Same-jar controls | §2.3 (plan-data flags); every PREREG |
| `orderAndPlaySimultaneousSa` sign-off | WS9 "Before E1"; owner decision 4 (Fri 10/16) |
| UI builds only on the VM | Owner decision 7 (Mon 9/28); VM builds only as fallback |
| `claude -p` under subscription unverified | WS2 layer B (checked W9; desktop fallback) |
| GameState multi-seat and game-thread use | WS3 mechanism notes; G-harness Wed 10/14 |
| API container has no Forge | WS4 task 1 (`forge_index` on `/data`) |
| New modules not copied into images | WS2 layer A task 2; preflight import check |
| Narrowing `plan.lines` changes other seats | WS5 T1 (`threatLines`); G0a `counter_fire` guard |
| DFC normalisation needs layout | WS4 task 2 (Forge index first; `layout` in the cache as fallback) |
| `ActivationPhases` may be a legality restriction | WS5 T3 (tutor window first; harness legality test before any use) |
| QA hook runs before the job finishes | WS2 layer A (from `process_one` after `finish`; detached, niced, bounded) |
| GPL drift in existing Java constants | WS10 task 5 |
| Effort vs capacity | §4.5 (re-total, decision 0, single-session order, cut order) |
| Paired designs do not exist | §3.0 pairing; E2 within 0.17.0 |
| Arm-neutral conversion | §3.0 metric definitions |
| Goodhart counter-metrics | §3.0 guards table; guard columns in WS5, WS6, WS7, WS10 |
| No holdout; holdout too small | §3.0 cEDH-holdout (drawn day 1, at least 30 assemblies); WS8 targets on dev decks only |
| Per-deck win-share gates uninformative; cluster unit | §2.1 (game-clustered SE; catastrophe guard only) |
| QA selection bias; weak agreement statistics | WS2 (20% blind sample, recall estimate, kappa on 50) |
| AI-choice evidence leaking into ground truth | §2.4; WS2 guardrails; WS7 task 6 (Tainted Pact) |
| Win-round censoring; human 5.0 as a soft floor | §2.1; WS9 targets |
| Passive opponents overstate gains; wall-clock CPU | WS9 G3 arms (readmit opponents, "faced a response", VM timing) |
| Prediction model shown on runs it was not fit for | WS11 task 11; decision 19 |
| Private data in a repo that may go public | WS2 layout (private data repo); decision 9 |

---

## Decisions on the critique

No item was rejected. These items were accepted with a change of detail, or needed a note on how they were applied:

- **1:** Accepted. `richard/` is also excluded from the repo (it holds a playtester's decklists) and goes to the archive, then to the private data repo.
- **2:** Accepted: decision 0 added, weeks 1–2 rebuilt, G0a on Tue 10/13, R1 on Fri 10/16, G1 on Fri 10/23. Later gates slip more than one week, because the re-total (item 24) came out larger. G3 is Mon 1/11.
- **6:** Accepted. The precon rank check runs only at releases that change pilot behaviour (R1, R2, R2.1, R3), not at UI-only releases.
- **8:** Accepted, using both options: dev-box CPU affinity with `-XX:ActiveProcessorCount=2` for G1, and the VM with an idle queue for G3.
- **10:** Accepted. E7 is also limited to a fidelity read, so it can run on a Ral deck that may be drawn into the holdout.
- **14:** Accepted with one nuance. T1 still removes Magda + Clock + Torque from `plan.lines`, because that removal is what stops the Portal override. WS8 restores it in DeckLines as an expert-banded Finisher with `steer: false` until S4 passes.
- **19:** Accepted, by choosing a private data repo over a gitignored folder. The reviewer needs version history and a worktree.
- **20:** Accepted, by adding a flags-only key set (`MTG_FLAG_KEYS`) rather than accepting the risk.
- **23:** Accepted. The turning point ships in R1 only if its own audit passes; otherwise it is labelled "biggest swing" or held.
- **24:** Accepted. The re-total is about 128 days, about 24 above the draft and more than the critic's 12–15 estimate, because each missing item was costed separately.
- **26:** Accepted, with recruitment by week 4 rather than week 2, because G-UX moved to week 8.
- **30:** Accepted. The protection response moved into WS7 (renamed "Oracle sequencing and line protection"), where it is gated at G2d whatever G1 decides.