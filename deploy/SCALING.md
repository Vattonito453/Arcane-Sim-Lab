# Scaling the sim fleet: costed options (2026-08-30)

The unit of work is ONE GAME: a stateless JVM, ~2 vCPU busy, 3-4 GB heap,
median ~5-6 min on fast cores (measured: 272-312 s median on dedicated
cores; 400-500 s on the current shared 2-vCPU VM), 900 s worst case, decks
and plans in, one JSONL out. Nothing about a game needs the machine that ran
the previous one, which makes this a textbook fan-out workload. "Install
Forge natively in GCP" IS containers: there is no managed Java-desktop
service, and the worker image (Forge + xvfb + shim) already runs anywhere
containers run.

Verified prices, us-central1, August 2026:
- Cloud Run: $0.000024 per vCPU-second, $0.0000025 per GiB-second
  (instance-based free tier: 240K vCPU-s + 450K GiB-s per month).
- e2-highcpu-4 (4 vCPU / 4 GB): $0.0989/hr on demand, $0.0594/hr spot
  (E2 spot is only ~40% off; N2D/C2D spot discounts run deeper and are worth
  a calculator pass before committing).
- Current VM (2 vCPU / 8 GB e2): ~$50/mo always-on plus disk.

## Cost per game, by option

| option | $/game | $/8-game sim | 8-game wall time | idle cost |
|---|---|---|---|---|
| A. today: 2-vCPU VM, sequential | ~$0.01 at full utilization (fiction: real utilization is a few %) | ~$0.08 | 45-60 min | $50/mo whether or not anyone sims |
| B. bigger VM (e2-highcpu-8 class) | same math, 4x throughput | ~$0.08 | ~12-18 min | ~$150-200/mo always-on |
| C. Cloud Run Jobs, per-game fan-out | ~$0.021 (720 vCPU-s x rate + memory) | ~$0.17 | **~6-8 min** (all games parallel) | **$0** (scale to zero) |
| D. Spot MIG fleet (e2-highcpu-4, 2 games/box) | ~$0.0033 | ~$0.03 | ~6-8 min when warm | ~$0 (autoscale to zero, minutes to warm) |

At scale, 1,000 sims/day (8,000 games):
- Cloud Run: ~$168/day (~$5.0K/mo)
- Spot fleet: ~$26/day (~$0.8K/mo), needs ~35-40 spot boxes at peak
- Today's VM: cannot do it at all (caps at ~170 games/day, one user at a time)

## Recommendation

**Phase 1 (now, cheap, biggest UX win): per-game fan-out on Cloud Run Jobs.**
The API enqueues one Cloud Run Job execution per game (Jobs natively run N
parallel tasks); each writes its JSONL to GCS; the engine's existing
merge/salvage machinery aggregates. An 8-game sim drops from 45-60 min to
~6-8 min, idle cost drops to zero, and the free tier alone covers ~300
games/month of testing. The current VM keeps serving web + API (it is fine
at that) and stops running sims.

**Phase 2 (when volume justifies ops): spot fleet for bulk.** Interactive
sims stay on Cloud Run (fast start, pay-per-use); batch/free-tier sims drain
through a spot MIG at ~6x cheaper. Preemption is already survivable: a killed
game is exactly the censored-game case the pipeline handles, and the job just
requeues.

**Do not** scale by replicating the API (rate limits are in-process,
per-container: CLAUDE.md) or by buying a bigger always-on VM (pays for idle,
still caps concurrency).

## The profitability frame

Ad-funded revenue is roughly single-digit dollars per thousand engaged
sessions. At Cloud Run rates a free user's 8-game sim costs ~$0.17 -- fine
for conversion, ruinous uncapped. The controls that keep unit economics sane:
- N free sims/day per user, queue beyond that (batch tier on spot at ~$0.03).
- 8 games default (the prediction plateau is ~12/deck; more is waste).
- The 900 s clock and 120-turn cap bound the worst-case game (already live).
- Lean fast-mode (~7% cheaper, fewer 900 s stalls) for the free tier.

## GPL note

All options run Forge server-side. GPL v3 imposes obligations on
DISTRIBUTION, not server-side use; containers in our project pulling the
official Forge release change nothing (CLAUDE.md legal posture). Publishing
the worker image to a public registry WOULD be distribution -- keep images in
Artifact Registry, private.

## What migration actually takes

1. Worker image already exists (deploy/Dockerfile.worker). Add a per-game
   entry mode: env vars for deck paths + plans + output GCS path (run_sim
   already supports --games 1).
2. Dispatcher: jobqueue gains a "cloud" backend that creates a Jobs
   execution with task-count = games and collects outputs from GCS.
3. Aggregator: reuse run_sim's rotation merge + salvage on the collected
   JSONLs (the multi-game scorer fixes from the QA pass already handle
   per-game files).
4. Keep the VM path as the fallback (`MTG_SIM_BACKEND=local`), because a
   playtester box with no cloud project must still work.

Costs in this doc are estimates from public list prices and measured game
timings; re-verify both before provisioning. Provisioning, accounts, and
budgets are Vincent's (deploy_plan.md Phase 0).
