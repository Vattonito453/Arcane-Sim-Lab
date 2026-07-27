# MTG Engine — Front-End API Specification

A working backend ships with this project (`engine/mtg_engine.py`): a Python API
wrapping a Magic: The Gathering Comprehensive Rules knowledge base and a Forge-based
game simulator behind a job queue. Build the front end against these real endpoints —
do not mock game logic or rules data. If the app needs a new endpoint, extend the
backend (see HANDOFF_README.md, "Extending the backend") rather than faking it
client-side. All endpoints return JSON and send `Access-Control-Allow-Origin: *`.

**Base URL must be a runtime-configurable setting** (config file / env / settings UI),
default `http://127.0.0.1:8484`. Real sample responses for every endpoint are in
`samples/`.

## Endpoints

### Rules knowledge (instant, <50ms)
| Endpoint | Purpose | Sample |
|---|---|---|
| `GET /rule/{number}` | Exact Comprehensive Rules lookup, e.g. `/rule/903.10a`. Parent numbers return subrules too. | `samples/rule_lookup.json` |
| `GET /search?q={text}&k={n}` | Scored free-text rules search | `samples/search.json` |
| `GET /keyword/{name}` | Keyword ability/action, e.g. `/keyword/station` | `samples/keyword.json` |
| `GET /glossary/{term}` | Glossary definition | (same shape as keyword) |
| `GET /turn-structure` | All phases/steps in order, each with its rules — good for a visual turn tracker | large; fetch live |
| `GET /health` | KB stats, use as connectivity check | `samples/health.json` |

### Decks
| Endpoint | Purpose | Sample |
|---|---|---|
| `GET /decks` | Available decks: `[{file, name}]` | `samples/decks.json` |

(No upload endpoint yet. To add one: wire `POST /decks` in `engine/mtg_engine.py`
to `engine/convert_decklist.py`'s importable `convert()` function, which turns a
Moxfield/Arena text export into a validated `.dck` file.)

### Simulation (long-running, queued)
| Endpoint | Purpose | Sample |
|---|---|---|
| `POST /simulate` body `{"decks":["a.dck","b.dck",...], "games":20}` | 2–4 decks. Returns `{ok, job_id, state:"queued"}` immediately | — |
| `GET /sim-status?id={job_id}` | Poll every ~4s. `state`: `running` → `done` or `error`. When done: `result` = `{games, draws, wins:{player:n}, win_rates:{player:0..1}}` | `samples/sim_status_done.json` |

Player keys look like `"Ai(2)-Inspirit Omega"` — strip the `Ai(n)-` prefix for display.
A 20-game sim takes 5–30 minutes: design for it (progress state, notify on completion,
history of past runs). 409/error states must be surfaced clearly.

Full per-game event logs exist as JSON files (see `samples/sim_result_game_excerpt.json`
for the schema: games → turns → events with `action`/`raw`). To serve them, add a
`GET /results/{file}` route in `engine/mtg_engine.py` reading from the sim results
directory — then build the "game replay/detail" view against that schema.

## Rules RAG — the AI assistant feature

The app must include an AI rules assistant grounded in the official Comprehensive
Rules (RAG). The retrieval layer ALREADY EXISTS — do not build embeddings or a
vector store. Two supported patterns:

**Pattern A (preferred): retrieve via backend, generate with Gemini**
1. User asks: "If my commander deals 19 damage then 3 more, is that player dead?"
2. `GET /search?q=<question>&k=8` → scored rule chunks (see `samples/search.json`);
   optionally also `GET /rule/<n>` for any rule numbers detected in the question.
3. Call Gemini with this system prompt shape:

   > You are a Magic: The Gathering judge. Answer ONLY from the rules excerpts
   > provided. Cite rule numbers inline (e.g. "per 903.10a"). If the excerpts
   > don't cover the question, say so — do not answer from memory, as your
   > training data may conflict with the current Comprehensive Rules.

   User content = the question + the retrieved chunk texts.
4. Render the answer with the cited rule numbers as clickable links that open
   `GET /rule/{n}` in a side panel.

**Pattern B (offline fallback): bundled corpus in `rules_kb/`**
- `chunks.jsonl` — 3,887 retrieval-ready chunks, one JSON per line:
  `{id, type, rule|term, section_title, text}`. Small enough to load in the
  browser and keyword-score locally (the backend's scorer is ~20 lines: count
  query-word occurrences in `text`, boost exact-phrase matches).
- `all_rules.json` — flat map of all 3,152 numbered rules for exact lookup.
- `turn_structure.json` — ordered phases/steps for the turn visualizer.

Rules content is from the June 2026 Comprehensive Rules. IMPORTANT for generation:
rule NUMBERS shift between CR editions — always cite from retrieved chunks, never
from the model's memory.

## Reference implementation

`reference_dashboard.html` is the current working (ugly) UI that exercises every
endpoint correctly — treat it as executable documentation, then massively improve it.

## Product brief

App: **Commander deck testing lab**. Core loops:
1. Pick 2–4 decks → run a simulation → watch progress → see win rates (charts) → drill
   into per-game details (who won, game length, key events by turn).
2. Rules assistant: search box + rule browser + turn-structure visualizer.
3. Sim history: past runs with results, comparable side by side (deck A v1 vs v2).

Design: dark, clean, MTG-flavored but not infringing (no WotC art/logos/mana symbols
from official fonts). Desktop-first, responsive. Fast perceived performance: rules
lookups render instantly; sims show live elapsed time and queue state.
