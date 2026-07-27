# 06 — Real accounts and per-user quotas

**Why:** open signup needs per-user identity. Shared API keys cannot express "this
user's 6 sims per hour", cannot be revoked individually, and cannot own anything.
`deploy_plan.md` Phase 2 item 4 is right that the auth layer is deliberately a
single seam — but the seam is narrower than the plan implies, and the front end has
none of it. Read the honest notes below before estimating.

**Depends on: task 04.** Users, deck ownership, and run ownership need a shared
relational store. Do not build a second one. **Touches task 05:** if results are in
a public bucket, per-user ownership leaks the moment more than one person signs up —
see Stage 5.

**Read first:** in `engine/mtg_engine.py` — `API_KEYS` (line 205), `_bearer()` (219),
`_rate_ok()` (223), the `client_key` property (391), `_authed()` (432), `_deny()`
(440), the auth gate at line 521, and the bind-refusal block at 575–583. In
`web/lib/api.ts` — `apiKey()`/`setApiKey()` (20–31) and the `Bearer` header in
`post()` (74).

**Size:** the largest task after 01, and the only one with legal obligations attached.

**Done means:** the shared definition of done in `tasks/README.md` applies in full,
plus the acceptance criteria below.

---

## Four honest notes that change the shape of this task

1. **`_rate_ok()` is in-process.** Quotas are per-container; two API replicas double
   every limit. CLAUDE.md and `deploy_plan.md` Phase 2 item 3 both say so. Per-user
   quotas are only *trustworthy* behind a shared store. This task must ship a quota
   **interface** with an in-process default and an optional Redis backend, and the
   deploy docs must keep saying "run exactly one API container" until Redis is
   configured. Shipping per-user quotas while running two replicas is worse than
   today, because the limit now looks personal and precise while being silently
   doubled.

2. **`client_key` will collapse every user into one bucket.** Line 395 returns
   `f"key:{k[:12]}"` — the first 12 characters of the credential. Every JWT from the
   same issuer starts with the same header segment
   (`eyJhbGciOiJSUzI1NiI…`), so a naive swap gives all authenticated users **a single
   shared rate-limit bucket**. The bucket must become `user:{sub}` derived from the
   *verified* claims, and it must never be derived from raw token bytes.

3. **The front end has no sign-in seam to swap — it is greenfield.**
   `setApiKey()` is exported and **called from nowhere** in `web/`. The only settings
   component is `ApiBaseSetting.tsx`, which sets the base URL. `api.ts`'s 401 message
   says "set one under Engine" and no such UI exists — that string is drift; fix it.
   Also `get<T>()` (line 62) sends **no** `Authorization` header at all, so once reads
   are ownership-scoped every read path needs the token added.

4. **Imported decks are already broken in the deployed topology, and this task is
   where it must be fixed.** `_import_deck()` (line 332) slugifies the deck *name*
   into a filename and writes to `Path(__file__).parent / "decks"` — inside the API
   container's image, **not** `MTG_DATA_DIR`. `worker.py` line 32 defaults
   `deck_dir` to its own container's copy of that directory, and `POST /simulate`
   sends no `deck_dir` in the payload. So in `deploy/docker-compose.yml`: a deck
   imported through the API passes the API's allowlist check, gets enqueued, and the
   worker cannot find the file. On top of that, two users importing "Zombies" produce
   the same slug and silently overwrite each other. Open signup turns a restart-time
   data-loss bug into a cross-user data-loss and disclosure bug. Deck storage must
   move to `MTG_DATA_DIR` and become per-user keyed. Verify the bug first (Stage 4)
   so the fix is grounded.

## Constraints

- **Do not weaken the bind refusal.** `serve()` exits when binding a non-loopback
  interface with no `MTG_API_KEYS` (CLAUDE.md: "Don't remove the check; don't default
  `MTG_ALLOW_OPEN_PUBLIC=1`"). With JWTs there may be no `MTG_API_KEYS` at all, so the
  check must be generalised, not deleted: refuse unless **either** API keys **or** a
  JWT issuer is configured. The property being protected — no anonymous access to a
  4 GB JVM — is unchanged.
- **API keys keep working.** Machine callers, `curl`, and the existing dashboard need
  them. `_authed()` accepts a verified JWT **or** a key in `API_KEYS`; a key resolves
  to a synthetic principal (`key:<prefix>`) with its own quota row.
- **Reads stay public where they can.** Rules lookups, `/search`, `/health`,
  `/turn-structure` have no owner and must not require sign-in — that is the product
  being usable before signup. Only decks, runs, and results become owned.
- **Design rules** (`mockups/design_principles.md` Part 3): sign-in and account UI
  obey the same rules as everything else — sentence case, one `.btn.pri` per view,
  `.st` dot + word for state, no pills, no emoji, no new CSS file. `Chrome.tsx`
  hardcodes `vincent` and a `Pro` badge (line 28); those become the real user and
  either the real plan or nothing.

---

## Stage 1 — pick a provider, then build sign-in

Compare briefly in a short `## Auth provider` section you add to `deploy_plan.md`,
then implement one. **Verify current free-tier limits and pricing yourself before
committing** — the numbers move, and this spec deliberately does not quote them as
fact.

- **Clerk** — first-class `@clerk/nextjs` for App Router (middleware plus drop-in
  `<SignIn/>`, `<UserButton/>`), issues standard RS256 JWTs with a JWKS endpoint,
  generous free tier for a beta. Least code for this stack.
- **Auth0** — the most mature and the most configuration surface; generic across
  stacks, so you write more glue for a Next.js App Router app than Clerk needs.
- **Supabase** — bundles Postgres, which task 04 needs anyway: one vendor for auth
  *and* the queue DB, on one free tier. The cost is coupling — your queue and your
  identity provider fail together, and moving off means moving both.

**Recommendation: Clerk**, because (i) the UI is Next.js 15 App Router on Vercel and
Clerk's middleware and components are the smallest amount of code to a working
session, (ii) it emits ordinary RS256 JWTs over a public JWKS URL, so the engine's
verification is provider-agnostic and swapping later touches one constant, and
(iii) credential handling, email verification, and password reset move off your
plate entirely — which `deploy_plan.md`'s legal section explicitly wants. Take
**Supabase** instead if you would rather have one vendor and one bill for auth and
Postgres together; that is a reasonable trade, not a mistake. Record whichever you
choose and why.

Front end:

- Add the provider's middleware and a sign-in route. Protect `/import` and the run
  pages; leave `/` and `/rules` (task 03) readable signed-out.
- `web/lib/api.ts`: replace `apiKey()`/`setApiKey()` with a token getter that returns
  the session JWT, falling back to `localStorage["simlab.apiKey"]` and
  `NEXT_PUBLIC_API_KEY` so `curl`-style local development still works.
  **Add the `Authorization` header to `get<T>()` as well as `post<T>()`.**
- **Review the `cache: "force-cache"` on `runSummary` and `runGame`** (lines 89 and
  94). Caching an authenticated response is how one user's run ends up in another
  user's page. Either drop `force-cache` on owned routes or key it per user; do not
  leave it as-is and hope.
- Fix the 401 copy in `fail()` (line 57): it should say to sign in, not to "set one
  under Engine".
- `Chrome.tsx`: real user name, avatar, and sign-out from the provider's hooks.

**Verify:** `cd web && npx tsc --noEmit` clean and `npx next build` succeeds; signed
out, `/import` redirects to sign-in and `/` still renders; signed in, the topbar shows
the real user; in devtools, a `GET /results` request carries
`Authorization: Bearer eyJ…`; `grep -rn "force-cache" web/lib/api.ts` shows no owned
route caching an authenticated response.

## Stage 2 — verify JWTs in the engine

- New `engine/auth.py`: `verify(token: str) -> dict | None` returning claims
  (`sub`, `email`, `exp`, `iss`, `aud`) or `None`. Fetch JWKS from
  `MTG_JWT_JWKS_URL`, cache keys in-process with a TTL (`MTG_JWT_JWKS_TTL`, default
  3600) and refetch once on an unknown `kid` — providers rotate keys. Enforce `exp`,
  `iss` (`MTG_JWT_ISSUER`), and `aud` (`MTG_JWT_AUDIENCE`) when set. Reject `alg:
  none` and reject any algorithm not on an explicit allowlist (`RS256`) — algorithm
  confusion is the classic JWT hole.
- **Dependency:** RS256 needs RSA and the Python stdlib has no RSA implementation, so
  this cannot be done stdlib-only. Add `PyJWT[crypto]` to the `engine/requirements.txt`
  that task 04 introduces, import it lazily inside `auth.py` so an API-key-only
  deployment never needs it, and amend CLAUDE.md gotcha 6 to record a **second**
  documented exception. The rejected alternatives, for the record: trusting a
  proxy-injected header (the API becomes unsafe if ever exposed directly) and calling
  the provider's session endpoint per request (latency plus a hard runtime dependency
  on their uptime).
- Rework the seam:
  - `_authed()` → `principal()` returning `{"kind": "user"|"key", "id": ..., "email": ...}`
    or `None`. Cache the result on the request object; it is consulted more than once.
  - `client_key` → `f"user:{sub}"` for users, `f"key:{prefix}"` for keys, `f"ip:{addr}"`
    for anonymous reads. **From verified claims only**, per honest note 2.
  - The gate at line 521 becomes a per-route requirement table
    (`simulate`, `decks`, `ask`, `coaching` → authenticated), so adding a route cannot
    forget the gate. `_deny(401, …)` copy stays as it is.
  - Generalise the bind refusal (lines 575–583): refuse when public and **neither**
    `API_KEYS` nor `MTG_JWT_ISSUER` is set. Keep the message's three options and add
    the issuer as a fourth.
- Add all `MTG_JWT_*` variables to `deploy/.env.example` and
  `deploy/docker-compose.yml`, and update the `mtg_engine.py` module docstring.

**Verify** — a hosted provider cannot be exercised without an account, and CLAUDE.md
forbids creating one. Test fully locally instead, which is also a better test:

```bash
# Generate a keypair, serve a static JWKS, mint tokens — no provider, no network.
openssl genrsa -out /tmp/jwt.pem 2048
python3 engine/tests/make_test_jwks.py /tmp/jwt.pem > /tmp/jwks.json   # you write this helper
python3 -m http.server 9999 --directory /tmp &
export MTG_JWT_JWKS_URL=http://127.0.0.1:9999/jwks.json \
       MTG_JWT_ISSUER=https://test.local MTG_JWT_AUDIENCE=simlab
python3 engine/tests/test_auth.py
```

`test_auth.py` must assert, at minimum: a valid token verifies and yields the right
`sub`; an expired token is rejected; a wrong-issuer token is rejected; a token signed
by a different key is rejected; `alg: none` is rejected; an `HS256` token whose
"secret" is the public key is rejected; an unknown `kid` triggers exactly one JWKS
refetch and then fails. Then:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8484/simulate \
  -H "Authorization: Bearer $VALID"   -d '{"decks":["a.dck","b.dck"],"games":1}'   # not 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8484/simulate \
  -H "Authorization: Bearer $EXPIRED" -d '{"decks":["a.dck","b.dck"],"games":1}'   # 401
env -u MTG_API_KEYS MTG_BIND=0.0.0.0 python3 engine/mtg_engine.py serve 8484       # exits
env -u MTG_API_KEYS MTG_BIND=0.0.0.0 MTG_JWT_ISSUER=https://test.local \
  python3 engine/mtg_engine.py serve 8484                                          # starts
```

## Stage 3 — quotas that mean something

- New `engine/quota.py`: `check(bucket: str, limit: int, window: float) -> tuple[bool, int]`
  — the exact signature `_rate_ok()` already has, so call sites do not change shape.
  In-process backend by default (move today's `_hits`/`_rate_lock` code there
  verbatim, comment intact); Redis backend when `MTG_REDIS_URL` is set, using
  `INCR` plus `EXPIRE` on a fixed window to match the current semantics rather than
  quietly changing them to a sliding window.
- Per-user limits replace per-key: `MTG_SIM_PER_HOUR` (6), `MTG_READ_PER_MIN` (240),
  deck import (30/hour, currently hardcoded at line 551 — promote it to
  `MTG_IMPORT_PER_HOUR`), plus `MTG_ASK_PER_HOUR` and `MTG_COACH_PER_HOUR` if tasks
  03 and 01 have landed. Anonymous reads keep the IP bucket.
- `MTG_SIM_MAX_QUEUED` is a **global** backpressure signal, not per-user — it protects
  the box. Leave it global and say so in a comment; the temptation to make everything
  per-user is how the queue gets oversubscribed.
- **Redis is a third dependency.** Same discipline: pin it, import it lazily, record
  it. If you would rather not, that is fine — ship the interface with the in-process
  backend only and leave the Redis implementation as a documented TODO. Then
  `deploy_plan.md` must keep the "exactly one API container" constraint, and the
  compose file must not gain a `deploy: replicas:` line.
- Surface the quota to the user: return `X-Quota-Remaining` on authenticated writes
  and show remaining sims this hour near the run button. A limit the user cannot see
  reads as a bug when they hit it.

**Verify:**

```bash
python3 engine/tests/test_quota.py     # same assertions pass on both backends;
                                       # skips cleanly with no MTG_REDIS_URL
# Two users must not share a bucket — this is honest note 2, proven:
for i in $(seq 1 7); do curl -s -o /dev/null -w '%{http_code} ' -X POST localhost:8484/simulate \
  -H "Authorization: Bearer $USER_A" -d '{"decks":["a.dck","b.dck"],"games":1}'; done   # 429 by the 7th
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8484/simulate \
  -H "Authorization: Bearer $USER_B" -d '{"decks":["a.dck","b.dck"],"games":1}'          # 200, not 429
```

Two replicas: document the measured doubling rather than pretending it away. With
`MTG_REDIS_URL` set, run two API processes on different ports against one Redis and
assert the 7th request is rejected regardless of which process serves it.

## Stage 4 — ownership

Needs task 04's Postgres.

- Tables, alongside `jobs`: `users (id text primary key, email text unique, created
  double precision, deleted double precision null)`, and ownership columns
  `owner_id` on `jobs` plus a `decks` table
  (`id, owner_id, slug, name, storage_key, created`). Keep unix floats for times, for
  the same reason task 04 does. Unique constraint on `(owner_id, slug)` — **not** on
  `slug` alone.
- Upsert the user row on first authenticated request from the verified claims. Do not
  build a separate registration endpoint; the provider owns signup.
- `POST /simulate` stamps `owner_id`. `_job_status()` and `/sim-status` return a job
  only to its owner (404, not 403 — do not confirm that someone else's job id
  exists). `_list_results()` filters to the caller's runs; anonymous callers see
  nothing, not everything.
- **Fix the deck bug from honest note 4, and prove it first.** Reproduce it: bring up
  `deploy/docker-compose.yml`, `POST /decks`, then `POST /simulate` with the new deck
  and watch the worker fail to find the file. Then fix it:
  - deck files move to `MTG_DATA_DIR/decks/{owner_id}/{slug}.dck` so the API and
    workers share them through the volume (or through task 05's blobstore, which is
    the better home);
  - `_list_decks()` (line 156) filters by owner;
  - the allowlist check at line 532 resolves against the caller's decks only, so a
    user cannot enqueue a simulation on someone else's deck by guessing a filename;
  - `POST /simulate` puts the resolved `deck_dir` in the job payload so
    `worker.py`'s fallback default is never used;
  - the built-in sample decks stay readable by everyone as a seeded, ownerless set —
    a signed-out visitor should still be able to see what a run looks like.

**Verify:**

```bash
# ownership isolation
curl -s -H "Authorization: Bearer $USER_A" localhost:8484/results | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
curl -s -H "Authorization: Bearer $USER_B" localhost:8484/results | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"   # 0
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $USER_B" \
  "localhost:8484/sim-status?id=$A_JOB_ID"       # 404
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8484/simulate \
  -H "Authorization: Bearer $USER_B" -d '{"decks":["'$A_DECK'","sample.dck"],"games":1}'   # 400 unknown decks
# slug collision no longer overwrites
for U in $USER_A $USER_B; do curl -s -X POST localhost:8484/decks -H "Authorization: Bearer $U" \
  -H 'Content-Type: application/json' -d '{"name":"Zombies","text":"..."}'; done
ls $MTG_DATA_DIR/decks/*/zombies.dck | wc -l     # 2
```

And the end-to-end proof that note 4 is fixed: in the compose topology, import a
deck and run a 1-game simulation on it to completion.

## Stage 5 — deletion, export, and the legal obligations

`deploy_plan.md`'s legal section becomes load-bearing here: open signup means you
hold email addresses and decklists. This is not legal advice; get a lawyer to
confirm before signup opens.

- `DELETE /account` (authenticated): delete the user's decks, jobs, and result
  objects, then tombstone the user row. Deleting the provider-side identity is the
  provider's API, not yours — call it, and record what you cannot delete.
- `GET /account/export`: the user's decks and run summaries as one JSON download.
- **Task 05 interaction:** if results are in a public bucket, ownership is
  cosmetic — filenames are timestamps (`sim_20260722_222841.json`) and trivially
  guessable. Before signup opens, either make the bucket private and serve through
  `presign_get()` (task 05 Stage 4 option 3, which exists for exactly this) or keep
  results proxied through the API where the ownership check runs. Pick one and write
  it down.
- Publish a privacy policy and terms of service; link them from `Footer` in
  `Chrome.tsx` beside the Fan Content notice. Cover what is stored (email,
  decklists, simulation results), the retention period, the deletion path, and any
  subprocessors (auth provider, host, object storage, LLM provider — note that
  question and deck text reach the model in tasks 01 and 03).
- Keep the Fan Content posture intact: unofficial, unaffiliated, no WotC trademarks
  in the name or domain, card images hotlinked from Scryfall and never rehosted.
  **Accounts are not a paid tier.** If a plan or price ever attaches to an account,
  CLAUDE.md is unambiguous: a lawyer reviews it first. The `Pro` badge in
  `Chrome.tsx` line 28 is mockup furniture — do not ship it as a real plan label.
- Tick `deploy_plan.md`'s "Per-user quotas (needs real accounts, Phase 2)" checkbox
  only when Stage 3 is honestly done, including the replica caveat.

**Verify:** create a test user, import a deck, run a 1-game sim, `GET
/account/export` and confirm both appear, then `DELETE /account` and confirm: the
deck file and result object are gone, `GET /results` with that token returns 401 or
an empty list, the DB row is tombstoned, and re-signing-in produces a fresh empty
account. Confirm the privacy policy and terms render and are linked from the footer.
Confirm a second user could never read the first user's results at any point — check
the object URL directly, not only the API.

---

## Acceptance criteria

- [ ] Provider chosen, compared, and justified in `deploy_plan.md`; current free-tier
      terms verified rather than assumed
- [ ] Sign-in works in `web/`; `/import` and run pages protected, `/` and `/rules` public
- [ ] `Authorization` header sent on **reads as well as writes**; `force-cache`
      removed or per-user keyed on owned routes
- [ ] `engine/auth.py` verifies RS256 with cached JWKS, enforces `exp`/`iss`/`aud`,
      allowlists algorithms, rejects `alg: none` and HS256-with-public-key
- [ ] `PyJWT[crypto]` (and Redis, if taken) pinned, imported lazily, recorded as
      documented exceptions in CLAUDE.md gotcha 6
- [ ] `client_key` is `user:{sub}` from **verified** claims — two users never share a
      rate-limit bucket, proven by the Stage 3 curl pair
- [ ] API keys still work alongside JWTs; per-route auth requirement table, not an
      inline route-name check
- [ ] Bind refusal generalised, not removed: still exits when public with neither keys
      nor an issuer; `MTG_ALLOW_OPEN_PUBLIC` still defaults to 0
- [ ] `engine/quota.py` interface with in-process default; Redis backend or a
      documented TODO plus the "one API container" constraint kept in the deploy docs
- [ ] `MTG_SIM_MAX_QUEUED` stays global, with a comment saying why
- [ ] Remaining quota surfaced to the user in the UI
- [ ] `users` table, `owner_id` on jobs, `decks` table with `(owner_id, slug)` unique
- [ ] Deck files under `MTG_DATA_DIR` (or the blobstore), per-user; the
      import-then-simulate path works in the compose topology; sample decks stay public
- [ ] Cross-user access returns 404 for jobs and 400 for unknown decks; `/results` is
      owner-scoped
- [ ] `DELETE /account` and `GET /account/export` implemented; deletion removes decks,
      jobs, and result objects
- [ ] Result objects are not publicly guessable once ownership exists (private bucket
      with presigned reads, or proxied through the ownership check)
- [ ] Privacy policy and terms published and linked in the footer; Fan Content notice
      retained; no paid tier introduced; the `Pro` badge is real or gone
- [ ] Account UI obeys Part 3: sentence case, one `.btn.pri` per view, `.st` dot+word,
      no new CSS file, no emoji
- [ ] `test_adapter.py` passes, `tsc` clean, `board.py` accuracy unregressed

## Out of scope

Teams, sharing, or public run links; roles and permissions beyond "owner"; OAuth
social providers beyond whatever the chosen provider gives for free; billing,
subscriptions, or any paid tier (needs legal review first — CLAUDE.md); SSO/SAML;
migrating existing local runs to a user (they are gitignored regenerable output);
email notifications when a sim finishes; a full audit log.
