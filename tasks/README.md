# Task specs

One file per independently shippable unit. Each spec states what to build, which
files to touch, what "done" means, and how to prove it. Read `../CLAUDE.md` first —
its invariants bind every task here.

**Work one spec at a time and finish it.** Each is sized to be completable and
verifiable on its own; none requires a later one to be useful.

## Order

Dependencies are the only reason to prefer one order over another. Within a tier,
pick by what you care about most.

```
Tier 1 — product value, no infra dependencies
  01-coaching-pipeline.md      the flagship feature; the product is a sim viewer without it
  02-telemetry-ui.md           deck_telemetry.py has no UI; small and high-value
  03-rules-assistant.md        retrieval already exists; needs generation + cache

Tier 2 — needed for multi-host scale (do when Tier 1 saturates one box)
  04-postgres-queue.md         unlocks workers on separate machines
  05-object-storage.md         moves 2.6 MB result files off the app host

Tier 3 — needed for open signup
  06-accounts-and-quotas.md    replaces shared API keys with per-user identity
```

## What is already done

Don't rebuild these. See `deploy_plan.md` for the measurements.

- Threaded API, gzip, per-game payload endpoints, immutable cache headers
- API-key auth, per-caller quotas, queue backpressure, input validation,
  path-traversal guards
- Scryfall card cache (`engine/cards.py`) and board reconstruction
  (`engine/board.py`, 86.5% exit match — see CLAUDE.md for the ceiling)
- Front end: home, import, run progress, run results, replay theater
- Docker compose with env config, healthcheck, `.env.example`

## What is deliberately NOT here

- **Playable game client.** Out of scope permanently; see `CLAUDE.md` legal.
- **Patching or linking Forge.** Same.
- **Paid tier.** Needs legal review before any code.
- **Board snapshots via Forge's Java API.** Blocked on GPL review, not on effort.

## Definition of done, for every task

1. The acceptance criteria in the spec are met.
2. The verification commands in the spec pass, and you ran them.
3. `python3 engine/tests/test_adapter.py` still passes; `cd web && npx tsc --noEmit`
   is clean.
4. `python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch`
   shows no regression in `exit_match_rate`.
5. Any number you changed in a doc is re-measured and updated in the same commit.
6. New UI obeys `mockups/design_principles.md` Part 3 — audit your own diff for
   ALL-CAPS labels, pills, a second `.btn.pri`, emoji, and new CSS files.
