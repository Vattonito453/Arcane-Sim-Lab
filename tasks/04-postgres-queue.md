# 04 — Postgres job queue

**Why:** SQLite needs working POSIX locks. On a network or 9p-style mount the queue
fails with `disk I/O error` — measured during testing, and documented twice
(CLAUDE.md gotcha 2, `deploy_plan.md` Phase 1). That constraint forces every worker
onto the same block volume as the API. Postgres removes the shared-lock requirement
and makes `claim()` safe across hosts.

**Dependencies:** none. **Task 06 depends on this** — per-user accounts and
run/deck ownership need a shared relational store, and this task is what puts one
in the topology.

**Read first:** `engine/jobqueue.py` (75 lines, the whole thing), plus its three
consumers: `engine/worker.py`, `_queued_count()` and `_job_status()` in
`engine/mtg_engine.py`.

**Size:** medium, and genuinely contained — four functions and one direct SQL query.

**Done means:** the shared definition of done in `tasks/README.md` applies in full,
plus the acceptance criteria below.

---

## Honest scope correction, read this before you start

`deploy_plan.md` Phase 2 says Postgres "is what unlocks workers on separate
machines". That is half true and the spec should not repeat it uncritically.
Simulation **results** are still written to the worker's own
`jobqueue.DATA_DIR / "sim_results"` (`worker.py` line 34) and read from the API's own
`RESULTS_DIR` (`mtg_engine.py` line 198). A worker on a different host will finish
a job the API can then never serve. **Postgres removes the queue's shared-filesystem
requirement; task 05 (object storage) removes the results'.** You need both for
multi-host. Fix the claim in `deploy_plan.md` as part of this task — CLAUDE.md's
working agreement says a measurement that contradicts a doc means the doc is wrong.

## Constraints

- **Same signatures.** `enqueue(payload) -> str`, `claim() -> dict | None`,
  `finish(job_id, result=None, error=None) -> None`, `get(job_id=None) -> dict | None`.
  `worker.py` and `mtg_engine.py` should need near-zero change beyond the two items
  named in Stage 1.
- **Module attributes are part of the interface too.** `worker.py` uses
  `jobqueue.DATA_DIR` (line 34, the `out=` argument) for the results directory and `jobqueue.DB_PATH`
  (line 48) in its startup log. `DATA_DIR` is a filesystem path and must survive
  unchanged — it has nothing to do with the DB. `DB_PATH` is SQLite-specific; keep it
  defined for the SQLite backend but stop `worker.py` from printing it
  unconditionally (print a backend description instead).
- **Both backends, one interface, selected by env.** `MTG_DB_URL` set → Postgres;
  absent → SQLite. This is a **new** environment variable; add it to
  `deploy/.env.example` and `deploy/docker-compose.yml`. Local development and
  `engine/tests/` must keep working with no Postgres installed and no config.
- **Same wire types.** `created`/`started`/`finished` are `time.time()` floats and
  `get()` returns `started` as a unix float that the front end consumes
  (`JobStatus.started` in `web/lib/types.ts`, elapsed maths in
  `web/app/runs/[id]/page.tsx`). Use `double precision`, **not** `timestamptz`, so
  no front-end change is required. `payload`/`result` stay `text` holding
  `json.dumps` output — not `jsonb` — so the round trip is byte-exact and key order
  is preserved.
- **The dependency exception.** CLAUDE.md gotcha 6 says the engine is stdlib-only by
  design. Adding `psycopg[binary]` is a **deliberate, argued exception** for this
  task: reimplementing the Postgres wire protocol is not a reasonable trade, and
  the alternative (talking to a Postgres HTTP proxy) adds a component instead of a
  library. Constraints on the exception:
  - Import `psycopg` **lazily inside the Postgres backend only**, so a SQLite-mode
    deployment never imports it and `python3 -c "import jobqueue"` works on a bare
    interpreter.
  - There is no `requirements.txt` and `deploy/Dockerfile.api` has no `pip` step
    today. Add `engine/requirements.txt` with the single pinned line and a
    `RUN pip install --no-cache-dir -r engine/requirements.txt` to
    `Dockerfile.api` and `Dockerfile.worker`.
  - Amend CLAUDE.md gotcha 6 in the same commit to read "stdlib only, with one
    documented exception: `psycopg` when `MTG_DB_URL` is set". Do not silently
    invalidate an invariant.

---

## Stage 1 — extract the interface, no behaviour change

SQLite only. This stage should be provably inert.

- Split `engine/jobqueue.py` into a dispatcher plus `engine/jobqueue_sqlite.py`
  holding today's code verbatim (or keep one module with two private backend
  classes — either is fine, one file per backend is easier to read). The public
  module keeps `DATA_DIR`, `enqueue`, `claim`, `finish`, `get`.
- Add `queued_count() -> int` returning
  `SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')`.
- Rewrite `_queued_count()` in `mtg_engine.py` (lines 168–178) to call it. Today it
  does `import sqlite3` and opens `jobqueue.DB_PATH` itself — that is the one place
  outside the module that knows the storage engine, and it must stop. **Keep the
  bare `except: return 0`**: the comment there ("never let a bookkeeping failure
  block a legitimate request") is deliberate and matters more once the DB is over a
  network.
- Replace `worker.py` line 48's `print(f"worker: polling {jobqueue.DB_PATH}")` with
  a backend-agnostic description, e.g. `jobqueue.describe()` returning
  `"sqlite:/data/jobs.db"` or `"postgres:<host>/<db>"` — **never** the full URL,
  which contains the password.

**Verify:**

```bash
python3 -c "import ast,glob;[ast.parse(open(f).read()) for f in glob.glob('engine/*.py')]"
python3 engine/tests/test_adapter.py                       # ALL ASSERTIONS PASSED
grep -n "sqlite3" engine/mtg_engine.py                     # no matches
MTG_DATA_DIR=/tmp/mtgq1 python3 -c "
import sys; sys.path.insert(0,'engine'); import jobqueue as q
i = q.enqueue({'decks':['a.dck','b.dck'],'games':2})
assert q.queued_count() == 1
j = q.claim(); assert j['id'] == i and q.claim() is None
q.finish(i, result={'summary':{'games':2}})
g = q.get(i); assert g['state'] == 'done' and q.queued_count() == 0
print('sqlite interface ok', q.describe())"
```

Then start the API with the embedded worker and run a real 1-game simulation
end-to-end to confirm `/sim-status` is unchanged.

## Stage 2 — the Postgres backend

`engine/jobqueue_postgres.py`, same four functions plus `queued_count` and
`describe`.

- Schema, mirroring `_SCHEMA` exactly:

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id text PRIMARY KEY,
  created double precision,
  state text,
  payload text,
  result text,
  error text,
  started double precision,
  finished double precision
);
CREATE INDEX IF NOT EXISTS jobs_queued ON jobs (created) WHERE state = 'queued';
```

  The partial index is the one addition worth making: `claim()` orders by `created`
  filtered on `state='queued'`, and that is the hot path every worker polls.
- **`claim()` must be one statement**, race-safe across hosts:

```sql
UPDATE jobs SET state = 'running', started = %s
WHERE id = (SELECT id FROM jobs WHERE state = 'queued'
            ORDER BY created LIMIT 1 FOR UPDATE SKIP LOCKED)
RETURNING id, payload;
```

  `SKIP LOCKED` is why two workers polling simultaneously each get a different job
  instead of one blocking or both taking the same one. Return `None` when the
  statement affects no rows — same contract as today's "lost a race" branch.
- Run schema creation once per process, not per call. Today `_conn()` executes
  `_SCHEMA` on every single call (`jobqueue.py` line 27); that is free on SQLite and
  wasteful over a network. Use a module-level connection or a small pool guarded by
  a lock, with `autocommit`, and reconnect on `psycopg.OperationalError` — a
  network DB drops connections and the worker loop must survive it.
- Backend selection lives in one place: `MTG_DB_URL` present → Postgres. Do not
  scatter `if os.environ.get(...)` through the call sites.

**Verify** — Postgres cannot be verified without a running server; the closest local
proxy is a throwaway container, which is free and offline after the image pull:

```bash
docker run -d --rm --name mtgpg -e POSTGRES_PASSWORD=x -p 5433:5432 postgres:16
export MTG_DB_URL="postgresql://postgres:x@127.0.0.1:5433/postgres"
# the exact same assertion block from Stage 1 must pass unchanged:
MTG_DATA_DIR=/tmp/mtgq2 python3 -c "...same script..."
psql "$MTG_DB_URL" -c "\d jobs"          # column types: double precision, text
docker stop mtgpg
```

Write that assertion block once as `engine/tests/test_jobqueue.py` and run it twice
— with and without `MTG_DB_URL`. **The same test file must pass on both backends**;
that is the actual deliverable of this stage. Skip cleanly with a printed message
when `MTG_DB_URL` is unset so a fresh clone with no Docker still passes.

## Stage 3 — prove the race safety

The claim above is unproven until it is contended.

- Add to `test_jobqueue.py`: enqueue 20 jobs, then have **8 concurrent claimers**
  loop until the queue is empty. Assert 20 distinct ids were claimed, zero
  duplicates, zero `None`-before-empty.
- Use **processes, not threads**, for the Postgres run — one connection per process
  is what a multi-host deployment actually looks like, and threads sharing one
  connection would not exercise `SKIP LOCKED`.
- Run the same test on SQLite. It should also pass (today's select-then-guarded-update
  is safe within one host); if it does not, that is a pre-existing bug you have just
  found, and the finding belongs in the commit message.

**Verify:**

```bash
python3 engine/tests/test_jobqueue.py --contended            # sqlite
MTG_DB_URL=... python3 engine/tests/test_jobqueue.py --contended   # postgres
# both print: 20 claimed, 20 distinct, 0 duplicates
```

## Stage 4 — migration and deployment config

- `python3 engine/jobqueue.py migrate` — reads the SQLite `jobs.db` at
  `DB_PATH` (or `--from <path>`) and inserts every row into Postgres with
  `ON CONFLICT (id) DO NOTHING`, so re-running is safe. Print counts read, inserted,
  skipped. Do not delete the source file.
- Running jobs are a migration hazard: a row in state `running` whose worker is gone
  will never finish. Report those counts separately and offer
  `--reset-running` to move them back to `queued`. Do not do it implicitly.
- `deploy/.env.example`: add `MTG_DB_URL` — commented out, with one line saying that
  leaving it unset keeps the SQLite queue and the shared-volume requirement.
- `deploy/docker-compose.yml`: pass `MTG_DB_URL: ${MTG_DB_URL:-}` to both `api` and
  `worker`. Update the `volumes:` comment at the bottom, which currently says the
  volume "must be a real filesystem with working POSIX locks — the job queue is
  SQLite"; qualify it with "unless `MTG_DB_URL` is set". Do **not** add a Postgres
  service to the compose file by default — the documented target is a managed
  instance (`deploy_plan.md` costs table: Supabase/Neon free tier), and bundling one
  invites running an unbacked-up database next to the app.
- Update `jobqueue.py`'s module docstring (currently "SQLite-backed job queue …
  Stdlib only") and the `deploy_plan.md` Phase 2 item 2 text.

**Verify:**

```bash
docker run -d --rm --name mtgpg -e POSTGRES_PASSWORD=x -p 5433:5432 postgres:16
MTG_DB_URL="postgresql://postgres:x@127.0.0.1:5433/postgres" \
  python3 engine/jobqueue.py migrate --from /tmp/mtgq1/jobs.db
# read == inserted on the first run; inserted == 0 and skipped == read on the second
MTG_DB_URL=... python3 -c "import sys;sys.path.insert(0,'engine');import jobqueue;print(jobqueue.queued_count())"
docker compose -f deploy/docker-compose.yml --env-file deploy/.env config   # renders, MTG_DB_URL present
```

---

## Acceptance criteria

- [ ] `enqueue`/`claim`/`finish`/`get` keep their exact signatures and return shapes
- [ ] `queued_count()` added; `mtg_engine.py` no longer imports `sqlite3` or touches `DB_PATH`
- [ ] `jobqueue.DATA_DIR` unchanged; `worker.py` logs a backend description with no credentials
- [ ] Backend chosen by `MTG_DB_URL` in exactly one place; unset → SQLite, no config, no Postgres needed
- [ ] `psycopg` imported lazily; `import jobqueue` works on a bare interpreter
- [ ] `engine/requirements.txt` added and installed in both Dockerfiles
- [ ] CLAUDE.md gotcha 6 amended to record the exception
- [ ] `claim()` on Postgres is a single `UPDATE … FOR UPDATE SKIP LOCKED … RETURNING`
- [ ] Timestamps are `double precision` unix floats; `payload`/`result` are `text`;
      no front-end change needed
- [ ] `engine/tests/test_jobqueue.py` passes on both backends and skips cleanly with
      no `MTG_DB_URL`
- [ ] Contended test: 20 jobs, 8 concurrent processes, 20 distinct claims, 0 duplicates
- [ ] `migrate` is idempotent, reports counts, never deletes the source
- [ ] `MTG_DB_URL` in `.env.example` and `docker-compose.yml`; compose comment and
      `deploy_plan.md` Phase 2 corrected to say Postgres alone does not enable
      multi-host workers (task 05 is the other half)
- [ ] `test_adapter.py` passes, `tsc` clean, `board.py` accuracy unregressed

## Out of scope

Retries, dead-letter handling, job cancellation, priorities, `LISTEN/NOTIFY`
push instead of polling, a connection pooler (pgBouncer), moving results off the
filesystem (task 05), the shared rate-limit store (task 06), and adding a Postgres
service to the default compose file.
