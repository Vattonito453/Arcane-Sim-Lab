#!/usr/bin/env python3
"""Simulation worker: claims jobs from the queue, runs Forge, stores results.

Standalone (Docker worker container / separate process):
    python3 worker.py

Embedded (started automatically by mtg_engine.py serve unless
MTG_EMBEDDED_WORKER=0): ensure_embedded() runs the same loop in a thread.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobqueue  # noqa: E402

_POLL_SECONDS = 3
_embedded_started = False


def process_one(job: dict) -> None:
    from mtg_engine import Engine
    payload = job["payload"]
    try:
        res = Engine().simulate(
            decks=payload["decks"],
            games=payload.get("games", 10),
            deck_dir=payload.get("deck_dir") or str(Path(__file__).parent / "decks"),
            fmt=payload.get("format", "Commander"),
            out=str(jobqueue.DATA_DIR / "sim_results"),
            run_id=job["id"],   # names the raw log so GET /sim-live can follow it
        )
        if res.get("returncode") == 0 and res.get("result"):
            jobqueue.finish(job["id"], result={
                "summary": res["result"]["summary"],
                "result_file": res.get("result_file"),
            })
        else:
            jobqueue.finish(job["id"], error=(res.get("stdout") or "simulation failed")[-800:])
    except Exception as e:  # noqa: BLE001
        jobqueue.finish(job["id"], error=str(e))


def loop() -> None:
    print(f"worker: polling {jobqueue.DB_PATH}")
    while True:
        job = jobqueue.claim()
        if job:
            print(f"worker: running job {job['id']} {job['payload'].get('decks')}")
            process_one(job)
            print(f"worker: finished job {job['id']}")
        else:
            time.sleep(_POLL_SECONDS)


def ensure_embedded() -> None:
    """Start one in-process worker thread (local/laptop mode)."""
    global _embedded_started
    if _embedded_started or os.environ.get("MTG_EMBEDDED_WORKER", "1") == "0":
        return
    _embedded_started = True
    threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    loop()
