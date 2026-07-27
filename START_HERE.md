# Handing this to Claude Code

## Do this first — one command

I initialized git but my sandbox couldn't finish the commit (it can't unlink files
git creates on this mount), so a stale lock is sitting there. Clear it and commit:

```bash
cd "/Users/vincentattonito/Desktop/Personal/MtG Rules Engine"
rm -f .git/index.lock
git add -A
git commit -m "Sim Lab: engine API, Next.js front end, deploy kit, agent handoff"
```

Verify the right things got excluded (should print nothing enormous, no `.env`,
no `node_modules`, no `engine/sim_results/`):

```bash
git ls-files | wc -l          # expect a few hundred, not thousands
du -ch $(git ls-files) | tail -1   # expect a few MB, not 500
```

If you'd rather start git from scratch: `rm -rf .git && git init` — `.gitignore`
is already written and verified against nine real paths.

**Why this matters:** without version control, an autonomous agent editing this
repo has no diff to review and no way to revert. Do it before pointing Claude Code
at anything.

## Then optionally delete the stale duplicate

`MtG Rules Engine/` (nested inside this folder) is a 2026-07-23 snapshot of the
whole project, missing `engine/cards.py` and `engine/board.py`. It's gitignored so
agents won't commit it, but it's still on disk and an agent could read or edit the
wrong copy.

```bash
rm -rf "MtG Rules Engine"     # only if you don't want it as a backup
```

## What to tell Claude Code

Point it at the repo and say:

> Read CLAUDE.md, then tasks/README.md. Work tasks/01-coaching-pipeline.md,
> one stage at a time, running the verification commands in the spec before
> claiming each stage is done.

That's it. `CLAUDE.md` carries the invariants (design rules, sim calibration,
legal posture, Forge's logging ceiling) and the verification loops. `tasks/` has
six specs with acceptance criteria, in dependency order.

## What NOT to delegate

- **Legal review.** The Fan Content Policy permits fan content but not
  commercialising WotC IP — a paid tier needs a lawyer *before* any code. Same for
  the Forge Java shim idea (`tasks/` deliberately excludes it): calling Forge's API
  from your own code is a different GPL posture than invoking an unmodified binary.
- **Spending money or creating accounts.** Vercel, Hetzner, Cloudflare, the LLM
  provider — `deploy_plan.md` Phase 0 is yours.
- **Production secrets.** Generate them yourself; `deploy/.env` is gitignored.

## Known-good state as of this handoff

| Check | Result |
|---|---|
| `engine/tests/test_adapter.py` | passes |
| `engine/board.py` on the fixture | 83.3% exit match (2-game fixture; 86.5% on a full 16-game run) |
| `web` TypeScript | `tsc --noEmit` clean |
| `web` production build | 6 routes, ~110 KB first load |
| Engine API routes | 8 routes, all 200; auth returns 401; quota returns 429 |
| Path traversal | blocked on results and decks, incl. null-byte and encoded forms |

## Bugs I found and fixed while preparing this

Worth knowing, because each was invisible until measured:

1. **API served requests serially** (`HTTPServer`, not threading) — 4 concurrent
   1-second requests took 4.04 s; now 1.02 s.
2. **Batched attackers were being dropped.** Forge writes
   `assigned A (1), B (2), C (3) to attack X` on one line and the parser kept only
   the last. Board exit-match went 76.3% → 86.5%.
3. **Rate-limit buckets collided.** `client_key` used the credential's first 12
   characters; every RS256 JWT from one issuer shares that prefix, so all
   authenticated users would have shared a single quota. Now a full hash.
4. **Imported decks were unreachable by the worker.** `POST /decks` wrote into the
   API container's image while the worker looked in its own copy — the deck passed
   validation, enqueued, then failed. Imports now go to `MTG_DATA_DIR/decks` (the
   shared volume) and jobs carry resolved paths. Slugs also got a content hash, so
   two people importing "Zombies" no longer overwrite each other.
5. **The test fixture lied.** Its summary claimed 16 games while carrying 2, so any
   per-game rate derived from it would be 8× off. Recomputed.

## Things still wrong that I did not fix

Documented in `tasks/` rather than patched, because they're task-sized:

- `_list_results()` parses all 31 result files (77 MB) to build the `GET /results`
  index. Fine locally; expensive on object storage. → `tasks/05`
- `web/lib/api.ts` `runSummary`/`runGame` use `cache: "force-cache"`, which becomes
  a cross-user leak once responses are per-user. → `tasks/06`
- `setApiKey()` is exported but no UI calls it, and `get<T>()` sends no
  `Authorization` header — the front-end auth "seam" is greenfield, not a swap. →
  `tasks/06`
- `components/Chrome.tsx` hardcodes `vincent` and a `Pro` badge. → `tasks/06`
- 31 MB of `forge_raw_*.log` in `engine/sim_results/` is served by nothing and read
  by nothing after adaptation. Safe to delete; `run_sim.py` keeps writing them.
