#!/usr/bin/env python3
"""The post-run feedback hook logs its failures (repair plan WS0 task 4).

Engine.simulate folds each finished run into the plan store through
plan_feedback.record_run. That call sat in `except Exception: pass`, so a
failing hook left no trace anywhere, and whether it ever completed in
production could not be established from the logs. It now writes the full
traceback to stderr (the worker runs python -u, so that is the container
log) and still hands the result back: feedback is an upgrade, never a
requirement for a run to count.

No Forge, no JVM, no network: subprocess.Popen and the result claim are
stubbed, so simulate() runs its real post-processing on a canned result.

Run: py engine/tests/test_post_run_hook.py
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mtg_engine  # noqa: E402
import plan_feedback  # noqa: E402

PAYLOAD = {
    "meta": {"agent": "simlab-forge-shim/0.16.0", "source_hash": "hook-test"},
    "games": [{"players": ["Ai(1)-Alpha", "Ai(2)-Beta"],
               "result": {"winner": "Ai(1)-Alpha"}, "turns": []}],
    "summary": {},
}


class FakePopen:
    """Stands in for the run_sim subprocess: exits 0 at once, prints nothing."""
    calls: list[list[str]] = []

    def __init__(self, cmd, **kwargs):
        FakePopen.calls.append(list(cmd))
        self.returncode = None

    def communicate(self, timeout=None):
        self.returncode = 0
        return "", ""


def _simulate(out_dir: Path) -> tuple[dict, str]:
    """Run Engine.simulate against the stubs; return (result, captured stderr)."""
    # simulate() never touches the rules KB, so skip loading it: the test must
    # not depend on rules/kb, which is stripped before the repo goes public.
    engine = mtg_engine.Engine.__new__(mtg_engine.Engine)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        res = engine.simulate(["alpha.dck", "beta.dck"], games=2, out=str(out_dir),
                              run_id="hooktest")
    return res, err.getvalue()


def main() -> None:
    real_popen = subprocess.Popen
    real_claim = mtg_engine._claim_result
    real_record = plan_feedback.record_run
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        result_file = out_dir / "sim_20260926_120000_hooktest_rotated.json"
        result_file.write_text(json.dumps(PAYLOAD), encoding="utf-8")
        subprocess.Popen = FakePopen
        mtg_engine._claim_result = lambda out, run_id, t0: result_file
        try:
            # 1. record_run raises: traceback logged, result still returned.
            hook_calls: list[dict] = []

            def exploding_record_run(payload):
                hook_calls.append(payload)
                raise RuntimeError("boom-sentinel from test_post_run_hook")

            plan_feedback.record_run = exploding_record_run
            res, err = _simulate(out_dir)
            assert FakePopen.calls, "simulate must go through the (stubbed) subprocess"
            assert "run_sim.py" in " ".join(FakePopen.calls[-1]), FakePopen.calls[-1]
            assert hook_calls == [PAYLOAD], "the hook must receive the parsed result"
            assert res["returncode"] == 0, res
            assert res["result"] == PAYLOAD, "a failing hook must not cost the result"
            assert res["result_file"] == str(result_file), res
            assert res["killed"] is False, res
            print("  record_run raising: result still returned: OK")

            assert "[post-run hook] plan_feedback.record_run FAILED" in err, err
            assert result_file.name in err, "the log line must name the run"
            assert "Traceback (most recent call last)" in err, err
            assert "RuntimeError: boom-sentinel from test_post_run_hook" in err, err
            assert "exploding_record_run" in err, "the FULL traceback, frames included"
            print("  record_run raising: full traceback on stderr: OK")

            # 2. An environmental failure (the module will not import) is the
            # suspected production cause; it must be logged the same way.
            plan_feedback.record_run = real_record
            saved = sys.modules.get("plan_feedback")
            sys.modules["plan_feedback"] = None  # makes `import plan_feedback` raise
            try:
                res, err = _simulate(out_dir)
            finally:
                sys.modules["plan_feedback"] = saved
            assert res["result"] == PAYLOAD, res
            assert "[post-run hook] plan_feedback.record_run FAILED" in err, err
            assert "ImportError" in err or "ModuleNotFoundError" in err, err
            print("  plan_feedback import failure: logged, result returned: OK")

            # 3. Control: a healthy hook stays silent.
            ok_calls: list[dict] = []
            plan_feedback.record_run = lambda payload: ok_calls.append(payload) or {}
            res, err = _simulate(out_dir)
            assert ok_calls == [PAYLOAD], ok_calls
            assert res["result"] == PAYLOAD, res
            assert "[post-run hook]" not in err, err
            print("  healthy hook: silent, result returned: OK")
        finally:
            subprocess.Popen = real_popen
            mtg_engine._claim_result = real_claim
            plan_feedback.record_run = real_record

    print("post-run hook: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
