# Behavior capture — scaling the human corpus to 30–50 games

Purpose: turn the qualitative human reference bands ("splits constantly",
"routine blocks") into measured numbers with confidence intervals, and
capture the behaviors Stage 5 added (tutor timing, combo holds, greed)
that the current 7-game corpus barely contains. The agent-vs-stock
question is already settled; this corpus calibrates **agent-vs-human**.

Two intake paths, in order of value:

## Path A — self-recorded games (highest value)

Self-recorded games beat YouTube extraction on every axis that matters:

- **Hidden information.** You know your own hand, your tutor targets, and
  what you were holding back. No video ever yields this; it is the only
  way to ground-truth the greed dial (did you jam into open mana or wait?)
  and tutor intent (what were you actually searching for?).
- **Decklists as .dck.** Export before playing. A game whose decks exist
  as .dck files can be replayed by the sim agent — the same 99, human
  pilot vs agent pilot, decision-by-decision. This is the strongest test
  the corpus can support (tasks/07, training track).
- **No ASR garbling.** Card names and speaker attribution are free.

### Recording protocol (per game, ~5 min of overhead)

Before the game:
1. Save each deck as `.dck` (or Moxfield/Archidekt links — convertible via
   `engine/convert_decklist.py`). Note seat order.
2. One line per player: name, commander, archetype tag (same vocabulary as
   `engine/deck_plan.py` TAG_MARKERS).

During the game (say it out loud on the recording — narration is the log):
3. **Mulligans**: each keep/take and a word on why ("no lands", "kept — has
   the engine piece").
4. **Tutors**: name the card you search for the moment you pick it, and
   the runner-up ("Demonic for the Ascendancy; almost took removal").
5. **Holds**: when you keep a castable spell back, say so ("holding Rite,
   Kess has blue up"). This is greed-dial gold and is invisible otherwise.
6. Everything else (attacks, blocks, politics talk) is already visible on
   camera — just keep the board and dice readable.

After the game:
7. Fill one `behavior_tally.json` per game (schema below) — counting, not
   transcription; ~10 minutes per game. Full rules-KB extraction (the
   game_00N/ treatment) stays optional and can lag behind.

## Path B — YouTube videos (volume)

Still valuable, selection criteria in priority order:

1. **Published decklists** (Mana Dorks-style Moxfield/Archidekt links) —
   replayable in Forge, like game_005.
2. **Combo or tutor-heavy decks at the table** — the corpus's biggest gap;
   the current 7 games skew midrange/aggro and contain near-zero tutor or
   combo-hold decisions.
3. Clean audio + readable board (ASR quality gates everything).
4. Complete single-video games (multi-episode games triple the work).

Same tally schema; hidden-info fields stay null for video games.

## behavior_tally.json schema (one per game)

Counting only — every field is observable except the `hidden` block,
which only self-recorded games can fill. Store as
`training/tallies/<game_id>.json`.

```json
{
  "game_id": "vja_2026-08-08_g1",
  "source": "self-recorded | youtube:<video_id>",
  "decklists": ["kombo.dck", "..."],          // null if unpublished
  "players": 4,
  "winner_archetype": "combo",
  "mulligans": {"decisions": 4, "taken": 1},
  "attacks": {"attack_turns": 22, "split_turns": 9},
  "blocks": {"opportunities": 31, "blocks_made": 12},
  "commander_deploys": [4, 5, 3, 7],          // player-turn of first cast
  "tutors": {
    "cast": 3,
    "held_castable": 1,                        // drawn+castable but never cast
    "targets": ["combo piece", "land", "removal"]
  },
  "combo": {
    "lines_present": true,
    "assembled": 1,
    "pieces_held_turns": 3,                    // turns a piece sat castable but held
    "jammed_into_open_mana": 0,
    "waited_for_protection": 1
  },
  "hidden": {                                  // self-recorded only, else null
    "holds_narrated": 4,
    "tutor_intents": ["Simic Ascendancy over removal"]
  },
  "notes": "free text; oddities, misplays, rules moments"
}
```

`python3 training/behavior_bands.py training/tallies/*.json` aggregates
all tallies into the reference bands (rates + 95% Wilson intervals) that
`engine/humanness_scorecard.py` metrics compare against — and prints the
current corpus size next to each band so nobody mistakes a 5-game band
for a 50-game one.

## Targets

- 30–50 games total (tasks/07 target), of which
- ≥8 games featuring a combo deck with real tutors (greed/hold evidence),
- ≥5 self-recorded games with .dck exports (replay diffing candidates),
- rest: volume for the four scorecard bands.

At ~20 attack turns and ~4 mulligan decisions per game, 40 games gives
±6–7% on mulligan rate and ±4–5% on split rate — tight enough to say
"the agent is inside the human band" as a measurement, not a direction.
