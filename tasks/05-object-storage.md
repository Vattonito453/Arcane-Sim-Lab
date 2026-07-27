# 05 — Results in object storage

**Why:** result files are immutable, large, and currently pinned to the app host's
disk. Moving them to S3-compatible storage takes the biggest disk and bandwidth cost
off the sim box and is the other half of running workers on separate machines (see
task 04). **R2 is the recommended target: no egress fee** (`deploy_plan.md` costs
table), and an immutable 2.6 MB JSON served from a CDN is exactly what R2 is for.

**Dependencies:** none required. Pairs with **04** for real multi-host operation —
Postgres frees the queue from a shared volume, this frees the results. Sequenced
before **06**: see the bucket-privacy note in Stage 4, which changes once runs are
user-owned.

**Read first:** in `engine/mtg_engine.py` — `RESULTS_DIR` (line 198),
`_list_results()` (240), `_read_result()` (257), `_read_result_summary()` (276),
`_read_result_game()` (298), and the `/results` routing block (479–497). Also
`engine/worker.py` `process_one()` and `engine/run_sim.py`'s `--out` handling.

**Size:** medium.

**Done means:** the shared definition of done in `tasks/README.md` applies in full,
plus the acceptance criteria below.

---

## Measured facts (re-measured for this spec; use these)

`engine/sim_results/` — gitignored, regenerable:

| | |
|---|---|
| `sim_*.json` result files | **31** |
| Total result bytes | **80.6 MB** |
| Mean / median / max | **2.60 MB / 2.93 MB / 5.73 MB** |
| Seat-rotated runs | 18 of 31 |
| `forge_raw_*.log` also in the directory | **~27 MB** |
| Directory total | **108 MB** |

The 108 MB figure quoted in CLAUDE.md and `deploy_plan.md` is the whole directory.
**Results proper are 80.6 MB; the rest is raw Forge stdout** written by
`run_sim.py` (lines 119 and 172) and never served by any endpoint. Correct those two
docs while you are here, and do not migrate the logs — see Stage 4.

## Constraints

- **Local filesystem must keep working with zero configuration.** A fresh clone,
  `engine/tests/`, and laptop development all run with no bucket. Object storage is
  opt-in via env.
- **The path-traversal guard survives.** `_read_result()` line 264 is the single
  choke point: `if name != Path(name).name or not name.endswith(".json"): raise
  ValueError("bad result filename")`. Object keys make this *more* important, not
  less — an unvalidated name becomes an arbitrary key prefix, and S3 happily accepts
  `..` as a literal path segment. Validate the bare filename first, then build the
  key as `PREFIX + name` with no other user input anywhere in it.
- **Immutable stays immutable.** The API already sends
  `Cache-Control: public, max-age=31536000, immutable` on result responses
  (`mtg_engine.py` line 483). When objects are uploaded, set the same value as object
  metadata so a CDN or a redirect target serves it too — otherwise the header
  silently disappears the moment you stop proxying bytes.
- **Snapshots still work.** `_read_result(name, snapshots=True)` calls
  `board.annotate(data, fetch=False)` in-process. That is CPU on the API host and is
  unaffected by where the bytes came from — but it means `?snapshots=1` can never be
  a redirect. Keep that path proxied.
- **Stdlib preference.** See the Stage 3 dependency argument.

---

## Stage 1 — `engine/blobstore.py`, local backend only

Introduce the abstraction and route every existing read through it. **No behaviour
change** — this stage is a refactor you can prove is inert.

- Interface, deliberately small:

```python
list_objects(prefix: str) -> list[dict]      # {"key", "bytes", "modified"} — modified is a unix int
get_bytes(key: str) -> bytes                 # raises FileNotFoundError, same as today
put_bytes(key, data, *, content_type, cache_control) -> None
exists(key) -> bool
delete(key) -> None
presign_get(key, ttl_seconds) -> str | None  # None on the local backend
describe() -> str                            # "local:/data/sim_results" — never a credential
```

- Local backend is `RESULTS_DIR` with the key used as the filename. `list_objects`
  is the existing `glob` + `stat`.
- Rewrite `_list_results`, `_read_result`, `_read_result_summary`,
  `_read_result_game` to go through it. `_read_result_summary` and
  `_read_result_game` already build on `_read_result` — keep that, so only one
  function touches storage.
- `RESULTS_DIR` stays as the local backend's root; do not delete it.

**Verify** — capture every result response before and after and diff:

```bash
# before the refactor
MTG_DATA_DIR=$PWD/engine MTG_API_KEYS=k1 MTG_EMBEDDED_WORKER=0 python3 -u engine/mtg_engine.py serve 8484 &
F=$(curl -s localhost:8484/results | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['file'])")
for p in "/results" "/results/$F" "/results/$F/summary" "/results/$F/game/1" "/board/$F"; do
  curl -s "localhost:8484$p" > /tmp/before$(echo $p | tr / _).json; done
# …refactor, restart, repeat into /tmp/after_*, then:
for f in /tmp/before_*; do diff -q "$f" "${f/before/after}" || echo "DRIFT: $f"; done
```

Zero drift, plus:

```bash
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8484/results/..%2F..%2Fetc%2Fpasswd"   # not 200
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8484/results/notes.txt"                 # not 200
```

## Stage 2 — the index must not read every object

This is the real design problem and the reason to do this task properly.

`_list_results()` **parses every result file in full** to extract `meta.decks`,
`len(games)`, and `summary` — 80.6 MB of reads for one `GET /results`. On the local
disk with a page cache that is merely wasteful. On object storage it becomes **31
network GETs of ~2.6 MB each per index request**, which is unacceptable and will
also bill you for it.

- At write time, emit a sidecar next to each result: `{name}.summary.json` holding
  exactly what the index needs — `{file, bytes, modified, decks, games, summary}` —
  plus the payload `_read_result_summary()` returns (the per-game rows). One object,
  a few KB.
- `_list_results()` reads sidecars only: `list_objects()` for the index, then one
  `get_bytes()` per sidecar. `_read_result_summary()` serves the sidecar directly and
  falls back to reading the full result when the sidecar is missing (older runs).
- Backfill command: `python3 engine/blobstore.py backfill` writes sidecars for every
  existing result. Idempotent; skip when present unless `--force`.
- Keep `_list_results`'s per-file `except` that reports `{"error": "unreadable: …"}`
  in the index. Surfacing a bad file beats hiding it, and that comment says so.

**Verify:**

```bash
python3 engine/blobstore.py backfill
ls engine/sim_results/*.summary.json | wc -l        # 31
python3 - <<'PY'
import time, urllib.request
t = time.time(); urllib.request.urlopen("http://127.0.0.1:8484/results").read()
print("GET /results %.0f ms" % ((time.time()-t)*1000))
PY
```

Record the before and after milliseconds in the commit message — that number is the
justification for the sidecar and belongs in `deploy_plan.md`. Then assert the
sidecar-derived index is identical to the full-read index:

```bash
# with sidecars present vs. --force-full, the JSON must match
diff <(curl -s localhost:8484/results) <(curl -s "localhost:8484/results?full=1")
```

(Add `?full=1` as a debug-only switch for exactly this comparison, or compare
against the Stage-1 captures — either is acceptable, but prove equality.)

## Stage 3 — the S3/R2 backend

- Selected by env, one place only. New variables, all to be added to
  `deploy/.env.example` and `deploy/docker-compose.yml` (api and worker):
  - `MTG_S3_BUCKET` — **presence selects the S3 backend**; absent → local
  - `MTG_S3_ENDPOINT` — e.g. `https://<account>.r2.cloudflarestorage.com`
  - `MTG_S3_REGION` — `auto` for R2
  - `MTG_S3_ACCESS_KEY_ID`, `MTG_S3_SECRET_ACCESS_KEY`
  - `MTG_S3_PREFIX` — default `sim_results/`
  - `MTG_S3_PUBLIC_BASE` — optional CDN/custom-domain base for Stage 4 redirects
- **Implement SigV4 with the stdlib** (`hashlib`, `hmac`, `urllib.request`,
  `datetime`). The argument: only four operations are needed (GET, PUT,
  `ListObjectsV2`, presign), R2 speaks SigV4, presigning is pure computation, and
  this preserves CLAUDE.md gotcha 6 without a second dependency exception. Cost is
  roughly 150 lines that need real tests. If you reject this and take `boto3`
  instead, that is a defensible call — but argue it in the commit message and amend
  CLAUDE.md gotcha 6, the same discipline task 04 uses for `psycopg`. Do not add a
  dependency silently.
- `ListObjectsV2` returns XML; parse with `xml.etree.ElementTree` and **handle
  pagination** (`IsTruncated` / `NextContinuationToken`). 31 objects fit in one page
  today; 1,000 is the default cap and this will exceed it.
- Retry idempotent GET/LIST twice with backoff on 5xx and on `URLError`. A network
  read failure must surface as a 500 from the endpoint, not a stack trace, and a
  missing key must still raise `FileNotFoundError` so the existing 404 branch
  (line 494) keeps working.
- `describe()` returns bucket and prefix, never the secret.

**Verify** — this cannot be fully verified without live credentials. Two honest local
proxies, do both:

1. **Signature correctness against AWS's published SigV4 test suite.** The
   `aws-sig-v4-test-suite` vectors give canonical request, string-to-sign, and
   signature for fixed inputs. Assert your signer reproduces them byte-for-byte in
   `engine/tests/test_blobstore.py`. This is the part that silently fails against a
   real bucket with an opaque `403 SignatureDoesNotMatch`, so test it offline.
2. **Round-trip against MinIO**, which is S3-compatible and free:

```bash
docker run -d --rm --name minio -p 9000:9000 minio/minio server /data
export MTG_S3_ENDPOINT=http://127.0.0.1:9000 MTG_S3_BUCKET=mtg \
       MTG_S3_REGION=us-east-1 MTG_S3_ACCESS_KEY_ID=minioadmin \
       MTG_S3_SECRET_ACCESS_KEY=minioadmin
python3 engine/tests/test_blobstore.py           # put/get/list/exists/delete round trip
python3 engine/blobstore.py backfill             # uploads 31 results + sidecars
curl -s localhost:8484/results | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"   # 31
diff <(curl -s "localhost:8484/results/$F/summary") /tmp/before_results_${F}_summary.json
docker stop minio
```

State plainly in the commit message that R2 itself is unverified until Vincent
supplies credentials (CLAUDE.md: do not create hosting accounts or generate
production secrets), and that MinIO plus the SigV4 vectors is the closest local
proxy.

## Stage 4 — the write path, and how bytes reach the browser

**Uploads.** `worker.py` `process_one()` gets the adapted result path back from
`Engine().simulate()` as `res["result_file"]`. After a successful run: write the
sidecar, `put_bytes()` both objects with `content_type="application/json"` and
`cache_control="public, max-age=31536000, immutable"`, and only then
`jobqueue.finish()`. Order matters — a job marked done whose object is not yet
readable produces a 404 on the results page the user was just watching.

- Keep or delete the local copy behind `MTG_S3_KEEP_LOCAL` (default keep). Deleting
  is the point of the task, but the first deployment should not be the first time
  you find out the upload path is wrong.
- **Do not migrate `forge_raw_*.log`.** They are debug artifacts, ~27 MB, served by
  nothing. Leave them local. If you want them off the box, that is a separate
  decision with its own retention policy — say so in `deploy_plan.md` rather than
  quietly uploading 27 MB of Forge stdout.

**Reads.** Three options; the honest ranking is not what the brief's phrasing
suggests:

1. **Proxy through the API (keep today's behaviour).** Correct for
   `/results/{file}/summary` and `/results/{file}/game/{n}` — they are *derived*
   payloads (930 B and ~15 KB), not stored objects, so there is nothing to redirect
   to. These are the endpoints the front end actually uses
   (CLAUDE.md gotcha 4; `web/lib/api.ts` `runSummary`/`runGame`). **Leave them
   proxied.**
2. **302 redirect to `MTG_S3_PUBLIC_BASE + key`** for the full-run route
   `/results/{file}`. This is where the multi-megabyte transfer is, and a public
   custom domain with the `Cache-Control` metadata set at upload time is CDN-cacheable
   — which a presigned URL is not, because the signature varies per request.
   Requirements: the bucket's CORS config must allow the front-end origin, because
   `api.result()` follows the redirect from the browser; and `?snapshots=1` must stay
   proxied (the annotation happens in-process).
3. **Presigned URL.** Needed only when the bucket must stay private. **It must stay
   private after task 06** — once runs are owned by a user, a public bucket leaks
   every user's results to anyone who can guess a filename, and the filenames are
   timestamps. So: implement `presign_get()` now, ship option 2 for the current
   single-tenant beta, and leave a comment naming task 06 as the trigger to switch.
   Add `MTG_S3_REDIRECT=0|1` so the choice is config, not a rebuild.

Given the front end almost never fetches whole runs, the redirect is a **smaller win
than Stage 2's sidecar index**. Ship it, but do not let it hold up the task.

**Verify:**

```bash
# with MTG_S3_REDIRECT=1 against MinIO:
curl -si "localhost:8484/results/$F" | head -5           # 302 + Location
curl -si "$(curl -si "localhost:8484/results/$F" | awk '/^[Ll]ocation:/{print $2}' | tr -d '\r')" \
  | grep -i cache-control                                # immutable header on the object
curl -si "localhost:8484/results/$F?snapshots=1" | head -1   # 200, still proxied
# with MTG_S3_REDIRECT=0: 200 and a JSON body, byte-identical to Stage 1's capture
```

Then run one real simulation end-to-end with the S3 backend on and confirm the run
appears in `GET /results`, its summary loads, and the replay plays — the full loop,
not just the endpoint.

---

## Acceptance criteria

- [ ] `engine/blobstore.py` with the six-function interface; storage touched in one place
- [ ] Local backend is the default and needs no configuration; a fresh clone works
- [ ] All four result endpoints plus `/board/{file}` go through the abstraction, with
      byte-identical responses to the pre-refactor captures
- [ ] Path-traversal guard intact and applied before key construction; traversal and
      non-`.json` names still rejected
- [ ] `GET /results` reads sidecars, not whole results; before/after latency recorded
- [ ] `backfill` writes sidecars and uploads existing results; idempotent
- [ ] SigV4 signer verified against the published AWS test vectors
- [ ] MinIO round trip passes: put, get, list with pagination handling, exists, delete
- [ ] `Cache-Control: public, max-age=31536000, immutable` set as object metadata at
      upload, not only as a proxied response header
- [ ] Worker uploads result + sidecar **before** `jobqueue.finish()`
- [ ] `forge_raw_*.log` are not uploaded; the decision is documented
- [ ] `MTG_S3_*` variables in `.env.example` and `docker-compose.yml`; no secret ever
      printed by `describe()` or a log line
- [ ] `MTG_S3_REDIRECT` switches redirect vs. proxy; `?snapshots=1` always proxied
- [ ] `presign_get()` implemented, with a comment naming task 06 as the trigger to
      make the bucket private
- [ ] Any dependency added is argued in the commit message and recorded in CLAUDE.md
- [ ] CLAUDE.md and `deploy_plan.md` corrected: 31 results, 80.6 MB, mean 2.60 MB,
      max 5.73 MB, and the 108 MB figure attributed to the directory including logs
- [ ] `test_adapter.py` passes, `tsc` clean, `board.py` accuracy unregressed

## Out of scope

Moving the Scryfall card cache (`engine/cards.py`, `card_cache.json`) — it is small,
mutable, and shared with workers by design; migrating raw Forge logs; lifecycle or
retention policies; multi-region replication; signed cookies; result deletion in the
UI (that arrives with account deletion in task 06); compressing objects at rest —
the API already gzips responses and double-compression buys nothing.
