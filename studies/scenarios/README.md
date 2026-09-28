# Seeded-board scenario harness (WS3)

Repair plan `tasks/25-repair-plan.md`, WS3. A scenario is a board where a
line is already assembled: every zone of every seat, life, poison, turn,
phase and whose turn it is. Forge loads it into a real Commander game after
mulligans and before anyone has priority, and the game plays on under
Forge's rules. The question a scenario answers is "does this mechanism
work?", in a minute of play instead of a 15-turn game that may never reach
the line.

- The spike and its verdict (the G-harness gate): `SPIKE.md`. Four-player
  states work; no fallback was needed.
- The loader: shim 0.17.1 `--scenario <file>` (public repo
  `simlab-forge-shim`, branch `shim-0.17.1-scenario`). It reads Forge's own
  `GameState` text and applies it through Forge's start-game hook, the path
  Forge's puzzle mode uses. The shim makes no decision and names no card.
- Here: the scenario format, `writer.py` (scenario JSON to Forge's state
  text), `run_scenarios.py` (arms x trials, report) and tests.

Stdlib Python only. Raw run output goes under `--out`, outside git; commit
summaries (`report.md`, `report.json`), never logs.

## Quick start

```bash
# one scenario, both arms, 20 trials each, 8 JVMs
py studies/scenarios/run_scenarios.py studies/scenarios/smoke/smoke_godo_helm.json \
    --jar <scratch>/harness/shim-0.17.1-967cb71.jar --out <scratch>/runs/smoke \
    --arms stock,plan --trials 20 --parallel 8 --seed 2026101400 \
    --data-dir <scratch>/g0a/cache_cedh        # card cache for building plans

py studies/scenarios/run_scenarios.py --report-only --out <scratch>/runs/smoke
py studies/scenarios/writer.py SCENARIO.json --seed 7          # print the state text
py studies/scenarios/tests/test_writer.py                      # ALL ASSERTIONS PASSED
py studies/scenarios/tests/test_report.py                      # ALL ASSERTIONS PASSED
```

`run_scenarios.py` flags: `--jar` (shim >= 0.17.1), `--out`, `--arms`
(comma list, default `stock,plan`), `--arms-file` (JSON adding or
overriding arms), `--trials` (default 20), `--parallel` (1 to 8, default
8), `--seed` (trial k uses seed + k; default 2026101400), `--timeout`
(per-game wall clock, default 900 s), `--horizon` (turns allowed after the
scenario turn when the scenario has no `horizon_turns`; default 8),
`--plans` (a prebuilt plans JSON keyed by deck name, used for every plan
seat), `--data-dir` (the `MTG_DATA_DIR` to build plans from), `--fetch`
(let the plan build fetch card data), `--xmx` (JVM heap, default 3g),
`--force` (re-run finished trials), `--report-only`.

## Scenario JSON (`simlab-scenario/1`)

```json
{
  "format": "simlab-scenario/1",
  "id": "smoke_godo_helm",
  "description": "What the scenario tests, in a sentence or two.",
  "seats": [
    {
      "deck": "studies/human_ceiling/decks/2iA_Jt0d6sM/dck/godo_archetype.dck",
      "pilots": {"plan": "stock:Default"},
      "life": 40, "poison": 0, "counters": {"ENERGY": 2}, "lands_played": 0,
      "battlefield": [
        {"card": "Godo, Bandit Warlord", "id": "godo"},
        {"card": "Helm of the Host", "attached_to": "godo"},
        {"card": "Mountain", "tapped": true},
        {"card": "Walking Ballista", "counters": {"P1P1": 2}, "sick": true, "damage": 1},
        {"token": "c_a_treasure_sac"},
        "Sol Ring"
      ],
      "hand": ["Lightning Bolt"],
      "graveyard": [], "exile": [], "command": [],
      "library": {"top": ["Ancient Tomb"], "rest": "shuffled", "bottom": []}
    }
  ],
  "active": 0, "turn": 5, "phase": "MAIN1",
  "success": {"type": "win", "seat": 0, "by_turn": 9},
  "line": {"seat": 0, "pieces": ["Godo, Bandit Warlord", "Helm of the Host"]},
  "horizon_turns": 8
}
```

**Seats.** 2 to 4. Seat `i` is the `i`-th `--decks` entry, Forge's
registered order: seat 0 is `Ai(1)-<deck name>`, seat 3 is `Ai(4)-...`, and
the state's keys are `p0` to `p3`. Turn order after the active seat follows
seat order (seat 1 active: then 2, 3, 0). Rotation is the caller's job:
write a second scenario with the seats reordered.

**`deck`** gives the seat its identity (the deck name the plans are keyed
by, its commanders) and the cards that fill its library. Absolute, relative
to the scenario file, or relative to the repo; environment variables
expand (`"$SIMLAB_PRIVATE/dck/kess.dck"`), so a scenario on a private deck
(Richard's) can be committed while the deck is not. A card placed beyond
the copies the deck holds, or one the deck does not hold at all, is written
anyway and reported as a warning.

**`pilots`** (optional) overrides the arm's pilot for this seat, by arm
name: `{"plan": "stock:Default"}` keeps this seat on stock AI in the plan
arm, which is how "one plan seat against three stock" is written. Pilot
strings are the shim's `--seat-pilots` entries (`stock:<profile>`,
`plan:<profile>`).

**A card** is a name (`"Sol Ring"`) or an object with exactly one of
`card` (the name Forge uses: a double-faced card by its front face, a split
card as `A // B`), `token` (a script name from Forge's `res/tokenscripts`,
written `T:<name>`) or `token_info` (Forge's inline token string, written
`t:<string>`), plus any of:

| Key | Forge option | Notes |
|---|---|---|
| `tapped` | `Tapped` | Read back exactly (measured). |
| `sick` | `SummonSick` | Without it a seeded permanent can attack and tap at once: Forge clears the flag on every card it creates. Haste still overrides it in play (the record's `sickNow`). |
| `counters` | `Counters:P1P1=2,LORE=1` | Forge's counter names (`P1P1`, `M1M1`, `LORE`, `LOYALTY`, `CHARGE`, ...). Read back exactly (measured with `P1P1` and `LORE`). |
| `damage` | `Damage:N` | Marked damage. |
| `id` | `Id:N` | A label for `attached_to`; the writer numbers labels 1, 2, ... in order of appearance. Unique across the scenario. |
| `attached_to` | `AttachedTo:N` | An equipment or aura on the labelled card, own or another seat's. Forge attaches only cards that are attachments. Read back exactly (measured: equipment on own creature). |
| `commander` | `IsCommander` | Added by the writer to every card named in the deck's `[Commander]` section, wherever it is placed; a commander the scenario does not place goes to the command zone. Forge then builds the commander effect. |
| `imprinting` | `Imprinting:N,...` | On the host (Isochron Scepter): the labelled card(s) it imprinted. Pair it with `exiled_with` on the exiled card; Forge's Scepter needs both (S6). |
| `exiled_with` | `ExiledWith:N` | On an exiled card: the labelled permanent that exiled it. |
| `transformed` | `Transformed` | A double-faced card on its back face (written under its front-face name). The board check compares it by count, since it reads back under the back face's name (measured: Invasion of Ikoria as Zilortha, C1). |
| `face_down`, `flipped`, `no_etb`, `monstrous`, `renowned`, `token_flag`, `set` | `FaceDown`, `Flipped`, `NoETBTrigs`, `Monstrous`, `Renowned`, `IsToken`, `Set:` | Passed through; not exercised. |

**Zones:** `battlefield`, `hand`, `graveyard`, `exile`, `command`,
`library`. Every zone of every seat is written, empty ones included:
Forge's loader clears every zone before it fills the ones it is given, so
an unwritten library is an empty library. `library` is a list (the whole
library, top card first) or `{"top": [...], "rest": "shuffled" | "none",
"bottom": [...]}`. `"rest": "shuffled"` (the default) is the deck minus
every card placed anywhere, shuffled by the writer with the trial's seed.
Forge never shuffles the seeded library itself, so each seat's next draw is
its library's first card (measured).

**Top level.** `active` (seat index), `turn` (the game turn number, all
seats' turns counted, as Forge counts it), `phase` (one of `UNTAP`,
`UPKEEP`, `DRAW`, `MAIN1`, `COMBAT_BEGIN`, `COMBAT_END`, `MAIN2`,
`END_OF_TURN`, `CLEANUP`; use `MAIN1`, see limits), `remove_sickness`
(clear summoning sickness on every card), `success`, `line`,
`horizon_turns`, `notes`, `tests`.

**`success`** (optional; without it the report still records the winner
and turns) is one of:

- `{"type": "win", "seat": i, "by_turn": T}`: seat `i` wins at or before
  game turn `T` (`by_turn` optional).
- `{"type": "zone", "seat": i, "from": Z1, "to": Z2, "cards": [names],
  "types_any": [types], "first": true, "by_turn": T}`: a card in `cards`,
  or with `types_any` any card Forge types as one of those (`Creature`,
  `Instant`, ...), moves from zone `Z1` to zone `Z2` for seat `i` by turn
  `T`; with `"first": true` the seat's first such move must qualify. This
  scores a tutor's pick (S8, S9) from the shim's zone records; `zone_first`
  in the report is the pick. Zone records written while the state loads
  carry turn 1, so the scenario turn must be above 1.
- `{"type": "alive", "seat": i, "by_turn": T}`: seat `i` has not lost when
  the game ends. Set `horizon_turns` so the game is called at `T`. This
  scores "do not kill yourself" (S5b). Forge's own outcome lines ("has
  won" / "has lost") decide. When Forge's setGameOver threw at the
  turn-cap kill, no such lines exist and the result's alive flags are not
  reliable, so the trial is unscored (`success: null`, `unscored`) and
  leaves the denominator.

**`line`** is `{"seat": i, "pieces": [names]}`: the
cards whose casts, activations and trigger resolutions the report counts
for that seat (token copies count, since Forge names them after the card).
**`horizon_turns`**: the game is called at turn `turn + horizon_turns`
(the shim's `--max-turns`); default 8, two table rounds at four seats.

## What a run reports

Per trial (`report.json` → `scenarios.<id>.arms.<arm>.trials`), from the
shim's JSONL:

- `applied`, `board_diffs`, `loaded`: whether the state applied, and every
  difference between what the writer asked for and the shim's `scenario`
  record of what Forge holds after the apply (life, poison, hand,
  graveyard, exile and command as multisets, library in order, each
  battlefield card's tapped, sick, counters, damage, attachment and
  commander flags, token count). `loaded` = applied with no difference.
  `line_loaded`: the line seat's line pieces on the battlefield read back
  as written, whatever else differs (a real board can differ off the line,
  because Forge runs enter-the-battlefield replacements such as Mox
  Diamond's during the load).
- `winner_seat`, `turns`, `draw`, `turnCapped`, `timedOut`, `error`,
  `killFailed`, `success`, `kill_on_scenario_turn` (the success seat, or
  any winner without `success`, won during the scenario turn),
  `turns_to_kill` (result turn minus scenario turn). For `zone` scenarios,
  `zone_moves` (the seat's qualifying-zone moves in order) and `zone_first`.
- `piece_counts` (per piece: cast / activated / triggered, the line seat
  only, from Forge's `STACK_ADD` log entries), `piece_activity_total`,
  `iterations_max_turn` and `iterations_scenario_turn` (activations plus
  triggers of line pieces in the best turn and in the scenario turn),
  `combats_max_turn` and `extra_combats_scenario_turn` (beginning-of-combat
  steps of the line seat). `piece_targets`: what each line piece's casts,
  activations and triggers targeted (split on each instance id, since card
  names contain commas); S1 and S2 test exactly this.
- `agent_events` (plan-seat telemetry by event) and
  `agent_events_on_pieces` (those naming a piece).
- `ms` (game wall time), `ms_per_turn`, `ms_per_decision` (always null:
  0.17.1 exposes no per-decision timing), `exceptions` and three samples
  from the JVM's stderr, `rc`, `wall_s`, `outcomes` (Forge's outcome
  line per seat) and `game_over_threw`.

Per arm (`summary`): trials, finished, loaded, line_loaded, scored and
unscored, success (of scored) with a Wilson 95% interval, kills on the scenario turn, turns to kill (median, mean), draws,
turn caps, timeouts, errors, exceptions, mean line activity, iterations and
extra combats, mean game ms, and wall time. `report.md` is the same as a
table per scenario, with any board differences listed; its header carries
the invocation's wall clock (also in `run.json`: `wall_s`, `trials_run`,
`trials_cached`).

**Pairing.** Trial `k` of every arm uses `--seed-forge seed+k` and the
same state file (same shuffled libraries), so arms start from identical
boards and identical Forge seeds. Forge's play under a seed is not fully
deterministic (`SPIKE.md`: stock-only games repeated exactly over 12 turns
in 7 of 7 runs; games with plan seats split into two or three variants from
the same seed), so treat trials as paired openings, not replays.

## Limits of the state format

What `GameState` can seed, and what it cannot (Forge 2.0.13 source,
`forge-game/.../GameState.java`, and the spike):

- **Carried:** every zone, life, poison and other player counters, lands
  played this turn, tapped, summoning sickness, counters, marked damage,
  equipment and aura attachments (by label), tokens, face-down,
  transformed and flipped states, commanders, the turn number, the phase
  and the active player. Four seats (`p0`..`p3`; the key reads one digit,
  so never more than ten, and the harness allows four).
- **Not carried, so every scenario starts without it:** commander tax
  (casts from the command zone start at zero) and commander damage; the
  storm count and anything else counted "this turn" (spells cast, cards
  drawn, life gained), which matters for S7; "until end of turn" effects;
  the monarch, the initiative, day and night; the stack; mana in pools
  (the writer never emits `manapool`: inside the shim, `GameState` would
  apply it on Forge's thread pool, not the game thread).
- **Combat cannot be seeded** in a multiplayer game (`GameState` declares
  attackers only against a single opponent), so the writer refuses combat
  phases. Start at `MAIN1` and let the pilots declare.
- **Starting mid-turn skips that turn's earlier steps.** The state sets the
  phase directly: starting at `MAIN1` means the active seat does not untap,
  upkeep or draw this turn, and "at the beginning of your upkeep" triggers
  do not fire until the next turn. Seed the board as it stands in the main
  phase.
- **Enters-the-battlefield replacement effects run during the load;
  triggers do not.** Forge moves each battlefield card in: a shock land
  asks its controller whether to pay 2 life (the shim then restores every
  seat's life to the file's value and lists the change as `lifeRestored`),
  "as this enters, choose" cards ask the seat's AI to choose, a clone asks
  what to copy, "enters tapped" is overridden by the `tapped` flag.
  Triggered abilities are suppressed while the state loads, so a seeded
  creature's "when this enters" search never happened (a seeded Godo has
  not fetched its equipment). Measured on C1's real boards: Mox Diamond
  goes to the graveyard or takes a land from hand (8 of 20 boards); a
  clone can re-pick and die (3); a battle can leave (1). `NoETBTrigs` does
  not help: it still moves the card through `moveToPlay`, which runs
  replacements. The board check reports these, and `line_loaded` says
  whether the line survived them.
- **Life 0 crashes the load in a multiplayer state.** `GameState` sets a
  life of 0 before its state-based check, which removes that seat, then
  indexes past the end of the shortened player list
  (`IndexOutOfBoundsException`, 2 C1 boards). Negative life is set after
  the check and works: the seat loses at the game's first check. The
  writer refuses 0; `board_from_game.py` writes an already-lost seat at -1.
- **The discarded opening.** Forge deals opening hands and resolves
  mulligans before the hook, then the state replaces every zone. So the
  log's first `Turn 1 (...)` line, the `MULLIGAN` entries, the `rubric`
  mulligan records and plan seats' `mull_keep` / `mull_take` events
  describe hands that were thrown away; `zone` records at turn 0 are those
  hands. The shim's `scenario` record is the authority for the seeded
  board. Forge logs the state's phase as `devAi(k)-...`, and its next
  `TURN` entry is the scenario turn plus one; `run_scenarios.py` counts log
  entries from the first `TURN` entry as the scenario turn.
- **Hidden information.** Forge's AI decides with whatever its own code
  reads; the harness does not change what a seat can see.

**Seen on scenario boards, not caused by the harness.** A plan seat logs
`attack_reask` once in a turn with extra combats (smoke, plan arm: 4 of 4
trials; also present in G0a's games on the same pod): its attack guard
counts declarations per turn, so from the second combat on it hands the
declaration to Forge unchanged, and the plan pilot's attack logic does not
run in extra combats. Combat work is frozen until G4 (owner decision 1);
read Godo, Helm and other extra-combat results on the plan arm with that in
mind.

## The suite (WS3 task 4)

`suite/` holds the initial suite: `s1_*` to `s9_*` (S5b included) and
`c1/`, 20 real stock-game boards for the positive control. Each file's
`description` says what it tests and its success condition; `notes` name
every deviation (a card placed that the deck does not list, a piece left
off to isolate the choice under test). Baselines, verdicts and anomalies:
`BASELINE.md`.

- Decks are study decks from allowed pods only (never the holdout pods).
  S8 is Richard's own pod, read through `$SIMLAB_PRIVATE` at run time.
- C1 boards come from `board_from_game.py`, which rebuilds every seat's
  zones from a real shim game at the end of a turn's precombat main phase;
  `suite/c1/make_c1.py` draws the 20 boards (seeded) and keeps each source
  game's outcome in `suite/c1/sources.json`. This is also how the suite
  grows from confirmed misplays (WS3 task 5).
- Plans for the plan arm: `--data-dir <scratch>/g0a/cache_cedh` for the
  cEDH scenarios and C1, `--data-dir <scratch>/g0a/cache_richard` for S8.

## Files

- `writer.py`: scenario JSON to state text; `parse_state` reads state text
  (and the `[state]` block of a Forge puzzle) back.
- `run_scenarios.py`: the runner and report.
- `spike/spike_4p.json`: the G-harness spike board (every field above).
- `smoke/smoke_godo_helm.json` with `smoke/report.md` and
  `smoke/report.json`: the end-to-end smoke run (4 trials per arm, both
  arms loaded 4/4 and won on the scenario turn 4/4). It is a loader check,
  not a pilot comparison: this board converts for any pilot.
- `tests/test_writer.py`, `tests/test_report.py`.
- `SPIKE.md`: the gate.
- `board_from_game.py`: a scenario board from a real shim game.
- `suite/`, `BASELINE.md`: the initial suite and its baselines.
