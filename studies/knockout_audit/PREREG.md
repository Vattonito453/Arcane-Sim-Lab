# Knockout and turning-point hand audit: pre-registration (week 3, before the R1 UI)

Written and committed **before any analyzer output for these runs has been
produced or read**, and before the draw below has been run. The draw is
`draw.py` and the reader instructions are `READER.md`, both committed in the
same commit as this file, so neither the sample nor what readers are asked can
drift toward the data.

Plan references: `tasks/25-repair-plan.md` WS1 acceptance rows "Knockout hand
audit (before the R1 UI): >= 95% agreement on 40 knockouts across 3 runs" and
"Turning-point hand audit (before the R1 UI): >= 16/20 games agree with a human
reading; otherwise it ships as 'biggest swing' or is held"; WS11 task 1 (the
game story reads cause, killer and turn from `qa.knockouts`, and they ship only
after this audit); item 23 of the plan's "Decisions on the critique" (the
turning point ships in R1 only if its own audit passes). Week 3 of the
schedule (section 4.3, the "3 (10/12)" row).

**The analyzer under audit** is `engine/qa/knockouts.py`: git blob
`16ff99d9527fb675c4a1d35099430b641f3c4a6d` on main at `6e4dee8` (with
`engine/qa/context.py` blob `ed6994bc28795fb94b5212d3dfb89b735e04fed4`). Other
week-3 branches may change it before R1; see "Order of work" for how that is
handled.

**The human readings are model readings.** The readers are independent Claude
agents reading the evidence blind, not people. The results will say so on
their first line, and the owner (Vincent) can overrule any item or the verdict.

## What the author saw before writing this

Stated so the reader of the results can judge the blinding.

- The **source** of `engine/qa/knockouts.py` (its docstring and cause
  vocabulary), to state the agreement rules in its vocabulary. It was not run.
  Neither was `engine/analysis.py`, nor any API route that exposes knockouts,
  win methods or turning points (`/analysis/*`, `/results/*/scorecards`).
- The first ~3 KB of an earlier corpus-wide analyzer summary in the session
  scratch folder (`corpus_ko_deckout.json`), opened because the task pointed at
  it as a list of known deck-outs: aggregate cause counts over 129 files and
  the first four deck-out rows. One of those rows concerns a game in this audit
  (run S, game 6, the deck-out). Its content is not repeated here or anywhere
  readers can reach. Nothing below uses it: runs were chosen and the sample is
  drawn from Forge's own records.
- Forge's own records of every local result: the "has lost" and "has won"
  lines of each game's outcome block and `result.winner/draw/timedOut`, used to
  survey loss reasons and choose runs (allowed by the task).
- `py engine/board.py <file> --no-fetch`, for each run's board basis only.
- The repair plan and the UX review contain a first-pass human-model reading of
  game 1 of Richard's run (in `tasks/25-repair-plan.md` WS11 acceptance and
  `tasks/26-ux-review.md`). That reading is not analyzer output, but it is a
  reading of a game in this audit, so readers must not see those files (see
  "What readers must not see").

## The runs

| Label | File | Path (board basis) | Pilot | Games | Decided | Knockouts (Forge loss reasons) | md5 of the audited file |
|---|---|---|---|---|---|---|---|
| **R** | `sim_20260925_003803_d0eb966b8d33_rotated.json` | shim, `zone_stream` (exit_match_rate 1.0) | shim 0.15.0, plan agent, all 4 seats | 8 | 7 | 22: life 20, poison 2 | `396ef82b5d818f67298682af924df3a2` |
| **S** | `sim_20260801_193328.json` | shim, `zone_stream` (exit_match_rate 1.0) | shim 0.2.0 | 6 | 5 | 17: life 13, alternate win 2, poison 1, deck-out 1 | `df282cd5cb44527001e9f229c447d6bd` |
| **T** | `sim_20260723_101044.json` | stock Forge stdout, `inferred` (exit_match_rate 0.9185) | stock Forge AI | 20 | 17 | 51: life 34, poison 9, commander damage 8 | `340c7b65b953ff3f7497be7bf275345c` |

Provenance:

- **R** is Richard's production run, fetched on 2026-09-28 from the public read
  route `GET /engine/results/{file}` into the scratch folder. It was already
  adapted by the current adapter (it carries the `more` continuation field).
  The file is kept byte-for-byte as served, including the `validity` block the
  route attaches. Game 6 is a draw on the 900 s clock with one knockout.
  Richard's decklists and raw logs are private: they are never committed, and
  nor is any evidence file built from this run.
- **S** is a local shim run. Shim 0.2.0 predates 0.3.0, so its zone records
  carry no card types or P/T. Game 1 was cut by that run's 120 s clock with two
  players alive: Forge prints two "has won" lines, so it is not decided, but
  its two eliminations are real. The audited file is a **re-adapted copy**:
  original `c7680af31f089f8303ca41bc67c3ddb5`, raw log
  `shim_raw_20260801_193328_817357.jsonl` (`16938b450c69ca523b44c68ac75fbd9b`)
  re-parsed with the current `shim_log_adapter.py` (blob
  `f6d2bfb513d3cf5acee8188535455f259ac7ae61`); every game keeps its players,
  winner, draw flag and turn count, and 124 combat continuation events are
  recovered.
- **T** is a local stock-Forge run on the stdout path. Games 6, 8 and 19 are
  cut by that run's 240 s clock (every player "has won", no loss lines), so
  they are not decided and have no knockouts. The audited file is a
  **re-adapted copy**: original `08df5deb1781e615b5d291057a07a368`, raw log
  `forge_raw_20260723_101044.log` (`54391cd3640e3f2c7bc0b2b7ccba7507`)
  re-parsed with the current `forge_log_adapter.py` (blob
  `b1ce5d32c055dd5c9da3c181939e75573bc199af`), same fingerprint check, 233
  combat continuation events recovered.

Why re-adapt: both local files were adapted before the 2026-09-01 fix, so they
lack the continuation lines of Forge's multi-line combat entries (CLAUDE.md,
"Forge joins multi-defender combat into ONE multi-line log entry"). Readers and
the analyzer must read the same, complete record, so both read the re-adapted
copies. The originals in `engine/sim_results/` are untouched. `readapt.py`
itself was not used because it only locates shim logs by run id and does not
handle stdout runs; the copy follows its rule (same fingerprint or refuse;
stored meta kept, agent string refreshed, `meta.readapted` set).

Why these runs: R is required. S has the widest spread of Forge loss reasons in
the local results (the only local deck-out, both alternate wins by spell, a
poison loss) and is on the shim path. T is on the stdout path and has the most
commander-damage losses (8) of any local run, plus 9 poison losses. No local
result has a concession or a lose-the-game effect, so those classes cannot be
sampled. "Life total reached 0" covers combat damage, non-combat damage and
drains, which cannot be told apart before reading without running analysis, so
those are sampled at random. None of the three runs uses a holdout pod deck
(`studies/holdout/HOLDOUT.md`) or any cEDH study deck.

## Definitions

- **Game key**: `<label>-g<NN>`, where NN is the game's 1-based index in the
  file's `games` array (the same n as `/results/{file}/game/{n}`).
- **Turn**: the `turn` field of the result file, which is Forge's own game-turn
  counter from its "Turn N (player)" lines. The evidence headers show it.
  Forge's end-of-game outcome block begins with a "Turn N" line of its own on a
  different counter; it is never used.
- **Knockout**: one "<player> has lost ..." line in a game's Forge outcome
  block. Id `<game key>:<player as printed>`.
- **Forge loss reason class** (stratification only): `life` ("life total
  reached 0"), `poison`, `commander` ("damage from generals"), `spell` ("won
  by spell"), `deckout` ("empty library"), `concession`, `other`.
- **Decided game**: `result.winner` set, `result.draw` false, `result.timedOut`
  not true, exactly one "has won" line in the outcome block naming that winner,
  and a "has lost" line for every other seat.

## The draw (`draw.py`, seed 20261012)

`py studies/knockout_audit/draw.py <runs_dir>` checks the three md5s above,
then, with `random.Random(20261012)` and every candidate list sorted first:

1. **Turning-point games (20).** Every decided game of R and S (expected 7 + 5
   = 12). T supplies the rest: its decided games are split into those with at
   least one non-life loss reason ("mixed"; expected 8 games) and all-life
   games (expected 9); half the remainder, rounded up, is drawn from the mixed
   games and the rest from the all-life games (expected 4 + 4).
2. **Reading set.** The turning-point games plus every undecided game of any
   run that has at least one knockout (expected R-g06 and S-g01): 22 games.
3. **Knockout frame.** Every knockout in the reading set (expected 63).
4. **Knockout sample (40).**
   a. Every non-life knockout in the frame, as a census (expected about 14:
      R's 2 poison, S's 2 alternate-win, 1 poison and 1 deck-out, and those in
      T's four mixed games). If there were more than 20, 20 would be drawn in
      proportion to class sizes.
   b. The rest are life knockouts, allocated to the runs in proportion to each
      run's life knockouts in the frame (largest remainder, ties in the order
      R, S, T) and drawn at random within each run.

The knockout sample is clustered in the turning-point games on purpose: every
game in the reading set is read in full twice, so drawing knockouts from other
games would roughly double the reading for the same 40 items. The cost is that
errors within one game are correlated; the results therefore report agreement
per run and per game as well as pooled.

Every game in the reading set is read in full, and readers report **every**
elimination in it, so they cannot tell which knockouts were sampled. Only the
40 sampled knockouts and the 20 turning-point games are scored.

## What readers see

One plain-text evidence file per game in the reading set, built mechanically
after this commit by a script that reads only the result file's event log,
pregame events and, on shim runs, Forge's zone records (and, for S's
pre-0.3.0 zone records, card types from the Scryfall cache, without fetching).
The files stay in the scratch folder and are never committed.

1. **Header**: the game key, the seats exactly as Forge prints them, the board
   basis in plain words (shim: the creature lists are read from Forge's own
   zone records; stdout: Forge's log does not record battlefield entries, so
   the creature lists hold only what the log narrates), and what, if anything,
   was dropped.
2. **The Forge log in order**: pregame lines, then per turn a header with
   Forge's turn number and the active player, then each event as
   `[step] Forge's text`, with continuation text (`more`) indented beneath it.
   Forge's standalone step lines ("X's Upkeep step") are not printed as lines
   of their own; every event carries the step it happened in instead. Pure
   mana and tap lines are dropped **only** from a file that would otherwise
   exceed about 250 KB, and its header then says so and how many were dropped.
3. **A per-turn digest** computed mechanically from the same records: active
   player; spells cast ("P cast X" lines); damage dealt to players (source,
   target, amount, combat or not); life totals at end of turn as last logged;
   poison totals summed from Forge's "receives N poison counter" lines;
   creatures entering and leaving the battlefield (shim: every zone record
   into or out of the battlefield of a creature, with P/T as recorded; stdout:
   creature spells resolving, tokens the log narrates creating, and "put into
   X from Battlefield" lines); and eliminations exactly as Forge prints them.

## What readers must not see

- Any analyzer output: knockouts, causes, killers, cards, turning points, win
  method, board power or swing, flags, `qa.json`, the analysis or scorecard
  routes, or `corpus_ko_*.json`.
- The result JSON itself, the plan agent's `agent_events`, plan files,
  `rubric`, `boardfx`, `validity`.
- The repository (in particular `tasks/25-repair-plan.md` and
  `tasks/26-ux-review.md`, which hold a reading of R-g01), the production site
  or API, Richard's feedback, and every other reader's answers.

Readers get `READER.md`, a batch manifest (game keys, evidence file paths,
whether a turning point is requested) and the evidence files, and are told to
use nothing else.

## Reading passes and how they combine

- **Two independent passes, A and B.** Each pass covers every game of the
  reading set exactly once, split into two batches of roughly equal size (A1,
  A2; B1, B2). Pass B pairs the games differently from pass A, so no pass-B
  reader has the same set of games as a pass-A reader. Each batch is read by a
  fresh agent with no access to any other reading.
- **Third reading (pass C).** After A and B are in, and **before any analyzer
  output for these runs is produced**, every game with a scored item on which
  A and B differ in any recorded field (knockout: turn, cause, killer or card;
  turning point: turn or card) is read in full by a fresh third reader under
  the same instructions.
- **Freeze.** All readings (A, B, C) are committed as JSON under
  `studies/knockout_audit/readings/` before the analyzer is run on these
  files. They hold turns, causes, seat names and card names only; no log text.
- **Human reading of an item**: per field, the value at least two readings
  share; "no consensus" if none (reported, and see below).
- **Verdict of an item**: each reading is compared with the analyzer under the
  agreement rules; the item agrees if the majority of its readings agree. When
  A and B are identical on every field they give one verdict; otherwise pass C
  exists and the majority of three decides. A missing or malformed reading of
  an item counts as a reading that disagrees with the analyzer.

## Agreement rules

**Knockout** (the analyzer's knockout for the same eliminated player in the
same game). It agrees with a reading when all of these hold:

- the same **turn** (Forge's turn number, as defined above);
- the same **cause class**, in the analyzer's vocabulary: `combat_damage`,
  `noncombat_damage`, `life_loss`, `life_total`, `poison`,
  `commander_damage`, `alt_win`, `lose_effect`, `deckout`, `concession`,
  `unknown`;
- the same **killer seat** (the analyzer's `by`; both absent counts as the
  same; seats compared as printed, or with the `Ai(n)-` prefix removed from
  both if one side omits it).

The **card** is scored separately under the same majority rule (names compared
case-insensitively with instance numbers removed) and is not part of the pass
rule. An eliminated player for whom the analyzer reports no knockout
disagrees.

**Turning point** (decided games only). The analyzer agrees with a reading
when its turning-point turn equals the reading's turn, or differs from it by
exactly one Forge turn and names the same card (the analyzer's `card` or
`event_hint`, whichever its output carries; the word `combat` matches
`combat`). A decided game for which the analyzer gives no turning point
disagrees.

## Pass thresholds and what follows

| Audit | Pass | If it passes | If it fails |
|---|---|---|---|
| Knockouts | **>= 38 of 40** agree | Per-knockout turn, cause and killer ship in the R1 UI (WS11 task 1), marked audited | They are held from the R1 UI; WS11 task 3's wording ("life reached 0 (combat or life loss)") stays. The analyzer is fixed on the disagreements, and a fresh audit on a newly drawn sample must pass before they ship |
| Turning point | **>= 16 of 20** agree | It ships as "turning point", marked audited | It ships labelled "biggest swing" or is held (the plan's rule, critique item 23; the owner chooses which) |

- No threshold is pre-registered for the knockout card. The results report its
  agreement, and the owner decides whether the UI names the card.
- Pass rules are read on the pooled items. The results also report agreement
  per run and per path (shim R and S against stdout T), each item's human
  reading next to the analyzer's, every "no consensus" item, and the number of
  pass-C readings.
- The frozen readings do not depend on the analyzer, so a later analyzer
  version can be re-scored against them. A fix made because of a disagreement
  found here must not be accepted on these same items: it needs the fresh draw
  above.

## Order of work

1. This commit: `PREREG.md`, `READER.md`, `draw.py`.
2. Run the draw; build the evidence files and batch manifests (scratch only).
3. Passes A and B; pass C where triggered; commit the readings.
4. Write and commit the scoring script, implementing exactly the rules above.
5. Only then run the analyzer, at the commit the lead names as the R1
   candidate, on the three audited files (md5-checked), recording the blob of
   `engine/qa/knockouts.py` it ran. Score, and publish `RESULTS.md` with the
   disclosure that the human readings are model readings.

No JVMs are run at any step.
