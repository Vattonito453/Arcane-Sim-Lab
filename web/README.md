# Sim Lab — front end

Next.js 15 app for the MTG rules/sim engine in `../engine`. Implements the v3
design system in `../mockups/design_principles.md`; every screen is a direct
build of the wireframes in `../mockups/`.

## Run it

Two processes. Terminal 1 — the engine API:

```bash
cd ..
python3 engine/mtg_engine.py serve 8484
```

Terminal 2 — this app:

```bash
npm install     # first time only
npm run dev     # http://localhost:3000
```

The API base URL is runtime-configurable (per `frontend_handoff/API_SPEC.md`):
it reads `localStorage["simlab.apiBase"]`, then `NEXT_PUBLIC_API_BASE`, then
defaults to `http://127.0.0.1:8484`. Change it in the UI from the "Engine" link
on the home page — no rebuild needed.

`npm run build` requires network access on first run (Google Fonts are fetched
and self-hosted at build time by `next/font`).

## Routes

| Route | Screen |
|---|---|
| `/` | Decks, past runs, start a gauntlet |
| `/import` | Paste/validate a decklist → `POST /decks` |
| `/runs/[id]` | Live run progress, polls `/sim-status` every 4 s |
| `/results/[file]` | Run report — win rates, games table |
| `/results/[file]/replay/[game]` | Replay theater, `?t=` deep-links an event |

## Layout

```
app/
  globals.css                     the whole design system — tokens + component
                                  classes. Pages add no CSS and no inline styles
                                  beyond computed percentages.
  page.tsx  import/  runs/[id]/  results/[file]/  results/[file]/replay/[game]/
components/
  Chrome.tsx                      topbar + tab row + footer
  ApiBaseSetting.tsx              engine URL control
lib/
  api.ts                          engine client, configurable base URL
  types.ts                        response shapes, mirroring the engine exactly
  format.ts                       stripAi, pct, timeAgo, scryfallArt, …
  replay.ts                       event-folding engine (pure, testable)
```

## `lib/replay.ts`

The replay is a local fold over the engine's event log — one JSON fetch per run,
no server round-trips while scrubbing. Parsers were written against real raw
strings from `engine/sim_results/` (samples are documented at the top of the
file); `buildTimeline(game)` turns events into steps, `foldTo(timeline, i)`
produces the board state at any point, `summarizeGame(game)` yields the "decided
by" phrase used in the games table.

Verified against a real 16-game rotated gauntlet: step count equals event count,
folded final life totals match the last explicit total in the raws for every
player in every game, and winner/eliminated states agree with the outcome
events — 22,316 events, 80/80 checks.

The board state is best-effort by design: Forge logs don't carry card types, so
a resolved permanent is inferred from its resolve line. The **event log is the
authoritative display**; the board is an aid.

## Card data and board reconstruction

`engine/cards.py` caches Scryfall facts (type line, P/T, mana cost, oracle text,
art) per card name. This is not decoration: **Forge's text log never records
cards entering the battlefield**, only leaving it (measured on a real 16-game
log: 134 `Battlefield→Graveyard`, 15 `→Exile`, **zero** entries). Board state
therefore has to be inferred from resolve events, and that requires knowing
whether a resolved card is a permanent or a one-shot spell. Without a type line
the replay puts `Go for the Throat` on the battlefield; with one, it doesn't.

Run `python3 engine/cards.py warm engine/sim_results/<file>.json` once to
populate the cache — about 260 distinct names per run, four batched requests.
A warm cache makes zero network calls.

`engine/board.py` does the reconstruction and reports its own error rate.
Exits are explicit in the log, so they act as an oracle: any card Forge says left
the battlefield must have been on our board at that moment. Measured on the
16-game rotated gauntlet:

| | cold cache | with type data |
|---|---|---|
| Exit match rate | 86.5% | 86.5% |
| Entries with unknown type | 46.6% | 27.1% |

**The known ceiling.** 71 exits (13.5%) don't match, and 68 of those are tokens.
For 71% of them the exit is the object's *first and only* mention anywhere in the
log — a Zombie token created and sacrificed to Wilhelt's own ability leaves no
trace but its death. That information does not exist in the log; it is not a
parsing bug, and neither Scryfall nor better regexes can recover it. Those cards
are shown dashed with a tooltip explaining why, and cards of unknown type are
grouped under "Unidentified" rather than silently mixed in.

The only route to exact board state is Forge's programmatic entry point
(`forge.view.SimulateMatch.simulateOffthreadGame`, noted in
`training/forge_integration.md`), which can dump real per-turn state. That is a
separate Java shim calling Forge's API — worth doing, and worth a GPL review
first, since the current posture depends on Forge staying an unmodified process.

## Backend routes this app added

`engine/mtg_engine.py` gained three routes (see `HANDOFF_README.md`, "Extending
the backend"):

- `GET /results` — index of adapted sim result files, newest first
- `GET /results/{file}` — one full result (games → turns → events);
  `?snapshots=1` appends an end-of-turn `board_snapshot` event per turn
- `GET /cards?names=a|b|c` — cached Scryfall facts; `?fetch=0` for cache-only
- `GET /board/{file}` — board-reconstruction accuracy report for that run
- `POST /decks` — `{name, text, commander?, save?}` → validated `.dck` via
  `convert_decklist.convert()`; returns `{ok:false, error}` rather than a 500 on
  a bad paste
- plus `OPTIONS` for CORS preflight

## Not built yet

Coaching synthesis (the LLM call), telemetry rendering, the rules assistant, and
deck-scoped tabs (Telemetry / Changes / Play guide) are stubs or absent — see
`../frontend_architecture.md` §6 and §8 for the intended shape.
