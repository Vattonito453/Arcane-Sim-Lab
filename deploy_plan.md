# Sim Lab — public beta deployment plan

Target: open-signup public beta of the deck analysis tool (sim → replay → coaching).
Assumes `frontend_architecture.md` §1 topology: Vercel for the UI, a separate sim
host for Forge, because Vercel cannot run long-lived JVMs.

**Status of the four launch blockers** found by auditing the running system:

| Blocker | Status | Evidence |
|---|---|---|
| API served requests serially | **Fixed** — `ThreadingHTTPServer` | 4 concurrent 1 s requests: 4.04 s → 1.02 s |
| Replay downloaded a whole run | **Fixed** — per-game endpoints + gzip | overview 235 KB → 930 B; replay → 15.3 KB |
| No auth or rate limiting | **Fixed** — API keys + quotas | unauthed `POST /simulate` → 401; 4th sim in an hour → 429 |
| State was host-local | **Partly** — env-driven paths, documented | still SQLite + local files; see Phase 2 |

What remains is genuinely remaining: identity, durable storage, the coaching
feature, and the legal review. Nothing below is blocked on unsolved engineering.

---

## Phase 0 — before anything is public (half a day)

1. `cp deploy/.env.example deploy/.env`, generate a key:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Set `MTG_ALLOW_ORIGIN` to the real front-end origin. `*` plus credentials is
   the classic CORS mistake; the API currently sends no cookies, but tighten it
   before that changes.
3. Put TLS in front. Cheapest correct option: Cloudflare Tunnel (no open inbound
   port, free tier) or Caddy with automatic Let's Encrypt. The API speaks plain
   HTTP by design and should never be directly exposed.
4. Keep `MTG_PORT` on loopback so only the proxy can reach the API.
5. Verify the refusal works: unset `MTG_API_KEYS`, confirm the API exits rather
   than starting open.

## Phase 1 — single-host beta (1–2 days)

This is the smallest thing that is honestly deployable.

```
Cloudflare (TLS, WAF, caching)
        │
Vercel: Next.js UI  ──HTTPS──►  one VPS (Hetzner CPX31 / Fly 2×shared-4GB)
                                  ├── api container   (this repo, threaded)
                                  ├── worker × 1-2    (Java 17 + Forge)
                                  └── /data volume    (SQLite queue, results, card cache)
```

- Front end: `cd web && vercel deploy`. Set `NEXT_PUBLIC_API_BASE` to the tunnel
  hostname. The UI already reads a runtime-configurable base URL, so this is
  config, not a rebuild.
- Sim host: `docker compose --env-file deploy/.env up -d --build`.
- Warm the card cache once per host: `python3 engine/cards.py warm <result>.json`.
  It lives in `/data`, so it survives restarts and is shared with workers.
- **Storage caveat that will bite you:** the job queue is SQLite, which needs
  working POSIX locks. On a network or 9p-style mount it fails with
  `disk I/O error` — I hit exactly this during testing. Use a real block volume
  (Hetzner volume, Fly volume), never NFS or a bind mount from a host FS that
  doesn't support locking.

**Capacity.** A 4-vCPU box runs ~3 concurrent Forge games and roughly 2,000
games/day. At 16 games per gauntlet that is ~125 gauntlets/day. With
`MTG_SIM_PER_HOUR=6` a single user can consume 96 games/hour, so about 20 active
users saturate one box. Watch queue depth, not CPU.

## Phase 2 — durable, multi-host (when Phase 1 saturates)

Do these in this order; each is independently useful.

1. **Object storage for results.** Result files are immutable: 31 runs totalling
   77 MB, mean 2.6 MB, max 5.7 MB (plus 31 MB of `forge_raw_*.log` that nothing
   serves and could simply be deleted after adaptation). Move them to S3/R2 and
   serve via CDN with the `immutable` cache header the API already sets. Also fix
   `_list_results()` while you're there — it parses every result file in full to
   build the index, which on object storage means 31 multi-megabyte GETs per
   `GET /results`. A sidecar index is the bigger win. See `tasks/05`.
2. **Postgres for the queue.** `engine/jobqueue.py` is a thin SQLite wrapper —
   `enqueue`/`claim`/`finish`/`get`. See `tasks/04`.

   **Correction:** Postgres alone does *not* unlock workers on separate machines,
   as an earlier draft of this doc claimed. Results are still written to the
   worker's own `MTG_DATA_DIR/sim_results` (`worker.py`) and read from the API's
   own `RESULTS_DIR` (`mtg_engine.py`), so a remote worker would complete jobs the
   API can never serve. **Both 04 and 05 are required.** Until both ship, workers
   must share a filesystem with the API.
3. **Shared rate-limit store.** `_rate_ok()` in `mtg_engine.py` is in-process, so
   limits are per-container. Two API replicas double every quota. Move to Redis,
   or keep exactly one API container (documented, and fine well past beta).
4. **Real accounts.** For open signup you need per-user quotas, not shared API
   keys. The auth layer is deliberately a single seam (`_authed()` and
   `client_key`): swap key-matching for JWT verification from Clerk/Auth0/Supabase
   and the quota logic keeps working unchanged.

## Phase 3 — the product work

None of this is deployment; it's what makes the beta worth using.

- **Coaching synthesis** (`frontend_architecture.md` §6) — the flagship feature and
  still unbuilt. One LLM call per deck-hash × gauntlet, cached.
- **Telemetry rendering** — `deck_telemetry.py` output has no UI yet.
- **Rules assistant** — retrieval already exists (`/search`); needs the generation
  step and a semantic cache.
- **Board snapshots via Forge's API** — the current reconstruction matches 86.5%
  of battlefield exits; the residual is tokens Forge never logs entering (see
  `web/README.md`). Exact state needs `simulateOffthreadGame`. Review GPL
  implications first.

---

## Costs (monthly, honest ranges)

| Item | Beta | Notes |
|---|---|---|
| Vercel | $0–20 | Free tier carries the UI; Pro when you need team seats or analytics |
| Sim host | $15–30 | Hetzner CPX31 ~€15; Fly 2×shared-cpu-4GB ~$25 |
| Volume / object storage | $1–5 | 80 MB of results today; R2 has no egress fee |
| Cloudflare | $0 | Free tier covers TLS, tunnel, and caching |
| Postgres (Phase 2) | $0–25 | Supabase/Neon free tier until real traction |
| LLM (coaching) | $0.01/deck-version | Small-model tier, cached per deck hash |
| **Total** | **~$16–55** | Dominated by the sim host |

The cost risk is not infrastructure, it is **compute abuse**: one unthrottled
`/simulate` loop can pin a box indefinitely. That is what the quotas exist for.
Set a hard spend cap at your host and alert on queue depth.

## Abuse and reliability checklist

- [x] Auth required for `/simulate` and `/decks`
- [x] Per-caller simulation quota, max games per job, queue-depth backpressure
- [x] Read rate limit, decklist size cap (100 KB)
- [x] Deck allowlist check before enqueue (no arbitrary filenames)
- [x] Path-traversal guard on result filenames
- [x] Container healthcheck, `restart: unless-stopped`
- [ ] Per-user quotas (needs real accounts, Phase 2)
- [ ] Structured request logging and an error tracker (Sentry)
- [ ] Alert on queue depth and worker liveness
- [ ] Backups: results to object storage, queue DB snapshot
- [ ] Load test at expected concurrency before opening signup

## Legal review — do this before open signup, not after

`frontend_architecture.md` §5 sets the posture and it is sound; public launch is
what makes it load-bearing. This is not legal advice — get a lawyer to confirm.

**Wizards Fan Content Policy.** The app must stay unofficial, unaffiliated, and
non-commercial in the ways the policy requires. Practical items: the Fan Content
notice is already in the footer; keep WotC trademarks out of the product name and
domain; no card images rehosted (we hotlink Scryfall, which is correct); do not
imply endorsement. **Charging money is the sharpest edge** — the policy permits
fan content but not commercialization of WotC IP. If Sim Lab ever has a paid
tier, that decision needs a lawyer first.

**Forge is GPL.** Today Forge runs as a separate, unmodified process invoked over
a CLI, which is the defensible arrangement. Two things would change the analysis:
linking Forge's code into your own program, or shipping a modified Forge. The
Phase 3 "board snapshots via `simulateOffthreadGame`" idea does exactly the first
— calling Forge's Java API from your own shim. Get that reviewed before building
it, and consider keeping the shim a separate GPL-licensed program that
communicates over a pipe.

**Scryfall.** Their API guidelines ask for rate limiting, a real User-Agent, and
caching rather than redistribution — `engine/cards.py` does all three (batched
`/cards/collection`, ~8 req/s, disk cache, only display fields stored).

**Your users' data.** Open signup means you hold email addresses and decklists.
You need a privacy policy and terms of service, a deletion path, and — if you have
EU or California users — GDPR/CCPA basics. Using a hosted auth provider moves most
of the credential risk off your plate.

## Definition of done for the beta

1. Front end on Vercel, engine behind TLS, no public unauthenticated write path.
2. Real accounts with per-user quotas.
3. Results in object storage; queue on Postgres if more than one worker host.
4. Coaching feature live — without it the product is a sim viewer.
5. Error tracking and queue alerting.
6. Legal review signed off; privacy policy and terms published.
7. Load tested at target concurrency with quotas enforced.
