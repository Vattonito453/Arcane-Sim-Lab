# MTG Sim Lab — Cloud Architecture & Front-End Design

Target: cloud-hosted product on Vercel. Design goals, in priority order:
(1) minimum cost-per-user, (2) seamless engine/front-end/deck-import,
(3) AI deck coaching, (4) watchable turn-by-turn sim playback,
(5) Baymard-grade UX.

**Deliberately OUT of scope: play-vs-AI / any interactive game client.**
Two reasons, both decisive: (a) it was the largest engineering item by far
(custom networked PlayerController); (b) legal posture — an interactive digital
Magic play experience competes with MTG Arena and is the category Wizards of
the Coast has historically acted against. A deck ANALYSIS tool (sim, replay,
coaching) sits in the same tolerated category as EDHREC/Moxfield/Archidekt.
Do not re-add this feature without legal review.

---

## 1. System topology

```
┌─ VERCEL ──────────────────────────────────────────────┐
│ Next.js app (App Router)                              │
│  • UI: deck import, sim theater, coaching, play mode  │
│  • API routes (thin): auth, enqueue, results proxy    │
│  • Edge cache/CDN for static + cached AI outputs      │
└──────────────┬────────────────────────────────────────┘
               │ HTTPS / WebSocket
┌─ SIM HOST (Fly.io / Railway / Hetzner VPS) ───────────┐
│ engine API (Python, existing mtg_engine.py evolved)   │
│ jobqueue (SQLite → Postgres when multi-worker)        │
│ Forge workers (Java 17, Docker, deploy/ kit)          │
│  • batch sims only (existing, proven)                 │
└──────────────┬────────────────────────────────────────┘
               │
┌─ DATA (Supabase or Neon Postgres + S3-compatible) ────┐
│ users, decks, sim results (JSON), coaching reports,   │
│ game replays                                          │
└───────────────────────────────────────────────────────┘
               │
┌─ LLM API (small-model tier: Haiku / Gemini Flash) ────┐
│ coaching synthesis + rules Q&A only                   │
└───────────────────────────────────────────────────────┘
```

**Non-negotiable split:** Vercel cannot run Forge (long-lived JVM processes;
serverless timeouts). Vercel = UI + thin API + cache. The sim host runs the
existing `deploy/` containers. This split is also the cost model: Vercel's free
tier carries the UI; sims run on a ~$10-20/mo box that handles thousands of
games/day.

## 2. Token economics (cost-per-user strategy)

The core insight from this project: **almost everything valuable is computable
without an LLM.** Retrieval is keyword scoring over local corpora (zero tokens).
Telemetry is pure code (zero tokens). Sim results are pure code (zero tokens).
LLM tokens are spent ONLY on synthesis and strategy, and every output is cached.

| Feature | Token strategy | Est. cost/use |
|---|---|---|
| Rules lookup/search | No LLM. Local KB search (existing engine) | $0 |
| Rules Q&A assistant | Retrieve top-8 chunks locally → small model synthesizes (~2.5k in / 500 out) → **semantic cache globally** (same question, same answer, forever) | ~$0.003 first ask, $0 after |
| Deck telemetry report | No LLM. `deck_telemetry.py` output rendered as UI | $0 |
| Deck coaching | ONE call per (deck-hash × gauntlet): sim summary + telemetry + top EDHREC synergies as context (~4k in / 1k out). Cached until decklist changes | ~$0.01 per deck version |
| Sim playback | No LLM. Event-log replay | $0 |

Rules of thumb baked into the design:
- **Cache keys:** rules answers → normalized question hash (global);
  coaching → deck hash + gauntlet id.
- **Free tier = $0 marginal cost** (cached coaching, replay, rules lookup).
  Paid tier carries the only token spend: fresh coaching runs and uncached
  rules Q&A — both small-model, both bounded.

## 3. Deck import (seamless, Baymard-forgiving)

Existing `convert_decklist.py` becomes `POST /decks`:
- Accept: Moxfield/Archidekt URL (fetch via their APIs — proven in this project),
  raw text export, or .dck upload. Parse tolerantly (the ENTRY regex already
  handles set codes, foils, collector numbers, single-line exports).
- Respond with a **validation preview**: 100-card check, singleton check, color
  identity vs commander (the game_003 Westvale lesson — check both faces),
  unknown-name suggestions. Never a dead-end error: show what parsed, flag the
  rest inline for correction (Baymard: forgiving inputs, inline validation).
- Store normalized decklist + hash. Hash drives all caching.

## 4. Sim theater (watchable sims)

The adapter's JSON is already an event-sourced game record (games → turns →
events with action/raw). The front end **replays by folding events into board
state** — no server round-trips, one JSON fetch per game (~50-200KB gzipped).

- **Playback UI:** VCR controls (play/pause/step/scrub/speed), turn timeline with
  phase ticks, four player panels (life, commander damage, poison, hand count),
  battlefield zones per player, a combat visualizer (attack arrows,
  blocks, damage numbers), and a scrolling narration feed built from event text.
- **Live mode:** worker streams log lines over SSE as Forge plays; the UI renders
  the same components in real time. (The streaming plumbing exists in
  `run_sim.py`'s line-reader — expose it over HTTP.)
- **Engine upgrade needed (small):** extend `forge_log_adapter.py` to also emit
  periodic `board_snapshot` events (zone contents per player) so the UI can
  seek instantly without folding from turn 1. Forge logs contain zone-change
  events already; snapshots are derivable server-side at adapt time.
- Every replay deep-links (`/replay/{game_id}?t=turn12`) for sharing (Baymard:
  every state addressable).

## 5. Sim opponent quality (replaces the removed play-vs-AI feature)

The human-model work still pays off — entirely server-side, zero legal surface:
apply the **Tier-A heuristic improvements** (attack-splitting, block valuation,
grudge/threat memory, commander-first sequencing) to the BATCH SIM opponents via
a custom `PlayerController` wrapping `PlayerControllerAi`, each fix
regression-tested against the humanness scorecard
(`training/ai_vs_human_analysis.md`). No user ever plays against it; it only
makes simulated tables more realistic, which directly improves coaching quality
— the product's core value lever. This work is OPTIONAL for launch (current
opponents already produced human-validated results) and can ship as a quality
upgrade at any point.

**Training data status:** the current corpus (7 games + rules moments) is
sufficient for the coaching feature and the humanness scorecard. If sim-opponent
calibration is pursued later, 30-50 additional extracted games WITH published
decklists (Mana Dorks-style) would help — optional, not blocking anything.

**Legal hygiene for the analysis-tool posture** (not legal advice; confirm with
a lawyer before public launch):
- Card images: hotlink via Scryfall's API per their guidelines; don't rehost.
- Oracle text: display via Scryfall data with attribution; don't bulk-republish.
- Include the WotC Fan Content Policy notice; no WotC trademarks in the
  product name or branding; no implication of affiliation.
- **The GPL process boundary** (full statement: CLAUDE.md "Legal posture").
  Forge runs server-side as a separate GPL-3.0 process. A thin GPL Java shim
  that wraps `PlayerControllerAi` is permitted (it enables the §5 opponent
  work), but it stays an adapter: decision policies, personality parameters,
  and combo-line data cross into it as data, never as Java logic. Rationale:
  the exit plan sells code we own exclusively; the AI/analysis layer must stay
  engine-agnostic (an acquirer — WotC included — has a better rules engine
  than Forge and would keep our layer, not the shim). Server-side use incurs
  no GPL obligations; distributing a shim or forked-Forge binary requires
  publishing that component's source.
- Monetization order: passive ad revenue on free fan content first (the FCP's
  most-tolerated form); any paid tier requires legal review beforehand.
- No gameplay client, no card sales, no rehosted set images = the same posture
  as the long-tolerated deck-tool ecosystem.

## 6. AI deck coaching (the flagship feature)

Pipeline per deck version (all steps existing tech from this project):
1. Import → hash → run rotated gauntlet on sim host (4 pods × 16, ~40-60 min,
   or "quick read" 1 pod × 16 in ~10 min — user picks; progress streamed).
2. Compute telemetry (win-con support chain, engine rates, death causes).
3. Fetch EDHREC synergy/consensus for the commander (proven scrape path).
4. ONE LLM synthesis call: sim results + telemetry + consensus diff + the
   SIM_CALIBRATION correction table → coaching report with:
   - archetype-adjusted verdict ("18% engine-class = above average", never raw)
   - support-chain status per win con (the table that cracked Inspirit)
   - matchup notes vs each gauntlet archetype + play guide
   - concrete swaps with reasons, each tagged [sim-evidence] / [consensus] / [theory]
5. Cache the report against the deck hash. Re-coaching only on list change.

The calibration doc's rules are enforced in code: seat-rotation always,
archetype baselines in every displayed win rate, telemetry alongside outcomes,
voltron/politics decks labeled "sim = floor."

## 7. UX system (Baymard-applied, not Claude-flavored)

Principles → concrete decisions:
- **Visible system status:** sims show live progress (games done, ETA, current
  game streaming); every long op is cancelable; no spinners without numbers.
- **Forgiving inputs:** deck import accepts anything, validates inline, never
  discards user text on error.
- **Progressive disclosure:** coaching leads with a 3-line verdict; evidence
  (telemetry tables, matchup grids, rule citations) expands on demand. Rules
  citations link to full CR text in a side panel.
- **Recognition over recall:** replay uses standard media-player controls;
  board zones mirror physical table layout (battlefield center, hands at edges).
- **No dead ends:** every empty state has a demo action ("watch a sample game",
  "try the Kilo deck") — one-click into the core loop before signup.
- **Descriptive everything:** buttons say "Run 16-game gauntlet (~10 min)",
  not "Submit".
- Visual language: dark neutral base, one accent per player seat (the four-seat
  palette doubles as data-viz encoding), dense-but-calm tables, tasteful mana
  iconography, zero purple-gradient AI clichés. Desktop-first (deck tools are
  desktop work), replay fully responsive.

## 8. Build order (each phase ships value alone)

1. **Phase 1 — Sim Lab (2-3 weeks):** Vercel app + sim host: import → gauntlet →
   results dashboard → replay theater (post-hoc). Coaching v1 (cached synthesis).
   All engine pieces exist today.
2. **Phase 2 — Live + polish:** SSE live-watching, board snapshots for instant
   seek, semantic cache for rules Q&A, share links.
3. **Phase 3 (optional quality upgrade):** humanized sim opponents
   (server-side PlayerController heuristics, scorecard-tested) for better
   coaching fidelity.

## 9. Cost-per-user snapshot (rough, monthly)

- Vercel: free tier covers early stage; Pro $20 later.
- Sim host: 1× 4-vCPU box ≈ $15-25 → ~3-4 concurrent games, ~2,000
  games/day capacity. Scale = add workers (queue already supports it).
- LLM: coaching ~$0.01/deck-version, rules Q&A ~$0.003/uncached question, on a
  small-model tier. A heavy free user costs ≈ $0.00-0.01/mo; a heavy paid user
  ≈ $0.20-0.50/mo in tokens — dramatically cheaper with play mode removed.
- DB/storage: Supabase/Neon free tier until real traction.

## 10. What this doc assumes from the existing repo

`engine/` (API, queue, adapter, telemetry, calibration), `deploy/` (containers),
`rules/kb` + `training_chunks.jsonl` (RAG corpora), `frontend_handoff/`
(API contract + sample payloads). The only NEW engineering: board snapshots in
the adapter (small), the deck-upload endpoint wiring convert_decklist.py
(small), and the Next.js app itself. With play mode removed, there is no large
engineering item left in the plan — every hard problem was solved and validated
during this project.
