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


def position(job_id: str) -> int:
    """How many queued jobs sit ahead of this one. 0 once it is claimed.

    claim() takes the oldest queued job, so "ahead" is simply the queued jobs
    created earlier. Lets the UI say "2 runs ahead" instead of showing an elapsed
    timer for a job that has not started.
    """
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE state='queued' AND created < "
            "(SELECT created FROM jobs WHERE id=?)", (job_id,)).fetchone()
    return int(row[0]) if row else 0


def get(job_id: str | None = None) -> dict | None:
    """Job by id, or the most recent job if id is None."""
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
