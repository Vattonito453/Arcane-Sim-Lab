# Testing the prototype

Everything in this repo already ran end to end on this machine. This is how to
bring it up, what to click, and how to tell whether it is actually working rather
than merely rendering.

To share it with people who aren't on this machine, see `deploy/HOSTING.md`.

## Start it

```bash
open "Sim Lab.command"
```

Or, if you'd rather watch it:

```bash
cd "/Users/vincentattonito/Desktop/Personal/MtG Rules Engine"
MTG_BIND=127.0.0.1 python3 engine/mtg_engine.py serve 8484 &
cd web && npm run dev
```

The launcher waits for `/health` to answer before opening the browser, warns if
Java or Forge is missing, and binds the engine to loopback.

**Requirements actually present here:** Python 3.9.6 (the engine is
`from __future__ import annotations` throughout, so it runs on 3.9 despite the
3.10+ note in the README), Java 17, Node 24, Forge 2.0.13 in `~/forge`, a warm
Scryfall cache, and 30+ real simulation results in `engine/sim_results/`.

## The automated check

```bash
python3 engine/tests/smoke_test.py --sim
```

29 checks, ~40 s. Without `--sim` it is 23 checks and ~2 s. It exercises the rules
KB, deck listing, the results index, run summaries, single-game payloads, `/cards`,
three path-traversal probes, and the three ways `POST /simulate` should refuse a
bad request — then queues a real 2-game Forge run and follows it through to a
readable result file.

Point it anywhere, including at a deployment:

```bash
python3 engine/tests/smoke_test.py --base http://localhost:3000/engine
python3 engine/tests/smoke_test.py --base https://your-host/engine --key "$KEY"
```

The rest of the verification loops are in `CLAUDE.md`; all of them pass right now:

```bash
python3 engine/tests/test_adapter.py
python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch
cd web && npx tsc --noEmit && npx next build
```

`next build` writes into `web/.next`, which pulls the rug out from under a running
`next dev`. Stop the dev server first, or expect `Cannot find module './941.js'`
until you restart it.

## The walkthrough

1. **Decks** (`/`). Pick 2–4 decks. The estimate next to the button is
   seat-aware: two decks costs ~2.5 s/game, three ~11 s, four ~52 s, plus ~7.5 s
   of JVM and card-database startup. Start with **1 game** to see the loop.
2. **Run progress.** Polls `/sim-status`, and once Forge has produced a game it
   **plays that game back on the table** over ~20 s while the simulation runs
   ahead, moving on to the next game as each finishes. It is playback from the
   buffered log, not a live feed, and says so: Forge writes its log in bursts, so
   following the newest event showed a still table that filled in exactly as the
   game ended. Playback is paced against the wall clock, so a backgrounded tab
   (which browsers throttle to ~1 timer callback a second) plays at the same rate
   rather than stretching to minutes. The page will not redirect to the results
   while you are still mid-playback; there is a "Skip to the results" link. Forge spends ~25 s loading its card
   database first, which the page says rather than showing an empty box. Behind a
   backlog the state reads "Queued — 2 runs ahead" instead of pretending to run.
3. **Results.** Every deck in the pod appears in *Win rates*, winless ones
   included, and the baseline marker reads 25% for four decks / 33.3% for three.
   If a 3-deck run ever shows "1 deck" and a 100% baseline again, the summary lost
   its winless seats — see `summarize()` in `engine/forge_log_adapter.py`.
4. **Replay.** Top-down table: seats around a centre line, each seat's creatures
   pinned to the middle edge, real Scryfall card faces, identical copies collapsed
   into one tile with a count (`Zombie Token 44`). Attackers get a red ring and an
   "attacking X →" line on the centre edge. Space plays, arrows step, shift+arrows
   jump a turn, `?t=<n>` deep-links an event.
5. **Results** (`/results`). Every finished run, filterable by deck. Runs are
   named by matchup — "Wyleth vs Drana vs Kilo vs Wilhelt" — not by the result
   filename, which is only the address and sits in the row tooltip.
6. **Import.** Paste a Moxfield/Arena export. The response reports the main-deck
   count, duplicates, and `cards_cached` — how many card faces it pulled from
   Scryfall in one batch so replays don't fetch mid-scrub. ~100 names is two
   batched calls, about 2 s.

## What to distrust while testing

- **The table is inference; the event log is the record.** Forge logs cards
  *leaving* the battlefield and never *entering*, so membership is reconstructed.
  Measured on the 2-game fixture: **83.3% of exits** match a card the
  reconstruction had on the board (86.5% on a full 16-game run). Cards whose type
  Scryfall doesn't know are grouped as unidentified rather than guessed onto the
  table or dropped. If the table and the log disagree, the log is right.
- **Win rates from 2-game runs mean nothing.** They exist so the loop is fast to
  test. Real numbers need seat rotation and 50+ games — `engine/SIM_CALIBRATION.md`.
- **Forge's AI under-pilots combo and politics decks**, so those sim below their
  real strength. Treat a low win rate for them as a floor, not a verdict.
- **Tokens have no card face.** Scryfall has no image for "Zombie Token", so those
  tiles are dashed and name-only. That is expected, not a broken image.

## Fixed while testing this

Each was invisible until a *fresh* run went through the UI — the 31 committed
results are all seat-rotated files whose post-processing masked the first two.

1. **A 3-deck run rendered as a 1-deck pod with a 100% baseline.**
   `summarize()` only recorded winners, so winless decks vanished from
   `summary.wins`, and the results page sized the pod from those keys. Winless
   seats are now seeded at 0 in both `forge_log_adapter.py` and `run_sim.py`; the
   page derives the roster from the games and folds `Ai(n)-` seat keys and bare
   deck names into one namespace. `test_adapter.py` updated to match.
2. **Raw `Ai(3)-Kambal Taxes B3` leaked into the results title, lede and figures**
   while the table below showed the clean name, and because `topNames` held raw
   keys and `winnerName` held stripped ones, "Watch a winning game" could point at
   a game the leading deck lost.
3. **Batched attackers parsed as one bogus creature.** Forge writes
   `assigned A (100), B (72) and C (326) to attack X` on one line. `replay.ts`
   matched the middle group as a single reference and produced a "creature" named
   `Wilhelt, the Rotcleaver (200), Zombie Token`. Splitting on commas isn't
   possible — card names contain them — so each name now runs up to its own
   instance id. The same comma bug was in `board.py`'s `_REF`, where fixing it left
   `exit_match_rate` unchanged at 83.3% and dropped assumed entries from
   **17.9% → 12.0%**, because correctly parsed names now hit the card cache.
4. **Keyed writes were impossible from a browser.** The CORS preflight advertised
   only `Content-Type`, so any `POST /simulate` carrying a Bearer key was blocked
   before it was sent. `Authorization` and `X-Api-Key` are now allowed, and
   `do_OPTIONS` honours `MTG_ALLOW_ORIGIN` instead of hardcoding `*`.

Still open, unchanged, and documented in `tasks/`: `_list_results()` parses all 33
result files to build the index; `runSummary`/`runGame` use `force-cache`, which
becomes a cross-user leak once responses are per-user; `Chrome.tsx` hardcodes
`vincent` and a `Pro` badge.
