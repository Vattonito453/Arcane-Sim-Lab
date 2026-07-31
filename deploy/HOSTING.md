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
| `ENGINE_ORIGIN` | Where the proxy forwards — a BUILD-time value (`next build` bakes it into the routes manifest). The compose file passes `http://api:8484`. |
| `NEXT_PUBLIC_API_KEY` | The same key, baked into the front end at build time so playtesters can start runs without pasting anything. |

That third one matters more than it looks. There is **no UI for entering an API
key** — the "change" link next to "Engine" sets the base URL only, and nothing
calls `setApiKey()`. So the key has to come from the build, or the *Run
simulation* button fails with a 401 for everyone including you. Reads are public,
so browsing and replaying work regardless.

`NEXT_PUBLIC_*` is inlined into the client bundle, so anyone who can open the site
can read that key out of it. For a trusted group behind an unguessable URL that is
an acceptable trade — it is a shared group key, not a per-user secret, and the
`MTG_SIM_PER_HOUR` / `MTG_SIM_MAX_QUEUED` caps still bound the damage. Real
per-user identity is `tasks/06-accounts-and-quotas.md`.

---

## The deployment: one GCP VM running docker compose

Three containers — `web` (Next.js, the public face), `api` (the engine), and
`worker` (Java 17 + Forge, runs the sims) — sharing one data volume. The web
container proxies `/engine/*` to the api over the compose network, so the only
thing exposed to the internet is the web port. Verified end to end in
containers before this was written: **35/35 smoke checks pass against the
containerized stack**, including a real 2-game Forge simulation executed by the
worker container in 15 s, and the front end renders 29 decks through the
proxy.

### What containerizing Forge actually required

Two failures that only appear in a container, both found and fixed here — worth
knowing because each looks like "the worker is doing nothing":

1. **Forge needs a display even in `sim` mode.** It ships one desktop jar for
   GUI and simulation, and `forge.GuiDesktop`'s static initializer calls
   `getDefaultScreenDevice()` before sim mode is reached. Headless that throws
   `java.awt.HeadlessException`; with `-Djava.awt.headless=false` it fails on a
   missing `libXext.so.6`. The worker image therefore installs `xvfb` plus the
   X11/font libraries and starts a virtual display before the worker runs.
2. **The failure is silent.** Forge registers a Sentry handler that swallows the
   exception and exits 1 with *no output at all* — no stack trace, no log file,
   an empty raw log in the volume. Setting `-Dsentry.dsn=` is what surfaced the
   real error. If a containerized worker ever "finishes" a sim in a few seconds
   with zero games, run Forge by hand inside the container with Sentry disabled.

Also: `xvfb-run` does **not** work as a container entrypoint. It starts Xvfb in
a subshell and waits for a SIGUSR1 readiness signal, and that handshake never
completes as PID 1 — measured here: Xvfb came up, the wait never returned, and
the worker it was supposed to launch never started. `deploy/worker-entrypoint.sh`
starts the server directly and polls for its socket instead.

Both container images also run Python with `-u`. Without it, stdout to a pipe is
block-buffered and `docker compose logs` stays empty until 8 KB accumulates,
which is what disguised the Forge failure above as an idle container.

### Sizing, from measured behaviour

Forge runs with `-Xmx4g` and its JVM peaks near 5 GB resident. Games are
single-threaded; game count parallelises across workers, one game does not.

| Machine | RAM | Fits | Running (us-central1, on demand) |
|---|---|---|---|
| e2-standard-2 | 8 GB | web + api + **1 worker** | ~$0.067/hr → ~$49/mo if never stopped |
| e2-standard-4 | 16 GB | web + api + **2 workers** | ~$0.134/hr → ~$98/mo if never stopped |

**Billing is per hour in the RUNNING state, not per simulation.** An idle VM
costs the same as a busy one — there is no usage metering here, unlike a
serverless product. So the only lever is stopping it:

```bash
gcloud compute instances stop simlab --zone=us-central1-a     # ~$4/mo, disk only
gcloud compute instances start simlab --zone=us-central1-a    # back in ~30 s
```

Data survives on the boot disk and the containers come back by themselves
(`restart: unless-stopped`). A stopped instance bills only that disk: ~$4/mo for
40 GB pd-balanced, or ~$1.60/mo if created with `--boot-disk-type=pd-standard`.

Realistic pattern — 10 hours of playtesting a week: 43 hrs x $0.067 = ~$2.90
compute + ~$4 disk = **~$7/mo**, comfortably inside the $300 trial credit. Start
with e2-standard-2. Figures are list prices; confirm on the GCP calculator.

### Steps only you can do (accounts and money)

1. A GCP project with billing, and the `gcloud` CLI authenticated locally.
2. Create the VM and open the web port:

```bash
gcloud compute instances create simlab   --zone=us-central1-a --machine-type=e2-standard-2   --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud   --boot-disk-size=40GB --tags=simlab-web
```

```bash
gcloud compute firewall-rules create simlab-web   --allow=tcp:80 --target-tags=simlab-web --description="Sim Lab playtest"
```

3. Get the repo onto the VM. Since 2026-07-31 it lives at
   `github.com/Vattonito453/Arcane-Sim-Lab` (private) and the VM has a
   **read-only deploy key** (`~/.ssh/github_deploy`), so clone it:

```bash
git clone git@github.com:Vattonito453/Arcane-Sim-Lab.git ~/simlab
```

The tarball route this replaced (kept for reference, e.g. bootstrapping a VM
before a deploy key exists — `COPYFILE_DISABLE=1` is mandatory or AppleDouble
`._*` sidecars ship and break `GET /decks`, which is how the first deploy died):

```bash
cd "/Users/vincentattonito/Desktop/Personal" && COPYFILE_DISABLE=1 tar czf /tmp/simlab.tgz --exclude='MtG Rules Engine/web/node_modules'   --exclude='MtG Rules Engine/web/.next*' --exclude='MtG Rules Engine/engine/sim_results'   --exclude='MtG Rules Engine/.git' --exclude='MtG Rules Engine/deploy/.env' --exclude='*.zip' "MtG Rules Engine" && gcloud compute scp /tmp/simlab.tgz simlab:~ --zone=us-central1-a
```

### Steps on the VM (`gcloud compute ssh simlab --zone=us-central1-a`)

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 && sudo usermod -aG docker $USER && newgrp docker
```

```bash
tar xzf simlab.tgz && cd "MtG Rules Engine/deploy" && cp .env.example .env
```

Edit `.env`: set `MTG_API_KEYS` to a generated secret
(`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`), set
`WEB_API_KEY` to the same value, leave `WEB_PORT=80`. Then:

```bash
docker compose --env-file .env up -d --build
```

First build takes several minutes: the worker image downloads Forge (~290 MB)
and the web image compiles the front end. **Build on the VM, not on the Mac** —
this laptop produces arm64 images and an e2 instance is x86_64.

`COPYFILE_DISABLE=1` is not optional on macOS. Without it, tar emits AppleDouble
`._name` sidecars for every file carrying an extended attribute; they extract as
real files on Linux, match `engine/decks/*.dck`, and being binary they made
`GET /decks` return a 500 for the entire deck list on the first deploy. The
engine now skips `._*` and reads deck files with `errors="replace"`, so a single
odd file can no longer take the endpoint down — but shipping the sidecars at all
is still wrong.

### Verify before sending the link

From the VM (or anywhere, using the external IP):

```bash
python3 engine/tests/smoke_test.py --sim --base http://localhost/engine --key "$YOUR_KEY"
```

35 checks including a real containerized Forge run. Then confirm the write
guard from outside: an unkeyed `POST /engine/simulate` must return 401.

The address to hand out is `http://EXTERNAL_IP/` (find it with
`gcloud compute instances describe simlab --zone=us-central1-a --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`).

### Plain HTTP, and when to fix that

This runbook serves HTTP on port 80: fine for a playtest link shared with
friends, not for anything beyond that. The upgrade path is a domain + Caddy in
front of the web container (automatic Let's Encrypt), moving `WEB_PORT` off 80.
Do that before collecting anything resembling accounts (tasks/06).

### Operating it

```bash
docker compose --env-file .env logs -f worker    # watch sims execute
docker compose --env-file .env up -d --scale worker=2   # e2-standard-4 only
docker system prune -f                                   # reclaim old image layers
```

**Deploying changes** — commit, push to GitHub, then one command (deploys only
what is on `origin/main`, so nothing uncommitted can reach the VM):

```bash
gcloud compute ssh simlab --zone=us-central1-a --command='~/simlab/deploy/redeploy.sh web'
```

`redeploy.sh` with no argument rebuilds the whole stack (needed when
engine/worker code changes, not just `web/`). Rollback: on the VM,
`git -C ~/simlab checkout <commit>` then re-run the compose build; return to
tracking with `git checkout main`.

Two constraints inherited from the engine (see CLAUDE.md): scale **workers**,
not the api — rate limits are in-process, so two api replicas double every
quota. And the data volume must stay a real filesystem (the job queue is
SQLite); the named docker volume on the VM's boot disk is exactly that.

### The tunnel option, retired

An earlier version of this doc led with a Cloudflare quick tunnel from the Mac.
It worked, but corporate networks commonly blackhole `*.trycloudflare.com` (the
Mac it ran on could not even resolve its own tunnel), the link died whenever
the laptop slept, and every sim ran on the laptop. `Share for Playtest.command`
still exists for a quick demo from a home network; the VM is the real answer.

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
