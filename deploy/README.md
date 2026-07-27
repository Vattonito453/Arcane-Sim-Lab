# Deploying the MTG Engine

Step-1 deploy kit: API container + Forge worker container + shared volume, wired
through the SQLite job queue in `engine/jobqueue.py`. No terminal needed after launch.

## Architecture

```
browser → api (python, port 8484)          instant: /rule /search /decks /turn-structure
              │  enqueue → jobs.db (shared /data volume)
          worker(s) (java17 + forge) ── claim → simulate → write result → mark done
              └── /data/sim_results/*.json
```

The **same code runs locally without Docker**: `python3 engine/mtg_engine.py serve 8484`
starts the API with an embedded worker thread (uses your local Forge install). Docker
mode just sets `MTG_EMBEDDED_WORKER=0` on the API and runs workers separately.

## Run it

```bash
cd "MtG Rules Engine"
docker compose -f deploy/docker-compose.yml up --build
# dashboard: http://localhost:8484
# more sim throughput:
docker compose -f deploy/docker-compose.yml up --scale worker=3
```

The worker image downloads Forge 2.0.13 (~290MB) at build time. Workers want ~3GB RAM each.

## Hosting notes

- Any container host works (Fly.io, Railway, Render, a VPS, ECS). Deploy `api` publicly,
  `worker` privately, share the `/data` volume (or swap `jobqueue.py` for Redis/Postgres
  later — it's 80 lines and isolated on purpose).
- The API is plain HTTP; put TLS + auth in front (Caddy/nginx/host-provided) before
  exposing publicly, and rate-limit `POST /simulate` — sims are expensive.
- **Licensing:** Forge is GPL-3. It runs here as an unmodified separate process, which
  keeps your app's code independent. Don't link it into your codebase.
- Queue jobs survive restarts (SQLite on the volume). A job orphaned mid-run by a worker
  crash stays "running"; add a timeout-requeue if that matters at scale.

## API contract for the front end

| Call | Returns |
|---|---|
| `GET /decks` | available `.dck` files |
| `POST /simulate {"decks":[..2-4..],"games":N}` | `{job_id}` immediately |
| `GET /sim-status?id=<job_id>` | `queued/running/done/error` + summary when done |
| `GET /rule/<n>` `GET /search?q=` `GET /keyword/<k>` `GET /glossary/<t>` `GET /turn-structure` | rules KB (instant) |

Next steps when the front end lands: deck upload endpoint (accept a Moxfield export,
run `convert_decklist.py`, drop into /data/decks), result caching keyed on
deck-hash + gauntlet + games, and WebSocket/SSE progress instead of polling.
