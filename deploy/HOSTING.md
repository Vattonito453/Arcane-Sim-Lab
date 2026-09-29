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
smoke test passes through the proxy (`--base http://localhost:3000/engine`);
it prints its own total, and every check must pass.

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
containers before this was written: **every smoke check passes against the
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

### Confirming which shim the worker carries

The `--build` in that command is load-bearing for the agent: the shim is built
from its own repo inside the worker image. Before 2026-08-02 the clone sat
behind a cached layer that never invalidated, so shim commits pushed after the
first build silently never shipped — the VM ran a Stage-3 agent while the shim
was on Stage 5. An `ADD` of the shim ref's GitHub commits API now busts that
layer whenever the ref moves (verified: the response is byte-stable per commit,
so builds are not repeated needlessly, and differs across commits, so a new
shim commit does invalidate).

Verify after any deploy that touches the agent — one line, no jar archaeology:

```bash
sudo docker logs deploy-worker-1 2>&1 | grep 'shim commit'
git -C /path/to/simlab-forge-shim ls-remote origin v0.17.0   # the pinned tag; should match
```

For an annotated tag, `ls-remote` prints two lines; the commit is the one
ending `^{}`. For v0.17.0 it is shim commit `33243d5` (the squash merge of
simlab-forge-shim PR #15, whose tree is identical to `b8894e1`, the commit
the G0a gate tested). The previous pin, v0.16.0, is `62fe295`.

If it prints `vendor-staged`, a jar from `deploy/sync-shim.sh` is being used and
the clone was skipped — fine locally, wrong on the VM. Delete
`deploy/vendor/simlab-forge-shim.jar` and rebuild.

### Releases pin a shim tag

Production no longer builds whatever the shim's `main` happens to be. The
worker's `SIMLAB_SHIM_REF` build arg comes from `docker-compose.yml`, which
defaults it to the current release tag (**`v0.17.0`**, the repair plan's R1
pin: the tutoring hotfix, read by version-2 plans, which compose also defaults
to since R1), and `deploy/.env` may override either for a test build or a
rollback (`MTG_PLAN_VERSION=1` plays as 0.16.0 did).

- **Pin a tag, never a bare commit.** `Dockerfile.worker` clones with
  `git clone -b "$SIMLAB_SHIM_REF"`, which accepts a branch or a tag only. A
  branch moves under you, so a release pins a tag.
- **The tag must exist before the build.** The ref is fetched from the GitHub
  API before the clone, so a missing tag fails the worker build outright; the
  containers already running keep serving. Each release tags the shim first,
  in the `simlab-forge-shim` repo (R0 tagged `v0.16.0` on `62fe295` like this;
  R1's `v0.17.0` on `33243d5` already exists):

  ```bash
  git -C /path/to/simlab-forge-shim tag -a v0.16.0 62fe295 -m "Sim Lab release pin (R0)"
  git -C /path/to/simlab-forge-shim push origin v0.16.0
  ```

  A tag also names the exact shim source the image was built from. Running
  the image on our own server imposes no GPL duty; if it is ever
  distributed, that source must be public at that commit (CLAUDE.md legal
  posture), and a pushed tag makes the commit easy to point at.
- **Bumping the pin** is one commit in this repo, after the new tag exists:
  the `SIMLAB_SHIM_REF` default for the worker and its mirror on the api in
  `docker-compose.yml`, and `SHIM_FLOOR` in `deploy/preflight.py`.
- `preflight.py` asserts the pin: it fails while the newest finished result
  was piloted by an older shim than the pin (read from the result's
  `meta.agent`, `simlab-forge-shim/X.Y.Z`). It also asserts
  `MTG_PLAN_FEEDBACK_APPLY` is off. See the post-deploy order below.

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

every check, including a real containerized Forge run. Then confirm the write
guard from outside: an unkeyed `POST /engine/simulate` must return 401.

### Post-deploy order: deploy, smoke test, then preflight

After every deploy, in this order:

1. **Deploy** (`redeploy.sh`, or the compose build above).
2. **`smoke_test.py --sim`** (the command above). Its 2-game sim runs on the
   worker that was just built, so it becomes the newest finished result.
3. **Preflight**, inside the api container:

   ```bash
   sudo docker exec deploy-api-1 python3 /app/deploy/preflight.py --files
   ```

   And the image half in the worker container, which serves no API:

   ```bash
   sudo docker exec deploy-worker-1 python3 /app/deploy/preflight.py --image-only
   ```

The order matters. Preflight's shim check reads the newest finished result,
and a run that finished before the deploy still carries the old shim's
version, so preflight fails on it until a new sim finishes. That failure
after a fresh deploy means "run the smoke test first", not a broken deploy;
the failure message says so.

**The qa.json race, and how it is closed (R1.1).** `preflight.py --files`
also fails unless the newest finished run has a `qa.json` with no errors
(QA layer A, below). The worker writes that file in a detached child
*after* the job is marked finished, so the smoke test's run is "done" a
moment before its `qa.json` exists. Two things close the gap, and neither
needs you to wait by hand: `smoke_test.py --sim` itself waits (up to
`--qa-timeout`, 180 s) for its new run's `qa.json` and fails if it never
comes, and preflight's check polls for up to `--qa-wait` seconds (150 by
default) before failing. On the dev box the file was there before the smoke
test asked (0 s), so after the documented order the wait is normally zero.

### QA layer A: a qa.json for every run (R1.1)

Every finished run gets `/data/simkb/runs/<result stem>/qa.json`: knockouts
and the biggest board swing per game, each deck's tutor figures, the pilot,
what Forge refused to load, the board accuracy, and flags (for example
`tutor.unreachable`: a tutor cast for a piece its search cannot find). It is
written by `engine/qa/run.py`, which the worker starts right after each job
is finished: at lowered priority, detached, and killed if it runs past
120 s, so it can never delay a run or fail one. While idle, the worker's
sweeper re-runs it every 30 s for one finished run that has no `qa.json`
(newest first), so a lost or killed analysis recovers on its own, and a
fresh deploy backfills older runs over the next few minutes. A run whose
analysis is killed three times is left alone and logged once
("QA gave up on ..."). Flags at medium severity and above are also filed
in `/data/simkb/review_queue/auto/`, at most 30 per run, spread across
detectors.

- Read it: `GET /engine/results/<file>/qa` (public, no human notes; 404
  `{"qa": "pending"}` until written). The review queue, human flags first:
  `GET /engine/qa/queue?since=<cursor>` with a **reviewer key** from
  `MTG_REVIEW_KEYS` in the api's environment. An API key gets 403, on
  purpose: `WEB_API_KEY` is one of `MTG_API_KEYS` and is inlined into the
  served JavaScript, so every visitor holds it, and the queue holds
  playtesters' own words. A flag key gets 403 too, and a reviewer key writes
  nothing. Generate one like a flag key (`secrets.token_urlsafe(24)`), put it
  in `deploy/.env` as `MTG_REVIEW_KEYS=<key>` (never also in `MTG_API_KEYS`
  or `MTG_FLAG_KEYS`: such a key is dropped), and recreate the api container.
  Unset, nobody reads the queue over HTTP and preflight lists it as
  deliberately off. On plain HTTP the key crosses the network in clear, so
  read the queue through an SSH tunnel to the api's loopback port
  (`gcloud compute ssh simlab --zone=us-central1-a -- -L 8484:127.0.0.1:8484`,
  then `http://127.0.0.1:8484/qa/queue`) until TLS is in front. Treat what it
  returns as private.
- Backfill or rerun by hand, from either container:
  `sudo docker exec deploy-worker-1 python3 -u /app/engine/qa/run.py --all`
  (skips runs whose `qa.json` is current; `--force` redoes all), or one run:
  `... run.py <result file name>`. It prints the traceback of any detector
  that failed; the same lands in `docker compose logs worker`.
- Time budget: `python3 -u /app/engine/qa/budget.py --corpus` in the worker
  container measures it on the VM (target: p95 under 10 s).
- `MTG_QA=0` in `deploy/.env` (compose passes it to the worker) turns the
  hook and the sweeper off. Preflight then fails its qa.json check, on
  purpose.
- `MTG_QA_QUEUE_MIN_SEVERITY` (`low` | `medium` | `high`, default `medium`),
  also in `deploy/.env`, sets what reaches the review queue.

The address to hand out is `http://EXTERNAL_IP/` (find it with
`gcloud compute instances describe simlab --zone=us-central1-a --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`).

### Giving a playtester a flag key

"Flag this moment" in the replay lets a playtester mark a play that looks
wrong and say why. The flag is written to `/data/simkb/review_queue/human/`
on the data volume; nothing serves it back publicly, and you triage the queue
(decision 11 in `tasks/README.md`: 30 minutes a week). To send one, the tester
needs a **flags-only key**. It can flag moments and nothing else: the engine
refuses it on `/simulate`, `/decks` and every other write with a 403, so it
cannot start a 4 GB sim. Generating and handing out the key is **you**; an
agent never creates a real one.

1. Generate a key (any machine with Python):

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(24))"
   ```

2. On the VM, add it to `deploy/.env` under a label that names the tester:

   ```
   MTG_FLAG_KEYS=richard:<the generated key>
   ```

   More testers are comma-separated, one key each so any one can be revoked
   alone: `richard:<key1>,vincent:<key2>`. The label is recorded as the flag's
   reporter; it may use letters, digits, `.`, `_` and `-` (up to 40), and the
   key may not contain `,` or `:` (`token_urlsafe` never does). **Never** put
   a tester's key in `MTG_API_KEYS` or `WEB_API_KEY`: those can start sims.

3. Recreate the api container so it reads the new value. No image rebuild is
   needed; the key is read at start, not baked in:

   ```bash
   cd ~/simlab/deploy && docker compose --env-file .env up -d api
   ```

4. Check it. Preflight should print `ok  playtester flag keys` (it reads the
   same `.env` through compose); a malformed entry fails it and says so. Then
   `smoke_test.py --flag-key <key>` with a flags key labelled for **yourself**
   (not the tester's), because that check writes one real flag, "smoke test:
   safe to delete", under the key's label.

5. Send the key to the tester privately (a direct message, not a group
   thread or an issue). What to tell them: open any replay, press **Flag this
   moment**, and paste the key into **Flag key** once. Their browser remembers
   it (that browser only) and sends it only with flags.

6. To revoke, delete that entry from `MTG_FLAG_KEYS` and recreate the api
   container again. Their saved key then gets "That flag key was not
   recognised."

Each key may send `MTG_FLAG_PER_HOUR` flags an hour (60 by default). To read
the queue:

```bash
sudo docker exec deploy-api-1 ls -1t /data/simkb/review_queue/human/
sudo docker exec deploy-api-1 cat /data/simkb/review_queue/human/<id>.json
```

Each file holds the run, the game, the anchor (event index, turn, round and
seat), the flagged log line, the note, the reporter and a UTC timestamp. The
notes are the tester's own words: private data that never goes into this
repo (decision 9 puts human data in the private data repo). The nightly
reviewer reads the same queue over HTTP, human flags first:
`GET /engine/qa/queue?since=<cursor>` with a reviewer key from
`MTG_REVIEW_KEYS` (never an API key or a flag key, which get 403; see
"QA layer A" above).

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
tracking with `git checkout main`. Either way, finish with the post-deploy
order above: `smoke_test.py --sim`, then preflight.

Two constraints inherited from the engine (see CLAUDE.md): scale **workers**,
not the api — rate limits are in-process, so two api replicas double every
quota. And the data volume must stay a real filesystem (the job queue is
SQLite); the named docker volume on the VM's boot disk is exactly that.

**Game-story switches (R1).** What the results page and the replay say about
how each game went is set by two api-container variables, applied
server-side in the payloads (`engine/game_story.py`), so the week-3 hand
audit of the knockout and turning-point readings can be applied without a
code change:

| Variable | Values | Default |
|---|---|---|
| `MTG_TURNING_POINT` | `swing`: labelled "Biggest board swing" (audit not passed); `audited`: labelled "Turning point"; `off`: not shown (held) | `swing` |
| `MTG_KNOCKOUT_DETAIL` | `on`: each knockout's cause and killer shown; `off`: who went out, and when, only | `on` |

The week-3 audit has reported (`studies/knockout_audit/RESULTS.md`), and
both defaults are its result, so R1 sets neither variable. Knockouts passed
(39 of 40 against the 38 required), so cause and killer ship
(`MTG_KNOCKOUT_DETAIL=on`). The turning point failed (8 of 20 against the 16
required), so it ships named for what it measures, "Biggest board swing"
(the largest rise in the winner's share of creature power;
`MTG_TURNING_POINT=swing`), with two rules that apply whatever the switch
says: it is held on stdout runs (their board is inferred, and there it
agreed in 1 of 8 games), and it is withheld when the winner's raw share did
not rise on the turn picked. `audited` stays off-limits until a refined
analyzer passes a re-audit on a fresh draw. The fixes made after the audit
(those two rules, and the knockout card's attribution) are listed under
"Fixes after the audit" in the same file and are not re-audited.

Set them in `deploy/.env`, then `docker compose --env-file .env up -d api`
(no rebuild; compose passes both through). Browsers pick the change up
within 5 minutes (the summary and game payloads are `max-age=300`).
`/health` reports the values in force under `story`, and preflight prints
them under GAME STORY SWITCHES. They govern the game story only (the
results page's game rows and the replay). The run page's "How games ended"
counts and the scorecards' "how it won" read the same knockout analyzer and
are not switched, so a failed knockout audit needs more than
`MTG_KNOCKOUT_DETAIL=off` to take its causes off the page.

**After deploying R1, backfill commander names** into existing results (the
results page, index and replay read them; old runs otherwise fall back to a
live read of each deck file, which fails once a deck is deleted):
`sudo docker exec deploy-api-1 python3 /app/engine/readapt.py --check --all`,
then `--write --all`. It keeps each file's mtime, only adds decks meta does
not name yet, and skips decks whose file is gone. It also leaves the original
beside each result as `<name>.bak` (measured locally on five results: only
`meta.commanders` differs once parsed; the rewrite is compact JSON, so an
indented original also shrinks). Nothing reads the `.bak` files; once the
pages look right, they can be removed to get the disk back.

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

Every check must pass (the count moves as checks are added, so none is quoted
here). It covers the rules KB, the deck list, result payloads, `/cards`,
path-traversal probes, and that `/simulate` rejects an empty pod, an unknown
deck, and an oversized game count. Then confirm by hand that an
unauthenticated write is refused:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://your-url/engine/simulate \
  -H 'Content-Type: application/json' -d '{"decks":["krenko_goblins.dck","torbran_burn.dck"],"games":1}'
```

`401` is the passing result. `200` means `MTG_API_KEYS` did not reach the process.

Once `MTG_FLAG_KEYS` is set, add `--flag-key <your own flags key>` to the
smoke test: it proves the key can flag and is refused (403) by `/simulate`
and `/decks`, and it writes one flag noted "smoke test: safe to delete".

## Before it is public rather than link-shared

- `rules/raw/` and `rules/kb/` hold WotC Comprehensive Rules text. Fine in a
  private repo; strip them before the repo goes public.
- Keep the Fan Content notice in the footer (it is there), keep card images
  hotlinked from Scryfall (they are), and keep Forge a separate unmodified process.
- `web/components/Chrome.tsx` hardcodes `vincent` and a `Pro` badge, so every
  playtester sees your name in the header. Cosmetic, but odd — `tasks/06` covers it.
- A paid tier needs legal review first. Not a code question.
