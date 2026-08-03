#!/usr/bin/env python3
"""SQLite-backed job queue for simulation jobs. Stdlib only.

Local mode: the API server runs an embedded worker thread (same process).
Deployed mode: API and worker are separate containers sharing MTG_DATA_DIR.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("MTG_DATA_DIR", Path(__file__).resolve().parent))
DB_PATH = DATA_DIR / "jobs.db"

_SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, created REAL, state TEXT,
    payload TEXT, result TEXT, error TEXT, started REAL, finished REAL)"""


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute(_SCHEMA)
    return c


def enqueue(payload: dict) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute("INSERT INTO jobs (id, created, state, payload) VALUES (?,?,?,?)",
                  (job_id, time.time(), "queued", json.dumps(payload)))
    return job_id


def claim() -> dict | None:
    """Atomically claim the oldest queued job. Returns job dict or None."""
    with _conn() as c:
        row = c.execute("SELECT id, payload FROM jobs WHERE state='queued' "
                        "ORDER BY created LIMIT 1").fetchone()
        if not row:
            return None
        updated = c.execute("UPDATE jobs SET state='running', started=? "
                            "WHERE id=? AND state='queued'", (time.time(), row[0])).rowcount
        if not updated:
            return None  # lost a race with another worker
    return {"id": row[0], "payload": json.loads(row[1])}


def finish(job_id: str, result: dict | None = None, error: str | None = None) -> None:
    with _conn() as c:
        c.execute("UPDATE jobs SET state=?, result=?, error=?, finished=? WHERE id=?",
                  ("done" if error is None else "error",
                   json.dumps(result) if result else None, error, time.time(), job_id))


def recover_orphans() -> int:
    """Requeue every job stuck in 'running' — call ONLY at worker startup.

    A container restart (redeploy, crash, VM reboot) kills the sim mid-run and
    nothing ever moves the job out of 'running': claim() only looks at
    'queued', so the run lingers forever and its UI page polls until the sun
    burns out. At worker startup any 'running' row is provably orphaned — this
    assumes ONE worker per queue, which is how every deployment runs today.
    If workers are ever scaled out, set MTG_RECOVER_ORPHANS=0 on all of them
    (a restarting worker would otherwise requeue its siblings' live jobs) and
    rely on reap_stale() instead.
    """
    if os.environ.get("MTG_RECOVER_ORPHANS", "1") == "0":
        return 0
    with _conn() as c:
        return c.execute("UPDATE jobs SET state='queued', started=NULL "
                         "WHERE state='running'").rowcount


def reap_stale(max_seconds: float | None = None) -> int:
    """Fail 'running' jobs older than the ceiling; returns how many.

    Backstop for a worker that died and never came back (recover_orphans only
    runs when a worker starts). Called from get(), so the same /sim-status
    poll a viewer's run page makes is what eventually turns a zombie into an
    honest error. The ceiling must exceed the worst legitimate sim — those are
    tens of minutes (SIM_CALIBRATION.md), and Engine.simulate kills the
    subprocess after MTG_SIM_TIMEOUT_SECONDS (2 h default) anyway.
    """
    if max_seconds is None:
        max_seconds = float(os.environ.get("MTG_JOB_TIMEOUT_SECONDS", 3 * 3600))
    now = time.time()
    with _conn() as c:
        return c.execute(
            "UPDATE jobs SET state='error', finished=?, error=? "
            "WHERE state='running' AND started < ?",
            (now, "the worker running this simulation was lost (restarted or "
                  "timed out) — start the run again", now - max_seconds)).rowcount


def position(job_id: str) -> int:
    """How many runs are ahead of this queued job. 0 once it is claimed.

    Two sources of "ahead": whatever is already 'running' (the worker has to
    finish that before it can claim anything else, regardless of when this
    job was created) and any older still-'queued' job (claim() takes the
    oldest queued job first). Missing the 'running' half of this used to
    make the very-next-in-line job report 0 whenever nothing else was
    queued, so the UI showed a bare "Queued" with no indication it was
    waiting on the job currently in flight.
    """
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE state='running' OR (state='queued' "
            "AND created < (SELECT created FROM jobs WHERE id=?))", (job_id,)).fetchone()
    return int(row[0]) if row else 0


def get(job_id: str | None = None) -> dict | None:
    """Job by id, or the most recent job if id is None."""
    reap_stale()  # status reads are frequent; zombies get reported honestly
    q = ("SELECT id, created, state, payload, result, error, started, finished FROM jobs "
         + ("WHERE id=?" if job_id else "ORDER BY created DESC LIMIT 1"))
    with _conn() as c:
        row = c.execute(q, (job_id,) if job_id else ()).fetchone()
    if not row:
        return None
    payload = json.loads(row[3] or "{}")
    out = {"id": row[0], "state": row[2], "decks": payload.get("decks"),
           "games": payload.get("games"), "started": row[6], "error": row[5],
           "result": json.loads(row[4]) if row[4] else None}
    if row[6]:
        out["elapsed"] = round((row[7] or time.time()) - row[6])
    return out
