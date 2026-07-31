# Sim Lab — agent orientation

A Magic: The Gathering **deck analysis** tool: import a decklist, run a Forge
simulation gauntlet, replay games event-by-event, and (not yet built) get AI
coaching. Python engine + Next.js front end.

Read this before touching anything. The invariants below were established by
measurement or by legal posture — violating them silently breaks the product.

---

## Repository layout

```
engine/            Python, stdlib only, no frameworks
  mtg_engine.py      rules KB + HTTP API (the server). ~630 lines.
  jobqueue.py        SQLite job queue: enqueue/claim/finish/get
  worker.py          polls the queue, runs sims
  run_sim.py         invokes Forge (Java) as a subprocess
  forge_log_adapter.py  Forge stdout -> event JSON
  cards.py           Scryfall card-fact cache (type lines, P/T, oracle)
  board.py           battlefield reconstruction + accuracy report
  deck_telemetry.py  win-con support metrics (no UI yet)
  shuffle_check.py   proves Forge shuffles; early-play rate vs the maths
  combos.py          known combos in a deck (Commander Spellbook, disk-cached)
  analysis.py        win methods + combo assembled-vs-converted per run
  convert_decklist.py  decklist text -> validated .dck
  tests/             test_adapter.py (unit) + smoke_test.py (live API) + fixtures/
rules/             Comprehensive Rules KB (build_rules_kb.py + kb/*.json)
web/               Next.js 15 App Router, React 19, TypeScript strict
  app/globals.css    THE ENTIRE DESIGN SYSTEM. Pages add no CSS.
  lib/               api.ts, types.ts, format.ts, cards.ts, replay.ts
mockups/           design_principles.md (BINDING) + v3 HTML wireframes
deploy/            Dockerfiles, compose, .env.example
tasks/             per-task specs with acceptance criteria — start here
```

**Key docs, in priority order:**

| Doc | Why you need it |
|---|---|
| `mockups/design_principles.md` | Binding UI rules. Part 3 is non-negotiable. |
| `frontend_architecture.md` | Product scope, topology, token economics, legal posture |
| `deploy_plan.md` | Deployment state, remaining phases, costs, legal checklist |
| `web/README.md` | Front-end architecture, card data, board-accuracy ceiling |
| `engine/SIM_CALIBRATION.md` | How sim results must be interpreted and displayed |
| `TESTING.md` | How to run the prototype, what to click, what to distrust |
| `deploy/HOSTING.md` | Getting it online for remote playtesters, and what only Vincent can do |
| `tasks/*.md` | What to actually build, with acceptance criteria |

---

## Hard invariants

### Don't reimplement Magic

**Forge is the rules engine.** It adjudicates every game correctly; that is why
the win rates are trustworthy. Never derive card behaviour from oracle text to
decide what happened in a game — Scryfall data is for *display and typing* only
(is this a permanent? what's its P/T?). A second rules engine would diverge from
the sim and make replays show a different game than the one that produced the
numbers.

### Forge's log has a known, measured ceiling

Forge logs cards **leaving** the battlefield, never **entering** (measured: 134
`Battlefield→Graveyard`, 15 `→Exile`, 0 entries in a 16-game run). So board state
is *inference*, not a read. `board.py` reports its own error rate — currently
**86.5% of exits match**, and 68 of the 71 misses are tokens created and
sacrificed without ever acting, for which the exit is the object's only mention.
On the 2-game fixture the same figure is **83.3%**. Entries recorded as assumed
(no type data to go on) depend on how warm the Scryfall cache is — **8.4%** with
the cache warm, more on a cold one — so treat exit_match_rate, not assumed_share,
as the regression signal.

Consequences you must respect:
- The **event log is authoritative**; the board is an aid. Never present
  reconstructed board state as ground truth. The replay's top-down table says so
  in a note under it — keep that note if you rework the view.
- Cards of unknown type go in an "Unidentified" group. Don't guess them onto the
  battlefield and don't silently drop them.
- If you change reconstruction, re-run `python3 engine/board.py <result>.json`
  and confirm `exit_match_rate` did not regress.
- **Forge batches attackers onto one line** — `assigned A (100), B (72) and C (326)
  to attack X` — and card names contain commas, so a reference list must be split
  on each `(instance id)`, never on commas. `board.py` `_refs()` and `replay.ts`
  `attackerNames()` implement the same rule; change them together.
- There is no verbosity flag that fixes this, and **patching Forge is forbidden**
  (see legal, below).

### Sim results must be presented honestly

From `engine/SIM_CALIBRATION.md`:
- Always seat-rotate; never report a single-seat win rate.
- Show archetype baselines alongside any win rate — a raw 20% is meaningless.
- Engine/combo decks sim **below** their real strength (the AI can't pilot
  politics or protection timing). Label these results a floor, not a verdict.
- Show telemetry next to outcomes. A deck can lose sims and still be healthy.

### UI design rules are binding

`mockups/design_principles.md` Part 3, in short:
- Sentence case everywhere. No ALL-CAPS microlabels.
- No pill badges. Status is a dot + word: `<span className="st ok"><i/>Passed</span>`
- Exactly **one** `.btn.pri` per view. Everything else is `.btn` or a text link.
- Every page opens with 1–2 sentences of real prose computed from real data.
- All numerals in `.mono` (tabular figures).
- One accent colour (blue) for links/focus only. No gradients. No emoji — inline
  stroke SVGs only.
- **All styling lives in `web/app/globals.css`.** Pages add no CSS files and no
  inline styles except computed percentages (bar widths, scrub position).

The v3 wireframes in `mockups/simlab_v3_*.html` are the reference DOM. New screens
should reuse existing classes rather than inventing any.

### Legal posture — do not change these without a lawyer

From `frontend_architecture.md` §5:
- **No gameplay client.** A playable Magic experience competes with MTG Arena and
  is the category WotC acts against. This tool analyses decks; it does not play.
- **Forge stays a separate, unmodified process** invoked over its CLI. Do not
  vendor, patch, or link Forge's code — that changes the GPL analysis.
- **Card images are hotlinked from Scryfall**, never rehosted. Oracle text is
  displayed with attribution, not bulk-republished.
- Keep the WotC Fan Content notice in the footer; no WotC trademarks in the
  product name or domain; imply no affiliation.
- **A paid tier needs legal review first.** The Fan Content Policy permits fan
  content but not commercialising WotC IP.
- `rules/raw/` and `rules/kb/` contain WotC Comprehensive Rules text. Fine in a
  private repo; **strip them before making this repo public.**

### Scryfall etiquette

`engine/cards.py` already does this correctly — keep it that way: batched
`POST /cards/collection` (≤75 names), a real User-Agent, ~8 req/s, everything
cached on disk. A warm cache makes zero network calls. Never loop single lookups.

### API safety

- Reads are public; `POST /simulate` and `POST /decks` require an API key.
- The server **refuses to start** on a public interface without `MTG_API_KEYS`.
  That is deliberate: a simulation is a 4 GB JVM for 10–60 minutes. Don't remove
  the check; don't default `MTG_ALLOW_OPEN_PUBLIC=1`.
- Rate limiting in `_rate_ok()` is **in-process**, so limits are per-container.
  Two API replicas double every quota. Scale workers, not the API, until there's
  a shared store.
- Result filenames are validated against path traversal. Keep that.

---

## Verification loops — run these, don't assume

```bash
# Engine
python3 engine/tests/test_adapter.py                          # must print ALL ASSERTIONS PASSED
python3 engine/tests/smoke_test.py --sim                      # needs the API up; 34 checks
                                                              # --sim runs real Forge (~40 s)
python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch
                                                              # exit_match_rate must not regress
python3 engine/mtg_engine.py rule 903.10a                     # KB smoke test
python3 -c "import ast,glob;[ast.parse(open(f).read()) for f in glob.glob('engine/*.py')]"

# API (start and test in ONE shell; use a writable MTG_DATA_DIR)
MTG_DATA_DIR=/tmp/mtgdata MTG_API_KEYS=k1 MTG_EMBEDDED_WORKER=0 \
  python3 -u engine/mtg_engine.py serve 8484

# Front end
cd web && npm run verify          # tsc + build into .next-verify
                                  # NEVER `next build` with a dev server or tunnel
                                  # running: it overwrites the .next they serve
                                  # from and they die with "Cannot find module
                                  # './941.js'" until restarted.
                                  # First run needs network (next/font fetches Inter).
```

**Test fixture:** `engine/tests/fixtures/sim_sample.json` — 2 real games, 2,874
events, 310 KB, with its summary recomputed for those 2 games. Committed so
verification works on a fresh clone.

`engine/sim_results/` is gitignored: 108 MB total, of which **77 MB is 31 adapted
result files** (mean 2.6 MB, max 5.7 MB) and **31 MB is `forge_raw_*.log`** — raw
Forge stdout that no endpoint serves and nothing reads after adaptation. All of it
regenerates by running a sim.

---

## Gotchas that will waste your time

1. **A stale duplicate of the whole project sits at `MtG Rules Engine/`** — a
   2026-07-23 snapshot missing `engine/cards.py` and `engine/board.py`. It's
   gitignored. Never edit it. Safe to delete.
2. **SQLite needs working POSIX locks.** On network/9p mounts the queue fails with
   `disk I/O error`. Use a real volume; point `MTG_DATA_DIR` somewhere local.
3. **`next build` needs network** the first time (`next/font` fetches and
   self-hosts Inter and Geist Mono). Offline builds fail on fonts, not on code.
4. **Prefer the small API payloads.** `api.runSummary(file)` (~930 B) and
   `api.runGame(file, n)` (~15 KB) exist because `api.result(file)` is ~235 KB
   gzipped. Don't reintroduce whole-run fetches into pages.
5. **Player keys carry a seat prefix** — `"Ai(2)-Kilo Helm Final"`. Strip with
   `stripAi()` for display; keep the raw key for lookups. Note `Ai(2)-` also
   looks like Forge's `(123)` instance-id syntax — parsers must not confuse them.
6. **The engine is stdlib-only by design.** Don't add Flask/FastAPI/requests to
   `engine/`. It's a deliberate constraint that keeps deployment trivial. There is
   no `requirements.txt` and `deploy/Dockerfile.api` has no `pip` step. Tasks 04
   and 06 each argue a narrow exception (`psycopg`, `PyJWT[crypto]`) — if you add
   one, create the dependency plumbing and update this bullet in the same commit.
7. **Two corpus sizes, both correct.** `/search` scores **3,887** chunks (rules +
   glossary); `all_rules.json` holds **3,152** numbered rules. Use 3,887 when
   talking about retrieval coverage, 3,152 for exact rule lookup.
8. **Rule numbers shift between CR editions.** Always cite from retrieved chunks,
   never from model memory. This is the whole point of the RAG discipline in
   `frontend_handoff/API_SPEC.md`.
9. **Decks live in two places.** `engine/decks/` is bundled into the image;
   imported decks go to `MTG_DATA_DIR/decks` because that's the only path the
   worker container can also see. Use `_find_deck()` / `_list_decks()`, never a
   bare `Path(__file__).parent / "decks"`.

## Working agreements

- Small, verifiable commits. Run the relevant loop above before saying done.
- When you change a documented number (accuracy rate, payload size), re-measure
  and update the doc in the same commit. Don't let docs drift.
- If a measurement contradicts a claim in these docs, **trust the measurement**
  and fix the doc — several numbers here came from exactly that.
- State uncertainty plainly. "Board membership is inferred at 86.5% exit match"
  is useful; "board state is accurate" is not.
- Don't spend money, create hosting accounts, or generate production secrets.
  Those are Vincent's, and `deploy_plan.md` Phase 0 covers them.
