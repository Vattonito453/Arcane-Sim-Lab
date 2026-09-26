# Production check, 2026-09-26 (plan WS0 task 3)

Run with `deploy/checks/prod_check.sh` (read-only; scp'd and run over gcloud ssh). Raw output below.

## Findings

- **record_run completes in production.** Reproduced in the worker container (where the post-run hook runs) against copies of `/data/plan_feedback.json` and `/data/card_cache.json`: "COMPLETED", 15 decks, 3 recorded runs. The newest run was already recorded, so the call was a no-op (it is idempotent per run).
- **The "never completes" concern is refuted.** It rested on `richard/cache/plan_feedback.json`, which was not a production snapshot: it was written locally when deck plans were rebuilt with `MTG_DATA_DIR` pointed at a scratch cache (building a plan registers decks with 0 games). Provenance: local, 2026-09-26.
- **The combat-majority nudge has therefore been live** for decks past the 8-game threshold: Skrat's Revenge (26 games), Ur-Dragon B3 (26), Living Energy+ (15), Power Cosmic (15), Ant-Man (11). Every recorded win method is "combat damage / life loss", so any nudge fired in the combat direction. The `MTG_PLAN_FEEDBACK_APPLY` gate (default off) stops it at the R0 deploy.
- **Production shim:** 0.15.0, commit 220160b (worker image built 2026-09-07). R0 pins 0.16.0.
- **Preflight:** OK on every surface.
- **Imported decks with " // " names:** 0 of 15, so no production deck needs re-conversion for the DFC fix.
- **Worker env:** `MTG_DATA_DIR=/data`; `MTG_PLAN_FEEDBACK_APPLY` unset.
- The VM clone's commit could not be read by the ssh user (home directory permissions); not needed for this check.

## Raw output

```
## time and host
Sat Sep 26 16:36:20 UTC 2026
simlab.us-central1-a.c.arcane-sim-lab-v2.internal

## containers
deploy-web-1  Up 2 weeks  deploy-web
deploy-worker-1  Up 2 weeks  deploy-worker
deploy-api-1  Up 2 weeks (healthy)  deploy-api

## preflight (api container)
preflight against http://127.0.0.1:8484
probe run: sim_20260925_194533_9212fe0f3a11_rotated.json
probe deck: kess_reanimator_305b76d7.dck

SURFACES
  ok     rules KB                       rules=3152 keywords=262
  ok     deck index                     43 items
  ok     results index                  46 items
  ok     run summary                    keys present
  ok     deck display names             ['Kess, Reanimator', 'Power Cosmic', 'Talrand Control']
  ok     deck scorecards                4 decks, behaviour=True
  ok     playgroup prediction           available, 4 decks scored
  ok     replay events                  keys present
  ok     win-condition analysis         keys present
  ok     board reconstruction           keys present
  ok     deck telemetry                 keys present
  ok     card facts (Scryfall cache)    keys present
  ok     rules answer cache             reachable (ok=False reason=not generated)
  ok     coaching report cache          reachable (ok=False reason=not generated)

DELIBERATELY OFF (not failures)
  off    coaching generation (POST /coaching) MTG_LLM_API_KEY is unset. Turning it on spends money on a paid model key, which is the owner's call, not the agent's. Set it in deploy/.env to enable.
  off    rules assistant generation (POST /ask) Same MTG_LLM_API_KEY. Retrieval works and is live; only the generated answer is gated.
  off    embedded worker                MTG_EMBEDDED_WORKER=0 on purpose: workers are separate containers here so a 4 GB JVM cannot take the API down.

IMAGE CONTENTS
  ok        /app/engine/models/precon_predict.json     the fitted prediction model; a top-level COPY glob once missed it
  ok        /app/rules/kb                              the Comprehensive Rules KB the /ask retrieval reads
  ok        /app/engine/decks                          bundled decks

PREFLIGHT OK: every surface meant to be live is live.

## shim version and commit (worker container)
entrypoint: shim commit 220160b79a81653387b9566a11207b0bc8e127fb
total 64
drwxr-xr-x 1 root root  4096 Sep  7 23:20 .
drwxr-xr-x 1 root root  4096 Sep  7 23:20 ..
-rw-r--r-- 1 root root    41 Sep  7 23:20 COMMIT
-rw-r--r-- 1 root root 48322 Sep  7 23:20 simlab-forge-shim.jar
220160b79a81653387b9566a11207b0bc8e127fb

## repo on the VM

## environment of interest (worker)
MTG_DATA_DIR=/data

## plan_feedback.json summary
path /data/plan_feedback.json size 2824 mtime 2026-09-25 19:45:33 UTC
top-level keys: ['_runs', 'decks']
_runs present: True count: 3
decks: 15
  Ant-Man                                  games=11 wins=0 methods={}
  Atraxa Counters B3                       games=4 wins=1 methods={'combat damage / life loss': 1}
  Deadpool, Trading Card                   games=7 wins=0 methods={}
  Drana Vampires                           games=0 wins=0 methods={}
  Kambal Taxes B3                          games=0 wins=0 methods={}
  Kess, Reanimator                         games=0 wins=0 methods={}
  Kilo Helm Final                          games=0 wins=0 methods={}
  Krenko Goblins                           games=0 wins=0 methods={}
  Living Energy+                           games=15 wins=1 methods={'combat damage / life loss': 1}
  Nekusar Punisher B3                      games=0 wins=0 methods={}
  Power Cosmic                             games=15 wins=3 methods={'combat damage / life loss': 3}
  Skrat's Revenge                          games=26 wins=1 methods={'combat damage / life loss': 1}
  Stella Lee, Wild Card                    games=0 wins=0 methods={}
  Talrand Control                          games=0 wins=0 methods={}
  Ur-Dragon B3                             games=26 wins=20 methods={'combat damage / life loss': 20}
tags: 0 {}

## decks carrying ' // ' names
files with // : 0 of 15

## record_run reproduction in the worker container (against copies)
result files: 46
newest: /data/sim_results/sim_20260925_194533_9212fe0f3a11_rotated.json
plan_feedback module: /app/engine/plan_feedback.py
store path used: /tmp/pfcheck/plan_feedback.json
COMPLETED. decks now: 15 _runs: 3
sample: {'Ant-Man': 11, "Skrat's Revenge": 26, 'Ur-Dragon B3': 26, 'Deadpool, Trading Card': 7, 'Atraxa Counters B3': 4, 'Living Energy+': 15}

## done
```
