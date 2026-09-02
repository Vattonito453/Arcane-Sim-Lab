# Sim Lab — agent orientation

A Magic: The Gathering **deck analysis** tool: import a decklist, run a Forge
simulation gauntlet, replay games event-by-event, read per-deck scorecards and
win-con telemetry, and get AI coaching. Python engine + Next.js front end.

Coaching and the rules assistant are BUILT and shipped; their generation is
gated on `MTG_LLM_API_KEY`, which production does not set, so those two
features are dark until an owner sets it. `deploy/preflight.py` is the
authority on what is live: run it rather than trusting this paragraph.

Read this before touching anything. The invariants below were established by
measurement or by legal posture — violating them silently breaks the product.

---

## Repository layout

```
engine/            Python, stdlib only, no frameworks
  mtg_engine.py      rules KB + HTTP API (the server). ~1,555 lines.
  jobqueue.py        SQLite job queue: enqueue/claim/finish/get
  worker.py          polls the queue, runs sims
  run_sim.py         invokes Forge (Java) as a subprocess
  forge_log_adapter.py  Forge stdout -> event JSON
  cards.py           Scryfall card-fact cache (type lines, P/T, oracle)
  board.py           battlefield reconstruction + accuracy report
  deck_telemetry.py  win-con support metrics (live at /results/{file}/telemetry)
  shuffle_check.py   proves Forge shuffles; early-play rate vs the maths
  combos.py          known combos in a deck (Commander Spellbook, disk-cached)
  analysis.py        win methods + combo assembled-vs-converted per run
  convert_decklist.py  decklist text -> validated .dck
  tests/             16 test_*.py (unit) + smoke_test.py (live API) + fixtures/
rules/             Comprehensive Rules KB (build_rules_kb.py + kb/*.json)
web/               Next.js 15 App Router, React 19, TypeScript strict
  app/globals.css    THE ENTIRE DESIGN SYSTEM. Pages add no CSS.
  lib/               api.ts, types.ts, format.ts, cards.ts, replay.ts
Design System/     DESIGN_SYSTEM.md (BINDING) + tokens css + backdrop art + dc.html specs
mockups/           design_principles.md (superseded for visuals) + v3 HTML wireframes
deploy/            Dockerfiles (api/worker/web), compose, worker-entrypoint.sh
tasks/             per-task specs with acceptance criteria — start here
```

**Key docs, in priority order:**

| Doc | Why you need it |
|---|---|
| `Design System/DESIGN_SYSTEM.md` | **Binding UI spec** (Arcane reskin): tokens, type, components, backdrop, a11y contract. Tokens in `Design System/arcane-sim-lab.tokens.css`. |
| `mockups/design_principles.md` | Superseded for visual language; its structural rules (prose openers, one primary, honesty notes) still bind. |
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

### Board state: read it from the shim, infer it only from stdout

Two paths, and only one of them guesses. **Check which one a result file is on
before quoting any accuracy number** — `board.py` prints `basis` first.

**Shim path (`meta.agent = simlab-forge-shim/*`, games carry `zones`): a read.**
`GameEventCardChangeZone` fires in both directions keyed by Forge's own card id,
including `None → Battlefield`, which is a token being created. Since shim
0.3.0 each record also carries the card's core `types`, net `pt` and `token`
flag as of the move. Measured on a 3-game humanized run: **exit_match_rate 1.0,
assumed_share 0.0**, tokens typed correctly with live P/T (`Zombie Token 2/2`,
and `3/3` where an anthem had grown it), zero Scryfall lookups. Re-adapt old
shim JSONL to pick up the new fields; logs written before 0.3.0 keep working
and fall back to Scryfall typing (measured 37.6% assumed on one such file).

**Stdout path (stock Forge runs, and every result file from before the shim):
inference.** Forge logs cards leaving the battlefield, never entering
(measured: 134 `Battlefield→Graveyard`, 15 `→Exile`, 0 entries in a 16-game
run). `board.py` reports its own error rate — **86.5% of exits match**, and 68
of the 71 misses are tokens created and sacrificed without ever acting, for
which the exit is the object's only mention. On the 2-game fixture the same
figure is **83.3%**. Entries recorded as assumed depend on how warm the
Scryfall cache is (**8.4%** warm, more cold), so treat exit_match_rate, not
assumed_share, as the regression signal.

Consequences you must respect:
- On the stdout path the **event log is authoritative** and the board is an
  aid: never present it as ground truth, and keep the note under the replay's
  top-down table if you rework the view. On the shim path the board IS a read,
  but the honesty note still has to distinguish the two rather than quietly
  upgrading every replay.
- Cards of unknown type go in an "Unidentified" group. Don't guess them onto the
  battlefield and don't silently drop them.
- If you change reconstruction, re-run `python3 engine/board.py <result>.json`
  on BOTH a stdout fixture and a shim result, and confirm neither
  `exit_match_rate` regressed.
- **Forge batches attackers onto one line** — `assigned A (100), B (72) and C (326)
  to attack X` — and card names contain commas, so a reference list must be split
  on each `(instance id)`, never on commas. `board.py` `_refs()` and `replay.ts`
  `attackerNames()` implement the same rule; change them together.
- **Forge joins multi-defender combat into ONE multi-line log entry.**
  `GameLogFormatter` appends `\n` between defenders in an attack declaration and
  between attackers in a defender's block declaration, so the printed (or
  shim-serialised) entry is one captioned line plus caption-less continuation
  lines. Until 2026-09-01 both adapters skipped every caption-less line as
  chatter, which dropped the second defender's attack and every block after the
  first attacker: 27 attack, 932 block and 7,340 didn't-block lines across 187
  stock logs, and 193 of 580 combat entries in one 16-game shim run. The replay
  then showed blocks with no attack and combat damage from an undeclared
  creature (the "illegal blocker for another deck" report). `forge_log_adapter`
  now emits each combat continuation line as its own event and keeps other
  continuation text (modal spell modes) on the event under `more`;
  `shim_log_adapter` captions every line of a COMBAT entry. Attacks are one
  lane PER DEFENDER in `replay.ts` and blocks carry the blocking player; never
  collapse them into one lane again. `readapt.py --write --all` recovers the
  events in existing shim-run results (counted as `events` in its gain report;
  it re-parses `shim_raw_*.jsonl` only, so a stock-path result needs a manual
  re-adapt from its `forge_raw_*.log`) and keeps each file's mtime, which the
  results index shows as the run's date.
- There is no verbosity flag that fixes the stdout path, and patching Forge is
  off the table. The sanctioned fix is the GPL shim driving `Match`
  programmatically, which is now the default agent — so the way to raise board
  accuracy on a given run is to run it through the shim, not to improve the
  inference (see legal, below, and `training/forge_integration.md`).

### Sim results must be presented honestly

From `engine/SIM_CALIBRATION.md`:
- Always seat-rotate; never report a single-seat win rate.
- Show archetype baselines alongside any win rate — a raw 20% is meaningless.
- Engine/combo decks sim **below** their real strength (the AI can't pilot
  politics or protection timing). Label these results a floor, not a verdict.
- Show telemetry next to outcomes. A deck can lose sims and still be healthy.

### UI design rules are binding

`Design System/DESIGN_SYSTEM.md` (the Arcane Sim Lab reskin, applied 2026-07-31)
is the binding spec. In short:
- **Never hardcode a hex** — every colour is a token from
  `arcane-sim-lab.tokens.css` (mirrored into `web/app/globals.css` `:root`).
- Cyan is interaction, violet is secondary, WUBRG pips are data — a colour never
  means two things. Pips never go inside a button.
- Glow marks only the primary action and live activity.
- Status is **shape**, not hue: running = filled circle + glow, queued = hollow
  circle (and no progress fill it hasn't earned), done = filled square,
  failed = filled circle.
- Cinzel appears exactly once per page — the wordmark. Body is Space Grotesk;
  data/figures are JetBrains Mono.
- Content sits on glass panels over the fixed backdrop; never text on unscrimmed
  art; panels never nest.
- Never disable the primary — state the blocker beside it.
- Every field keeps a persistent visible label; 2px cyan focus ring everywhere.
- **No em dash in copy.** Anything a user reads (JSX text, string literals,
  `aria-label`/`title`/`placeholder`, page metadata, and engine strings that
  surface in the UI) uses a period, colon, semicolon or parentheses instead.
  An empty value in a table or figure is an en dash `–`. The one exemption is
  Scryfall card text, which is WotC's printed wording shown verbatim
  ("Legendary Creature — Phyrexian Angel Horror"). Comments and docs are not
  copy. Full rule and the substitution table: `DESIGN_SYSTEM.md` §1.
- `--ink-4` is the text floor; the Fan Content + Scryfall footer lines render at
  it, never below.
- Still true from the old spec: every page opens with 1–2 sentences of real
  prose computed from real data; one primary per view; honesty notes on
  inferred data; **all styling lives in `web/app/globals.css`** — pages add no
  CSS files and no inline styles except computed percentages.

Reference DOM: `Design System/*.dc.html` (visual spec + canonical screens).
Mascot and mana pips are **commissioned painted artwork served as WebP** from
`web/public/art/` (`mascot-brass-archivist*.webp`, `pips/pip-{w,u,b,r,g,c}.webp`),
wrapped by `web/components/Mascot.tsx` and `web/components/ManaPips.tsx`. They
are the only sanctioned bitmaps besides the backdrop plates; everything else is
inline SVG or CSS. Never emoji, never WotC mana symbols, never recoloured by CSS.

Tracing this art to vector is a dead end that has already been tried: it is
painted with continuous gradients, so tracing posterizes it into flat bands and
costs ~15x the bytes. Re-export with `Design System/tools/export_pips.py`
(needs Pillow + numpy, hence outside stdlib-only `engine/`), which is verified
to reproduce the committed WebPs byte-for-byte. Two traps it encodes: the source
PNGs are ~70% transparent with junk RGB behind, so **never `convert("RGB")`** (it
bakes in a grey plate), and **never clip to a circle** (it amputates the
medallion's spikes and wing flourishes). The source PNGs are not committed.

### Legal posture — two regimes, one bright line

Two separate legal regimes apply and must never be conflated: **GPL** (Forge's
license) and **WotC IP** (the Fan Content Policy). Forge's GPL cannot grant
WotC rights; WotC's tolerance says nothing about GPL duties.

**The GPL process boundary (posture set by Vincent, 2026-07-31).** Forge is
GPL-3.0. The business goal is ad-funded revenue first, then an exit — and in an
acquisition, buyers pay for code owned exclusively. GPL code can be sold but
never exclusively (its copyright belongs to Forge's ~hundreds of contributors
and it stays GPL for everyone), so **everything commercially valuable must live
on our side of a process boundary**: the Python engine, the Next.js app,
telemetry, coaching, the training corpus, and — critically — all AI decision
*policies*. Rules that keep the boundary bright:

- Java that links Forge (e.g. a `PlayerController` shim wrapping
  `PlayerControllerAi`) is a GPL derivative. That is now **allowed**, but it
  lives in its own repo/module under GPL-3.0 and stays a *thin adapter*:
  personality params, combo lines, heuristic weights and anything clever cross
  the boundary as data (JSON in, decisions out), never as Java logic. This
  keeps the AI layer engine-agnostic — Arena's rules engine is better than
  Forge, and an acquirer would retarget our analysis/AI layer onto their own
  engine and discard the shim. Design for that.
- Never vendor Forge or shim Java into this repo; the engine talks to them by
  subprocess/CLI only. No in-process bridges (Py4J, JNI) into our code.
- Distributing a modified Forge or a shim **binary** (public Docker image,
  installer) requires publishing that component's source under GPL-3.0.
  Running it server-side imposes nothing (GPL v3, not AGPL).
  **This changed and the doc used to say otherwise.** The worker image no
  longer pulls stock Forge only: `deploy/Dockerfile.worker` builds the shim in
  a `shim-builder` stage (or takes a vendored jar) and bakes
  `simlab-forge-shim.jar` into the runtime image, and the shim is the default
  agent. So the image now *contains* a GPL derivative. Running it on our own
  server still imposes nothing. **Publishing that image** (a public registry,
  an installer, anything a third party receives) carries the GPL-3.0 source
  obligation for the shim, which is satisfied only while the
  `simlab-forge-shim` repo stays public at the commit the image was built
  from. Do not push this image anywhere public without checking that first.
- Prefer upstream PRs to Card-Forge over carrying a fork; any fork we do carry
  must be public from day one.
- GPL non-compliance is the only path where Forge contributors could ever
  claim money from us. Compliance is cheap; keep it boring.

**The WotC side (confirm with a lawyer before public launch):**
- **No gameplay client.** A playable Magic experience competes with MTG Arena
  and is the category WotC acts against. This tool analyses decks; it does not
  play. The humanized sim AI is batch-only, server-side; no user ever plays it.
  **Carve-out (2026-08-02):** a solo, rules-free playtest sandbox (draw hands,
  drag cards — Moxfield/Archidekt-style goldfishing) is allowed. The tripwires
  that make something a gameplay client are: an opponent of any kind, rules
  adjudication by the app, or a declared win/loss. Cross any one → legal
  review first. See `tasks/08-goldfish-mode.md`.
- **Card images are hotlinked from Scryfall**, never rehosted. Oracle text is
  displayed with attribution, not bulk-republished.
- Keep the WotC Fan Content notice in the footer; no WotC trademarks in the
  product name or domain; imply no affiliation.
- **Monetization order matters.** Passive ad revenue on free fan content is
  what the Fan Content Policy most plainly tolerates. Paywalls, subscriptions,
  or any paid tier are the risky category — legal review first.
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

### Sim timing: three numbers, and they are not interchangeable

- **Per-game clock** (`--clock`, 900 s, measured): the wall a single game gets
  before Forge draws it. Passed explicitly from the engine so it cannot drift
  from the maths below.
- **Outer ceiling** (`sim_timeout_seconds`): played games x clock + rotations x
  150 s + 300 s. A hang detector, nothing else. It must exceed worst-case play
  or it kills legitimate work, which is what a flat 2 h used to do (audit A14).
  4.2 h for 16 games, 16.2 h for 64. `reap_stale()` derives from it, so raising
  one without the other can no longer reap a live job.
- **Typical duration** (`estimate_sim_seconds`): what to TELL a user, roughly
  40-105 min for a 4-deck 16-game gauntlet. Never used to kill anything.
  Re-measured 2026-08-28: the plan agent deliberates more than the stock AI
  the old 10-25 min figure came from (in-JVM game median 220-260 s across 186
  agent-era games, `TYPICAL_GAME_SECONDS = 240`). If that constant changes,
  re-measure and update this line in the same commit.
- **Turn cap** (`--max-turns`, default 120 in run_sim, shim >= 0.8.0): the
  deterministic bound. Measured on 1,198 finished games, p95 is 70-75 turns
  and the max is 122, so 120 trims almost nothing legitimate while ending
  turn-cycling stalemates without waiting out the clock. It cannot end a game
  wedged INSIDE one turn (token-copy boards recheck every static ability per
  token entering play); only the clock catches those.

Keep these separate. Quoting the ceiling to a user reads as "this may take 16
hours"; using the estimate as a timeout kills healthy runs.

**A rotated run plays more games than were requested**, rounded up so every
deck sits in every seat the same number of times (10 requested -> 12 played).
Any surface that shows a game count shows the played number and says why.

### Containerized Forge needs a display

The worker image installs xvfb and starts a virtual display before the worker
runs (`deploy/worker-entrypoint.sh`). Forge's single desktop jar initializes AWT
for DPI scaling even in `sim` mode, and it fails **silently** without a display —
its Sentry handler swallows the exception and exits 1 with no output. Do not
replace the entrypoint with `xvfb-run`: its SIGUSR1 readiness handshake does not
complete as PID 1. Both images run Python with `-u` so container logs are not
lost to block buffering. See deploy/HOSTING.md.

---

## Verification loops — run these, don't assume

```bash
# Engine — every test, discovered. Do NOT replace this with a hand-written
# list: the previous list named 8 files while 16 existed, so "running the
# loop" silently ran half the suite. Each must print ALL ASSERTIONS PASSED.
for t in engine/tests/test_*.py; do
  python3 "$t" >/dev/null 2>&1 && echo "pass  $t" || echo "FAIL  $t"
done

python3 engine/tests/smoke_test.py --sim                      # needs the API up; every
                                                              # check must pass. Do not quote a
                                                              # count here: it moved 23 -> 29 ->
                                                              # 35 -> 37 and every doc that
                                                              # pinned one now reads as a failure.
                                                              # --sim runs real Forge (~40 s)

# Is the DEPLOYMENT actually serving what we think? Tests and a clean deploy
# both passed while the prediction model was missing from the image, because
# the endpoint answered 200 with {"available": false}. This is the only check
# that would have caught it. Exits non-zero when a surface meant to be live
# is dark, and prints the reason for every surface deliberately off.
sudo docker exec deploy-api-1 python3 /app/deploy/preflight.py --files
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

# No em dash in copy. Comments are exempt, so this is a first pass, not a verdict:
# read each hit and confirm it is a comment before dismissing it.
grep -rn "—" web/app web/components web/lib --include='*.tsx' --include='*.ts' \
  | grep -vE ':\s*(//|\*|/\*|\{/\*)'
```

**Test fixture:** `engine/tests/fixtures/sim_sample.json` — 2 real games, 2,975
events, 315 KB, with its summary recomputed for those 2 games. Committed so
verification works on a fresh clone. Re-adapted 2026-09-01 from its raw log
(`forge_raw_20260724_093703_397702.log`) so it carries the continuation lines
of Forge's multi-line combat entries; the old file had 2,874 events.

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
- State uncertainty plainly, and name the path it applies to. "Board membership
  is inferred at 86.5% exit match on stdout runs, and read exactly on shim runs"
  is useful; "board state is accurate" is not.
- Don't spend money, create hosting accounts, or generate production secrets.
  Those are Vincent's, and `deploy_plan.md` Phase 0 covers them.
