#!/usr/bin/env python3
"""The worker's QA hook and idle-loop sweeper (repair plan WS2 layer A task 1).

After a job is finished, worker.process_one launches engine/qa/run.py as a
detached, niced child with a 120 s watchdog; it never raises into the worker
and never delays "finished". The idle loop's sweeper re-runs QA for any
finished run with no qa.json, one child at a time. These checks pin:

  * ordering: jobqueue.finish runs BEFORE the QA launch, the launch gets the
    result file, and an errored job (or a finish that raised) launches none;
  * launch_qa never raises: a Popen that fails, QA switched off (MTG_QA=0),
    no result file; it returns at once while the child keeps running;
  * the watchdog kills a child that outlives its timeout and forgets it;
  * a real launch writes the run's qa.json;
  * the sweeper: newest first, skips a run with a qa.json, a result still
    being written, a run whose attempt may still be running, a run tried
    MAX_ATTEMPTS times (logged once), and starts nothing while a QA child is
    alive; idle_tick sweeps at most every QA_SWEEP_SECONDS and never raises.

A throwaway MTG_DATA_DIR; no network, no JVM, no Forge.

Run: py engine/tests/test_qa_hook.py   -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="simlab_qa_hook_"))
os.environ["MTG_DATA_DIR"] = str(_TMP)
os.environ.pop("MTG_QA", None)

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import jobqueue  # noqa: E402
import mtg_engine  # noqa: E402
import worker  # noqa: E402
from qa import run as qa  # noqa: E402

RESULTS = _TMP / "sim_results"
RESULTS.mkdir(parents=True)
FIXTURE = RESULTS / "sim_20260724_093703_fixture.json"
shutil.copy(ENGINE / "tests" / "fixtures" / "sim_sample.json", FIXTURE)


def eq(a, b, msg):
    assert a == b, f"{msg}: {a!r} != {b!r}"


def captured(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        val = fn(*a, **kw)
    return val, out.getvalue()


def ordering() -> None:
    calls: list[tuple] = []
    real_engine, real_finish, real_launch = mtg_engine.Engine, jobqueue.finish, worker.launch_qa

    class FakeEngine:
        answer: dict = {}

        def simulate(self, **kw):
            calls.append(("simulate",))
            return FakeEngine.answer

    def fake_finish(job_id, result=None, error=None):
        calls.append(("finish", job_id, bool(result), error))
        if FakeEngine.answer.get("raise_on_finish") and result:
            raise RuntimeError("database is locked")
        return True

    mtg_engine.Engine = FakeEngine
    jobqueue.finish = fake_finish
    worker.launch_qa = lambda f, **kw: calls.append(("qa", f))
    try:
        job = {"id": "job1", "payload": {"decks": ["a.dck", "b.dck"], "games": 2}}
        FakeEngine.answer = {"result": {"summary": {"games": 2}, "meta": {"games_expected": 2}},
                             "result_file": str(FIXTURE), "returncode": 0}
        worker.process_one(job)
        eq([c[0] for c in calls], ["simulate", "finish", "qa"], "finish, THEN the QA launch")
        eq(calls[1][2:], (True, None), "finished with a result")
        eq(calls[2][1], str(FIXTURE), "QA gets the run's result file")

        calls.clear()   # a partial (salvaged) run is finished with a result, so it gets QA
        FakeEngine.answer = {"result": {"summary": {"games": 1},
                                        "meta": {"games_expected": 4, "incomplete": True}},
                             "result_file": str(FIXTURE), "returncode": -1, "killed": True}
        captured(worker.process_one, job)
        eq([c[0] for c in calls], ["simulate", "finish", "qa"], "a salvaged run gets QA too")

        calls.clear()   # nothing played: an error, no result file, no QA
        FakeEngine.answer = {"result": {"summary": {"games": 0}}, "returncode": 0,
                             "stdout": "nothing"}
        worker.process_one(job)
        eq([c[0] for c in calls], ["simulate", "finish"], "no QA for a failed job")
        assert calls[1][3], "finished as an error"

        calls.clear()   # finish() itself raised: the job is not "done", so no QA
        FakeEngine.answer = {"result": {"summary": {"games": 2}, "meta": {}},
                             "result_file": str(FIXTURE), "returncode": 0,
                             "raise_on_finish": True}
        worker.process_one(job)
        eq([c[0] for c in calls], ["simulate", "finish", "finish"], "error path, no QA")
    finally:
        mtg_engine.Engine, jobqueue.finish, worker.launch_qa = real_engine, real_finish, real_launch


def never_raises() -> None:
    def broken(*a, **kw):
        raise OSError("fork failed: out of memory")

    proc, out = captured(worker.launch_qa, FIXTURE, popen=broken)
    eq(proc, None, "a Popen failure returns None")
    assert "QA not started" in out and "out of memory" in out, out
    eq(worker.launch_qa(None), None, "no result file: nothing to do")
    os.environ["MTG_QA"] = "0"
    try:
        seen = []
        eq(worker.launch_qa(FIXTURE, popen=lambda *a, **k: seen.append(a)), None, "MTG_QA=0")
        eq(seen, [], "and nothing was started")
    finally:
        os.environ.pop("MTG_QA", None)


def sleeper(cmd, **kw):
    """A stand-in child that ignores its command and outlives any timeout."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **kw)


def watchdog() -> None:
    target = RESULTS / "sim_20260102_000000_ffffffffffff.json"
    t0 = time.perf_counter()
    proc, out = captured(worker.launch_qa, target, timeout=1.0, popen=sleeper)
    took = time.perf_counter() - t0
    assert proc is not None, out
    assert took < 1.0, f"launch returns at once, whatever the child does ({took:.2f} s)"
    assert proc.poll() is None, "the child is still running after the launch returned"
    assert worker._qa_busy(), "a live QA child makes the worker busy"
    deadline = time.time() + 20
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    assert proc.poll() is not None, "the watchdog killed the child at its timeout"
    time.sleep(0.5)
    with worker._qa_lock:
        assert "sim_20260102_000000_ffffffffffff" not in worker._qa_children, "forgotten"
    assert not worker._qa_busy(), "not busy once it is gone"


def real_launch() -> None:
    proc, _ = captured(worker.launch_qa, FIXTURE)
    assert proc is not None
    rc = proc.wait(timeout=120)
    eq(rc, 0, "run.py wrote a clean qa.json")
    d = qa.read_qa(FIXTURE.name, _TMP)
    eq((d["run"], d["errors"]), (FIXTURE.name, []), "the hook's qa.json")
    eq(qa.read_attempts(FIXTURE.name, _TMP)["attempts"], 1, "one attempt recorded")
    time.sleep(0.5)
    assert not worker._qa_busy(), "reaped"


def sweeper() -> None:
    ddir = _TMP / "sweep"
    rdir = ddir / "sim_results"
    rdir.mkdir(parents=True)
    now = time.time()

    def result(name, age):
        p = rdir / name
        p.write_text('{"meta": {}, "games": []}', encoding="utf-8")
        os.utime(p, (now - age, now - age))
        return p

    result("sim_20260101_000001_a.json", 3600)       # has a qa.json
    result("sim_20260101_000002_b.json", 7200)       # needs QA
    result("sim_20260101_000003_c.json", 10)         # still being written
    result("sim_20260101_000000_d.json", 9000)       # needs QA, older
    (ddir / "sim_results" / "notes.txt").write_text("x", encoding="utf-8")
    qa_dir = ddir / "simkb" / "runs" / "sim_20260101_000001_a"
    qa_dir.mkdir(parents=True)
    (qa_dir / "qa.json").write_text("{}", encoding="utf-8")
    launched: list[str] = []
    launch = lambda f, **kw: launched.append(Path(f).name)

    eq(worker.sweep_qa(now, data_dir=ddir, launch=launch), "sim_20260101_000002_b",
       "the newest finished run without a qa.json")
    eq(launched, ["sim_20260101_000002_b.json"], "one launch per sweep")

    def attempts(stem, **rec):
        p = ddir / "simkb" / "runs" / stem / "attempts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec), encoding="utf-8")

    attempts("sim_20260101_000002_b", attempts=1, last_started_epoch=now - 20)
    eq(worker.sweep_qa(now, data_dir=ddir, launch=launch), "sim_20260101_000000_d",
       "an attempt that may still be running is left alone")
    attempts("sim_20260101_000002_b", attempts=1, last_started_epoch=now - 600)
    eq(worker.sweep_qa(now, data_dir=ddir, launch=launch), "sim_20260101_000002_b",
       "a stale attempt is retried")
    attempts("sim_20260101_000002_b", attempts=qa.MAX_ATTEMPTS, last_started_epoch=now - 600)
    attempts("sim_20260101_000000_d", attempts=qa.MAX_ATTEMPTS, last_started_epoch=now - 600)
    got, out = captured(worker.sweep_qa, now, data_dir=ddir, launch=launch)
    eq(got, None, "nothing left that may be retried")
    eq(out.count("gave up"), 2, "each give-up is logged")
    got, out = captured(worker.sweep_qa, now, data_dir=ddir, launch=launch)
    eq(out.count("gave up"), 0, "once")
    eq(worker.sweep_qa(now + 10**6, data_dir=_TMP / "nowhere", launch=launch), None,
       "no results dir: nothing to do")

    class Alive:
        def poll(self):
            return None

    attempts("sim_20260101_000000_d", attempts=0)
    with worker._qa_lock:
        worker._qa_children["someone"] = Alive()
    try:
        eq(worker.sweep_qa(now, data_dir=ddir, launch=launch), None,
           "nothing starts while a QA child is alive")
    finally:
        with worker._qa_lock:
            worker._qa_children.pop("someone", None)
    eq(worker.sweep_qa(now, data_dir=ddir, launch=launch), "sim_20260101_000000_d", "then it does")


def idle() -> None:
    real = worker.sweep_qa
    n = []
    worker.sweep_qa = lambda now=None, **kw: n.append(now)
    try:
        worker._last_sweep = 0.0
        worker.idle_tick(1000.0)
        worker.idle_tick(1000.0 + worker.QA_SWEEP_SECONDS - 1)
        eq(n, [1000.0], "at most one sweep per interval")
        worker.idle_tick(1000.0 + worker.QA_SWEEP_SECONDS + 1)
        eq(len(n), 2, "the next interval sweeps again")
        os.environ["MTG_QA"] = "0"
        worker.idle_tick(10**6)
        eq(len(n), 2, "MTG_QA=0: no sweep")
        os.environ.pop("MTG_QA", None)

        def boom(now=None, **kw):
            raise RuntimeError("disk gone")

        worker.sweep_qa = boom
        _, out = captured(worker.idle_tick, 10**7)
        assert "QA sweep failed" in out, out
    finally:
        worker.sweep_qa = real
        os.environ.pop("MTG_QA", None)


def main() -> None:
    try:
        ordering()
        never_raises()
        watchdog()
        real_launch()
        sweeper()
        idle()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
