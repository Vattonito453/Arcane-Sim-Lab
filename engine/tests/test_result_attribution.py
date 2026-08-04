#!/usr/bin/env python3
"""Result-file attribution tests (audit A13).

A job used to claim "the newest sim_*.json written since I started", which
credits another producer's file to this job and marks it done with someone
else's numbers. Results are now claimed by run id.

Run: python3 engine/tests/test_result_attribution.py   (no network, no JVM)
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mtg_engine  # noqa: E402
import run_sim  # noqa: E402


def _write(d: Path, name: str, marker: str, mtime: float | None = None) -> Path:
    p = d / name
    p.write_text(f'{{"marker": "{marker}"}}', encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


def test_result_path_embeds_run_id() -> None:
    out = Path("/tmp")
    assert run_sim.result_path(out, "20260804_120000", "abc123", False).name == \
        "sim_20260804_120000_abc123.json"
    assert run_sim.result_path(out, "20260804_120000", "abc123", True).name == \
        "sim_20260804_120000_abc123_rotated.json"
    # No id: unchanged legacy shape, so old tooling and old files still match.
    assert run_sim.result_path(out, "20260804_120000", None, True).name == \
        "sim_20260804_120000_rotated.json"
    # Path separators can never escape the output directory.
    assert "/" not in run_sim.result_path(out, "s", "../../etc/passwd", False).name
    print("  result filename carries the run id: OK")


def test_foreign_newer_file_is_not_claimed(d: Path) -> None:
    """The actual bug: another producer's result lands first and wins."""
    t0 = time.time()
    time.sleep(0.01)
    mine = _write(d, "sim_20260804_120000_myjob_rotated.json", "MINE")
    # A second worker finishes a moment later -- newer, so the old mtime-window
    # claim would have picked exactly this one.
    _write(d, "sim_20260804_120001_otherjob_rotated.json", "THEIRS")

    got = mtg_engine._claim_result(str(d), "myjob", t0)
    assert got == mine, f"claimed the wrong run's result: {got}"
    assert "MINE" in got.read_text(encoding="utf-8")
    print("  a newer foreign result is not claimed: OK")


def test_stale_attempt_of_same_job_is_not_claimed(d: Path) -> None:
    """recover_orphans requeues under the SAME id; the old file must not win."""
    old = _write(d, "sim_20260804_100000_retried_rotated.json", "ATTEMPT1",
                 mtime=time.time() - 3600)
    t0 = time.time()
    time.sleep(0.01)
    new = _write(d, "sim_20260804_130000_retried_rotated.json", "ATTEMPT2")

    got = mtg_engine._claim_result(str(d), "retried", t0)
    assert got == new, f"claimed the stale attempt: {got}"
    assert old.exists(), "test setup: the old attempt should still be on disk"
    print("  a requeued job ignores its previous attempt: OK")


def test_no_match_returns_none_rather_than_guessing(d: Path) -> None:
    """If this job wrote nothing, claim nothing -- never fall back to a guess."""
    t0 = time.time()
    time.sleep(0.01)
    _write(d, "sim_20260804_120000_somebodyelse_rotated.json", "THEIRS")
    assert mtg_engine._claim_result(str(d), "ghostjob", t0) is None, \
        "claimed another job's file when this job produced none"
    print("  no result means None, not someone else's file: OK")


def test_idless_run_falls_back_to_the_time_window(d: Path) -> None:
    """A hand-run sim has no id to match on; the old behavior is the best available."""
    _write(d, "sim_20260804_090000_rotated.json", "OLD", mtime=time.time() - 3600)
    t0 = time.time()
    time.sleep(0.01)
    fresh = _write(d, "sim_20260804_140000_rotated.json", "FRESH")
    assert mtg_engine._claim_result(str(d), None, t0) == fresh
    print("  id-less run still uses the freshness window: OK")


def test_run_id_is_not_matched_as_a_substring(d: Path) -> None:
    """'job1' must not claim a file belonging to 'job12'."""
    t0 = time.time()
    time.sleep(0.01)
    _write(d, "sim_20260804_120000_job12_rotated.json", "OTHER")
    assert mtg_engine._claim_result(str(d), "job1", t0) is None, \
        "run id matched as a substring of a longer id"
    mine = _write(d, "sim_20260804_120002_job1_rotated.json", "MINE")
    assert mtg_engine._claim_result(str(d), "job1", t0) == mine
    print("  run id is matched exactly, not as a prefix: OK")


def main() -> None:
    test_result_path_embeds_run_id()
    for fn in (test_foreign_newer_file_is_not_claimed,
               test_stale_attempt_of_same_job_is_not_claimed,
               test_no_match_returns_none_rather_than_guessing,
               test_idless_run_falls_back_to_the_time_window,
               test_run_id_is_not_matched_as_a_substring):
        with tempfile.TemporaryDirectory() as tmp:
            fn(Path(tmp))
    print("result attribution: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
