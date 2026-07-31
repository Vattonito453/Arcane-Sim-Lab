# 09 — Multi-format playtesting (Pauper, Standard, Modern, …)

Commander is the launch format, but the pipeline is nearly format-agnostic
already: `run_sim.py --format` passes Forge's `-f` flag, and Forge's sim mode
supports constructed formats natively (60-card, 2-player, best-of-N via `-m`).
The work is legality validation, 2-player calibration, and UI.

## Scope order

1. **Pauper** first (Vincent's ask; also the cheapest legality rule: every
   card printed at common — Scryfall `legalities.pauper`).
2. **Standard** second (rotating legality — must come from live Scryfall
   data, never a baked list).
3. Modern/Pioneer/Legacy after — same plumbing, bigger card pools.

## Engine work

- `engine/cards.py`: extend the cached card facts with Scryfall's
  `legalities` map (one-time cache invalidation bump; keep batched
  `/cards/collection` etiquette exactly as-is).
- `engine/convert_decklist.py`: `--format` flag → validate 60-card minimum /
  4-copy rule / format legality; reject with per-card reasons (UI shows
  them). Commander path unchanged.
- `engine/run_sim.py`: 2-player pods for constructed formats; seat rotation
  becomes A/B seat swap; `forge_profile_deck_dir()` already maps
  non-Commander to `decks/constructed` — verify staging works.
- Deck storage: constructed decks join the same `MTG_DATA_DIR/decks` flow
  (`_find_deck()` / `_list_decks()` — never a bare path).

## Calibration (do not skip)

`SIM_CALIBRATION.md` numbers are Commander-only. Before showing any
constructed win rate:
- Re-measure seat bias 2-player (on-the-play advantage is real in 60-card
  formats; rotation must cancel it).
- Build per-format archetype baselines (aggro/control/combo gauntlet decks
  per format) — a raw % is meaningless without them (existing invariant).
- Verify the log adapter on 2-player constructed output: player count
  assumptions, mulligan lines, `sideboard` noise from best-of-N matches
  (prefer `-n` single games first; best-of-3 with sideboarding is a
  follow-up — Forge AI sideboarding is off by default in the Default
  profile).

## UI

- Format picker at import (`/new`), defaulting to Commander; format badge on
  deck list and results.
- Baseline table per format next to win rates (existing honesty rule).
- Prose openers state the format ("In 40 Pauper games against the aggro and
  control baselines…").

## Acceptance criteria

- [ ] Pauper decklist imports with per-card legality errors when invalid.
- [ ] A Pauper 2-deck sim runs end-to-end: import → queue → sim → results →
      replay, with seat-swap rotation.
- [ ] Adapter unit tests extended with a 2-player constructed fixture (same
      recomputed-summary convention as `sim_sample.json`).
- [ ] Per-format baseline decks committed under `engine/decks/` and their
      baseline table rendered beside results.
- [ ] `SIM_CALIBRATION.md` gains a constructed section with measured 2-player
      seat bias.
- [ ] Standard legality is resolved from the live Scryfall cache at import
      time, never a hardcoded set list.

## Verification

```bash
python3 engine/convert_decklist.py sample_pauper.txt --format pauper
python3 engine/run_sim.py --decks pauper_a.dck pauper_b.dck --format Pauper \
  --games 4 --rotate --out /tmp/sim_test
python3 engine/tests/test_adapter.py
python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch
cd web && npm run verify
```
