# Getting Sim Lab online for playtesters

Goal: someone who is not on your LAN opens a URL and can browse decks, read runs,
scrub replays, and start a simulation.

Everything below is set up and verified except the parts that cost money or need
an account in your name — those are marked **you**. Nothing here was purchased,
signed up for, or exposed to the internet on your behalf.

---

## What "hosted" changes

Locally the browser and the engine are the same machine, so the front end's
default API base — `http://127.0.0.1:8484` — happens to work. Hosted, that string
resolves to *the visitor's own laptop*, and they see an engine-is-down page.

The fix is already in the repo: `web/next.config.mjs` proxies `/engine/*` to the
engine, so you set

```
NEXT_PUBLIC_API_BASE=/engine
```

and every API call goes through the app's own origin. One public hostname, no CORS
configuration, and no https-page-calling-http mixed content. Verified: the full
smoke test passes through the proxy (`--base http://localhost:3000/engine`, 23/23).

Two settings are **not** optional once anything is reachable from outside:

| Setting | Why |
|---|---|
| `MTG_API_KEYS=<random>` | `POST /simulate` spawns a 4 GB JVM. Without keys it is a free compute faucet, and the engine deliberately refuses to bind a public interface without them. Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ENGINE_ORIGIN` | Where the proxy forwards. Same host: leave it. Separate API box: `http://10.0.0.5:8484`. |

Playtesters need the key to start runs. Reads are public, so they can browse and
replay without one. There are no user accounts yet — one shared key is the whole
auth model (`tasks/06-accounts-and-quotas.md` replaces it).

---

## Option A — tunnel from your Mac (fastest; good for a weekend playtest)

No server, no deploy, no cost. Your Mac serves it; when you close the lid, it's
down. Right choice for "can four friends try this on Saturday".

**you** — install the tunnel client once:

```bash
brew install cloudflared
```

Then run the app in hosted mode and expose it:

```bash
cd "/Users/vincentattonito/Desktop/Personal/MtG Rules Engine"
MTG_BIND=127.0.0.1 MTG_API_KEYS="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))' | tee /tmp/simlab.key)" \
  python3 engine/mtg_engine.py serve 8484 &
cd web && NEXT_PUBLIC_API_BASE=/engine npm run build && NEXT_PUBLIC_API_BASE=/engine npm run start -p 3000 &
```

```bash
cloudflared tunnel --url http://localhost:3000
```

`cloudflared` prints a `https://<random>.trycloudflare.com` URL — that is what you
send people. The key is in `/tmp/simlab.key`; give it to whoever should be able to
start runs (they paste it under **change** next to "Engine" in the header).

Caveats, in order of how likely they are to bite:

- **A quick tunnel URL is public and unguessable, not private.** Reads need no
  key, so anyone with the link can browse your decks and replays. Fine for
  friends; don't post it.
- Every simulation runs on your Mac. Four people queuing 64-game gauntlets will
  saturate it — `MTG_SIM_MAX_QUEUED=3` and `MTG_SIM_PER_HOUR=6` already cap this.
- The URL changes every restart. A stable subdomain needs a Cloudflare account
  and a domain (**you**).

## Option B — a small VPS (persistent; the real deployment)

Use when you want a URL that survives closing your laptop. `deploy/` already has
the container kit and it is unchanged by this work; `deploy_plan.md` has the sizing
and cost analysis.

**you** — the account, the box, the DNS, the secrets. Then:

```bash
cp deploy/.env.example deploy/.env      # set MTG_API_KEYS; leave MTG_PORT on loopback
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up --build -d
```

That gets the engine and a Forge worker. The front end is a separate deploy — it
is a stock Next.js app, so either Vercel (**you**, free tier) with
`NEXT_PUBLIC_API_BASE=https://api.yourdomain` and `MTG_ALLOW_ORIGIN` set to the
Vercel origin, or `npm run build && npm run start` on the same box behind the same
reverse proxy, which keeps the single-origin `/engine` setup and is simpler.

Sizing, from measured behaviour rather than guesswork: a worker needs **>4 GB RAM**
(Forge runs `-Xmx4g`) and Forge is single-threaded per game, so 2 vCPU per worker.
A 2-deck 2-game run took 10 s and a 3-deck run 27 s on an M-series laptop; the
10–60 minute figure in the docs is for 64-game 4-deck gauntlets.

Two things to know before you scale:

- **Scale workers, not the API.** Rate limiting in `_rate_ok()` is in-process, so
  two API replicas double every quota (`tasks/04`, `tasks/06`).
- The job queue is SQLite and needs working POSIX locks. Keep the volume on a real
  filesystem — a network/9p mount fails with `disk I/O error`.

## Not an option: putting the engine straight on 0.0.0.0

The engine exits rather than bind a public interface with no `MTG_API_KEYS`, and
`MTG_ALLOW_OPEN_PUBLIC=1` exists only for a trusted private network. Leave both as
they are; terminate TLS in front instead.

---

## Verify a deployment before handing out the URL

Against the public URL, from anywhere:

```bash
python3 engine/tests/smoke_test.py --base https://your-url/engine --key "$SIMLAB_KEY"
```

29 checks with `--sim`, 23 without. It covers the rules KB, the deck list, result
payloads, `/cards`, path-traversal probes, and that `/simulate` rejects an empty
pod, an unknown deck, and an oversized game count. Then confirm by hand that an
unauthenticated write is refused:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://your-url/engine/simulate \
  -H 'Content-Type: application/json' -d '{"decks":["krenko_goblins.dck","torbran_burn.dck"],"games":1}'
```

`401` is the passing result. `200` means `MTG_API_KEYS` did not reach the process.

## Before it is public rather than link-shared

- `rules/raw/` and `rules/kb/` hold WotC Comprehensive Rules text. Fine in a
  private repo; strip them before the repo goes public.
- Keep the Fan Content notice in the footer (it is there), keep card images
  hotlinked from Scryfall (they are), and keep Forge a separate unmodified process.
- `web/components/Chrome.tsx` hardcodes `vincent` and a `Pro` badge, so every
  playtester sees your name in the header. Cosmetic, but odd — `tasks/06` covers it.
- A paid tier needs legal review first. Not a code question.
