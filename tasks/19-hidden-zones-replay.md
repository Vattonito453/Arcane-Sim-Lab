# 19 — Hand, graveyard and library in the replay

> **STATUS 2026-08-31: hands SHIPPED, the rest untouched.** The hand panel
> landed in `1bac7e7` and reads from the shim zone stream. Graveyard, exile
> and library count are not built, and the `engine/board.py` side is
> untouched.

Playtester feedback (2026-08-06): "Hard to confirm effective play if we can't
see what the AI is holding in hand or has in graveyard." The replay shows the
battlefield and the event log, but a viewer judging whether the AI piloted the
deck well needs the hidden zones too: what it was holding, what it has in the
graveyard to recur, how deep the library still is. There is no hidden-information
concern here — these are finished AI-vs-AI games, and seeing the AI's hand is
the point.

## What the data already gives us (measured 2026-08-06)

**Shim path: this is a read, not new work in the shim.** The `zones` stream
records EVERY zone change in both directions, not just battlefield traffic.
Measured on `shim_raw_study_blight-curse_agent_v3_g32_c900_rot0.jsonl`
(8 games, 3,303 zone records):

```
from: Library 1133, Hand 964, Battlefield 462, Stack 457, None 182,
      Graveyard 78, Command 14, Exile 13
to:   Hand 1089, Battlefield 977, Graveyard 607, Stack 458, Library 139,
      Exile 27, Command 6
```

Opening hands are present (turn-0 `Library -> Hand` records), so hand
membership can be folded from the very start of the game. `Hand`, `Graveyard`,
`Exile` and `Command` contents per player per turn are exactly derivable the
same way `reconstruct_from_zones` already derives the battlefield. The
per-game API payload (`/results/{file}/game/{n}`) already ships the `zones`
array to the browser — nothing new to serve.

**Library is the one zone where contents are NOT fully known.** We observe
cards leaving (draws, tutors, mills) and returning (shuffles, tucks), but
never the residents. Two honest options, in preference order:

1. **Count only** — starting size from the format/decklist, minus observed
   departures, plus observed returns. Verify mulligan bookkeeping against the
   `MULLIGAN` entries before trusting turn-0 counts.
2. Optionally "known to remain": decklist minus every card observed outside
   the library — but this needs the decklist joined in and must be labeled as
   a derivation, not shown as an ordered library. Do not build this in v1.

**Stdout path: mostly unavailable, and the spec must say so.** Stock-Forge
stdout never logs draws or battlefield entries, so hand/library contents are
not derivable. Graveyard membership is partially inferable from the existing
`zone_change` exits. On this path the zone panels render as "not recorded on
this run; re-run through the shim" — the same honesty pattern the board
already uses, not a silent empty list.

## What to build

1. **Board** (`engine/board.py`): extend the shim-path fold to track per-player
   membership for Hand, Graveyard, Exile and Command alongside the battlefield,
   plus a library count. Zone tracking must not touch battlefield inference or
   `exit_match_rate` on either path. Shim logs older than 0.3.0 lack
   `types`/`pt`/`token` on zone records — reuse the existing Scryfall-fallback
   typing, and put unknowns in the "Unidentified" group per the invariant.
2. **Replay UI** (`web/lib/replay.ts`, replay page): per-player zone panels —
   hand and graveyard as card lists, exile and command when non-empty, library
   as a count. They scrub with the same turn/event position as the tabletop.
   Strip seat prefixes with `stripAi()` for display, keep raw keys for lookups.
   All styling in `globals.css`; no new CSS files.
3. **Honesty note**: the existing basis note distinguishes the two paths.
   Shim path: zone contents are read from Forge's event stream. Stdout path:
   panels state the data was not recorded rather than rendering empty.

Out of scope here: player resources (energy, poison, experience) — that is
task 10. Cards' identity in hand is known only from the zone record's `card`
name; do not invent Scryfall-based "likely holdings" for stdout runs.

## Acceptance criteria

- [ ] Replaying a shim result shows each player's hand and graveyard at any
      event position, and they match a hand-audited game (pick one game, walk
      the zones records by hand, compare).
- [ ] Library count never goes negative and reconciles with mulligans on a
      game that mulled (find one via the `MULLIGAN` entries).
- [ ] A stdout-path replay (e.g. the committed fixture) shows the
      "not recorded" state, not empty panels.
- [ ] `python3 engine/board.py engine/tests/fixtures/sim_sample.json
      --no-fetch` — `exit_match_rate` unchanged; same check on a shim result
      (exit_match_rate stays 1.0).
- [ ] `python3 engine/tests/test_adapter.py` passes; `cd web && npm run verify`
      clean.
- [ ] Run the `ui-review` gate before calling the front end done.

## Verification

```bash
python3 engine/tests/test_adapter.py
python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch
python3 engine/board.py <a shim result>.json          # basis: zones, exit_match_rate 1.0
cd web && npm run verify
# manual: open a shim replay, scrub to mid-game, confirm hand/graveyard
# contents against the event log; open a stdout replay, confirm the
# "not recorded" state renders.
```
