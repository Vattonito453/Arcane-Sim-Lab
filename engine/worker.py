#!/usr/bin/env python3
"""Simulation worker: claims jobs from the queue, runs Forge, stores results.

Standalone (Docker worker container / separate process):
    python3 worker.py

Embedded (started automatically by mtg_engine.py serve unless
MTG_EMBEDDED_WORKER=0): ensure_embedded() runs the same loop in a thread.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobqueue  # noqa: E402

_POLL_SECONDS = 3
_embedded_started = False

# ---- QA layer A (repair plan WS2 layer A task 1) ----------------------------
# After a job is FINISHED, engine/qa/run.py analyses its result in a detached,
# niced child with a 120 s watchdog, and writes
# $MTG_DATA_DIR/simkb/runs/<result_stem>/qa.json. It is launched only after
# jobqueue.finish, so it can never delay "finished", and nothing it does can
# raise into this loop. The idle loop's sweeper re-runs it for any finished
# run that has no qa.json (one child at a time, one launch per tick), which is
# what makes a lost or killed analysis recover on its own. MTG_QA=0 turns both
# off (an operator's escape hatch; preflight then fails the qa.json check).
QA_SCRIPT = Path(__file__).resolve().parent / "qa" / "run.py"
QA_TIMEOUT_SECONDS = 120.0
QA_NICE = 10
QA_SWEEP_SECONDS = 30.0
# A result modified this recently may still be being written: leave it to
# the next sweep.
QA_FRESH_SECONDS = 60.0
_qa_lock = threading.Lock()
_qa_children: dict[str, subprocess.Popen] = {}   # run stem -> child
_qa_gave_up: set[str] = set()
_last_sweep = 0.0


def qa_enabled() -> bool:
    return os.environ.get("MTG_QA", "1") != "0"


def _stem(result_file) -> str:
    name = Path(str(result_file)).name
    return name[:-5] if name.endswith(".json") else name


def _qa_watch(proc: subprocess.Popen, stem: str, timeout: float) -> None:
    """Reap the child; kill it at the timeout. Never raises (a daemon thread)."""
    try:
        try:
            rc = proc.wait(timeout=timeout)
            if rc not in (0, 1):
                print(f"worker: QA for {stem} exited {rc} without a qa.json "
                      f"(the sweeper retries it)", flush=True)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    import signal
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:  # noqa: BLE001 - already gone
                pass
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
            print(f"worker: QA for {stem} killed after {timeout:.0f} s "
                  f"(the sweeper retries it)", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"worker: QA watchdog for {stem}: {type(e).__name__}: {e}", flush=True)
    finally:
        with _qa_lock:
            if _qa_children.get(stem) is proc:
                del _qa_children[stem]


def launch_qa(result_file, *, timeout: float | None = None, reason: str = "finished",
              popen=None) -> subprocess.Popen | None:
    """Start QA for one result: detached, niced, watched. Returns the child,
    or None when QA is off or could not start. Never raises."""
    try:
        if not result_file or not qa_enabled():
            return None
        stem = _stem(result_file)
        timeout = QA_TIMEOUT_SECONDS if timeout is None else timeout
        cmd = [sys.executable, "-u", str(QA_SCRIPT), str(result_file),
               "--data-dir", str(jobqueue.DATA_DIR), "--nice", str(QA_NICE)]
        kw: dict = {"stdin": subprocess.DEVNULL, "close_fds": True}
        if os.name == "nt":
            kw["creationflags"] = (getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        else:
            kw["start_new_session"] = True   # its own group: the watchdog kills it whole
        proc = (popen or subprocess.Popen)(cmd, **kw)
        with _qa_lock:
            _qa_children[stem] = proc
        threading.Thread(target=_qa_watch, args=(proc, stem, timeout),
                         name=f"qa-watch-{stem}", daemon=True).start()
        print(f"worker: QA started for {stem} ({reason})", flush=True)
        return proc
    except Exception as e:  # noqa: BLE001 - QA must never take the worker down
        print(f"worker: QA not started for {result_file}: {type(e).__name__}: {e}", flush=True)
        return None


def _qa_busy() -> bool:
    with _qa_lock:
        return any(p.poll() is None for p in _qa_children.values())


def sweep_qa(now: float | None = None, *, results_dir: Path | None = None,
             data_dir: Path | None = None, launch=None) -> str | None:
    """One bounded sweep: start QA for at most one finished run that has no
    qa.json, newest first. Returns the run stem it started, else None.

    Skipped: a result modified in the last QA_FRESH_SECONDS (maybe still
    being written); a run whose last attempt started within the hook's
    timeout (maybe still running); a run already tried MAX_ATTEMPTS times
    (logged once). Nothing is started while any QA child is alive."""
    from qa import run as qa_run
    now = time.time() if now is None else now
    data_dir = Path(data_dir or jobqueue.DATA_DIR)
    results_dir = Path(results_dir or (data_dir / "sim_results"))
    if not results_dir.is_dir() or _qa_busy():
        return None
    try:
        files = [(f.stat().st_mtime, f) for f in results_dir.glob("sim_*.json")]
    except OSError:
        return None
    for mtime, f in sorted(files, reverse=True):
        if now - mtime < QA_FRESH_SECONDS:
            continue
        stem = _stem(f)
        if qa_run.qa_path(f.name, data_dir).is_file():
            continue
        att = qa_run.read_attempts(f.name, data_dir)
        tries = int(att.get("attempts") or 0)
        if tries >= qa_run.MAX_ATTEMPTS:
            if stem not in _qa_gave_up:
                _qa_gave_up.add(stem)
                print(f"worker: QA gave up on {stem} after {tries} attempts; "
                      f"run engine/qa/run.py on it by hand to see why", flush=True)
            continue
        started = att.get("last_started_epoch")
        if isinstance(started, (int, float)) and now - started < QA_TIMEOUT_SECONDS + 30:
            continue
        (launch or launch_qa)(f, reason="sweep")
        return stem
    return None


def idle_tick(now: float | None = None) -> None:
    """What the worker does between jobs. Never raises."""
    global _last_sweep
    now = time.time() if now is None else now
    if not qa_enabled() or now - _last_sweep < QA_SWEEP_SECONDS:
        return
    _last_sweep = now
    try:
        sweep_qa(now)
    except Exception as e:  # noqa: BLE001
        print(f"worker: QA sweep failed: {type(e).__name__}: {e}", flush=True)


def process_one(job: dict) -> None:
    from mtg_engine import Engine
    payload = job["payload"]
    qa_target = None   # the finished run's result file, analysed after finish()
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
            qa_target = res.get("result_file")
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
    if qa_target:
        # After finish() and outside the try: the job is already "done" and
        # nothing here can turn it into an error. launch_qa never raises.
        launch_qa(qa_target)


def _start_forge_index() -> None:
    """Build Forge's card index (forge_index.py) if it is missing, on a daemon
    thread. The import pre-check and the API read it from the shared volume;
    the worker is the only container with Forge, so it builds it. Never blocks
    the queue and never takes the worker down: at worst the index is missing
    and imports say their checks were skipped."""
    try:
        import forge_index
        forge_index.ensure_index_async(log=print)
    except Exception as e:  # noqa: BLE001
        print(f"worker: forge index not started: {type(e).__name__}: {e}")


def loop() -> None:
    print(f"worker: polling {jobqueue.DB_PATH}")
    _start_forge_index()
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
            idle_tick()
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
