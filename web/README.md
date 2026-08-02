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
defaults to `http://127.0.0.1:8484`. Change it from the **Engine** row at the
bottom of the nav menu — no rebuild needed. It lives there and nowhere else; it
used to be printed into two different section headers, which put an
infrastructure address in the middle of the deck picker.

`npm run build` requires network access on first run (Google Fonts are fetched
and self-hosted at build time by `next/font`).

## Routes

Five top-level destinations, all nouns. `Decks`, `Simulate` and `Playtest` all
render the same `DeckGallery`; they differ only in what a tile does.

| Route | Screen |
|---|---|
| `/` | Splash hub — tallies, action hub, top decks, recent runs |
| `/decks` | **Nav.** Gallery of every deck; Import is the primary here |
| `/decks/[file]` | One deck: every card with cost, type line, oracle text |
| `/new` | **Nav: Simulate.** Seat 2–4 decks, pick games, run |
| `/playtest` | **Nav.** Deck chooser for the sandbox |
| `/playtest/[deck]` | Solo goldfish sandbox (no opponent, no rules, no outcome) |
| `/results` | **Nav.** Run history |
| `/results/[file]` | Run report — win rates, win conditions, games table |
| `/results/[file]/telemetry` | Did the deck's plan actually fire? |
| `/results/[file]/coaching` | Cached coach report, or the one generate action |
| `/results/[file]/replay/[game]` | Replay theater, `?t=` deep-links an event |
| `/rules` | **Nav.** Grounded rules Q&A over the CR |
| `/import` | Paste/validate a decklist → `POST /decks`; reached from `/decks` |
| `/runs/[id]` | Live run progress, polls `/sim-status` every 4 s |

There is no breadcrumb in the top bar. The `<h1>` is the page title; where a
page has a real parent (a replay belongs to a run, a deck to the collection) it
renders a `.back` link. A breadcrumb here only restated the H1, and on a narrow
screen its width pushed the nav off the edge.

**Addresses are not content.** A result filename, `.dck` name, port or job id
never appears in a heading, a sub-line or the footer — it goes in the
`<PageDetails>` disclosure at the foot of the page, closed by default. The
footer carries the two legal lines and nothing else.

**No em dash in copy.** Anything a user reads uses a period, colon, semicolon or
parentheses instead, and an empty value in a table or figure is an en dash
(`–`). This covers JSX text, string literals, `aria-label` / `title` /
`placeholder`, page metadata, and engine strings that surface in the UI.
Scryfall card text is exempt: it is WotC's printed wording shown verbatim. Code
comments are not copy. Rule and substitution table:
`Design System/DESIGN_SYSTEM.md` §1. Check with:

```bash
grep -rn "—" app components lib --include='*.tsx' --include='*.ts' | grep -vE ':\s*(//|\*|/\*|\{/\*)'
```

## Layout

```
app/
  globals.css                     the whole design system — tokens + component
                                  classes. Pages add no CSS and no inline styles
                                  beyond computed percentages. Responsive lives
                                  in three blocks at the bottom: max-width 980,
                                  max-width 720, and pointer:coarse.
  page.tsx  decks/  decks/[file]/  new/  playtest/  playtest/[deck]/
  import/  rules/  runs/[id]/  results/  results/[file]/{,telemetry,coaching}
  results/[file]/replay/[game]/
components/
  Chrome.tsx                      topbar + nav (+ narrow-screen sheet), tab row,
                                  footer, PageDetails disclosure
  DeckGallery.tsx                 the gallery, shared by /decks /playtest /new
  ApiBaseSetting.tsx              engine URL control (used only by Chrome)
  Tabletop.tsx  Mascot.tsx  ManaPips.tsx
lib/
  api.ts                          engine client, configurable base URL
  types.ts                        response shapes, mirroring the engine exactly
  format.ts                       stripAi, pct, timeAgo, runDate, scryfallArt, …
  cards.ts                        Scryfall card-fact client + memo
  replay.ts                       event-folding engine (pure, testable)
```

## Responsive contract

- **720px** is the breakpoint between the wide layout and the narrow one.
- Data tables that carry a list (`/results`, the run report's Games table) get
  `class="games stackable"` and tag their cells `c-title` / `c-meta` / `c-act` /
  `c-drop`. Below 720px the same markup renders as stacked rows. Wide *analytic*
  tables (Win conditions) keep their grid and gain a visible scroll cue instead.
- `.only-narrow`, `.only-narrow-inline`, `.only-wide` and `.only-fine-pointer`
  gate copy that is only true at some widths or on some inputs — a keyboard hint
  does not belong on a touch device.
- Touch targets come up to `--control-h` (44px) under `@media (pointer: coarse)`,
  and hover-only controls (the playtest counter buttons) become always-visible
  there. Nothing in the product may be reachable by hover alone.

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
