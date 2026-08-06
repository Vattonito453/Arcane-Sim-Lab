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
        result = res.get("result") or {}
        summary = result.get("summary") or {}
        meta = result.get("meta") or {}
        if result and summary.get("games", 0) > 0:
            # Played vs expected, checked here rather than assumed (audit A5).
            # "rc==0 and games>0" accepted one surviving game out of sixteen as
            # a finished job, so a rotation that OOM'd produced a run that
            # looked complete and was quietly a quarter of the requested size.
            expected = meta.get("games_expected") or meta.get("games_requested")
            played = summary.get("games", 0)
            short = bool(expected) and played < expected
            # NOT `payload`: that name already holds the job's request in
            # this scope, and shadowing it here is how a later edit reads the
            # wrong decks.
            done = {"summary": summary, "result_file": res.get("result_file")}
            if short or meta.get("incomplete"):
                done_rot = meta.get("rotations_completed")
                total_rot = meta.get("rotations")
                done["incomplete"] = True
                done["warning"] = (
                    f"played {played} of {expected} games"
                    + (f" ({done_rot} of {total_rot} seat rotations completed)"
                       if done_rot is not None and total_rot else "")
                    + (". The run was cut short, so these numbers are a partial "
                       "sample and the seat rotation did not finish balancing."
                       if not res.get("killed") else
                       ". The run hit its time ceiling and was stopped; the "
                       "games that finished were recovered."))
                print(f"worker: job {job['id']} incomplete: {done['warning']}")
            jobqueue.finish(job["id"], result=done)
        elif res.get("returncode") == 0 and res.get("result"):
            # Forge exited 0 but played nothing — a silent failure (bad deck,
            # missing display, dead shim). "Done, 0 games" looked like nothing
            # happened; say what we know instead.
            jobqueue.finish(job["id"], error=(
                "the simulation produced no games — Forge started but played "
                "nothing. Engine output:\n" + (res.get("stdout") or "")[-700:]))
        else:
            jobqueue.finish(job["id"], error=(res.get("stdout") or "simulation failed")[-800:])
    except Exception as e:  # noqa: BLE001
        jobqueue.finish(job["id"], error=str(e))


def loop() -> None:
    print(f"worker: polling {jobqueue.DB_PATH}")
    # A restart mid-sim (redeploy, crash) leaves the job 'running' forever —
    # nothing else ever touches that state. We are the only worker on this
    # queue, so anything 'running' right now is provably dead: requeue it and
    # the sim simply runs again.
    recovered = jobqueue.recover_orphans()
    if recovered:
        print(f"worker: requeued {recovered} orphaned job(s) from a previous worker")
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
