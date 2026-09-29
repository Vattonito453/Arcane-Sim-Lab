#!/usr/bin/env python3
"""The QA analyzer's time budget (repair plan WS1 task 8): p95 under 10 s.

    py -u engine/qa/budget.py [--data-dir D] [--repeat 20] [--corpus]

Times engine/qa/run.py the way the worker launches it (worker.launch_qa): a
child process at lowered priority (nice 10 on POSIX; below-normal priority
class on Windows), wall clock from spawn to exit, so interpreter start, the
card cache and Forge index loads, and the qa.json write are all counted.
The priority drop is the stand-in for the 2-vCPU VM the plan names: on a
busy box the analyzer only gets what Forge leaves.

  --repeat N   runs on the LARGEST sim_*.json in <data dir>/sim_results, N
               times; reports min / median / p95 / max and PASS or FAIL
               against the 10 s budget
  --corpus     one run on every sim_*.json there, and its distribution

It writes each run's qa.json into that data dir AND files the run's flags in
the review queue, exactly as the worker's hook would (the queue is
idempotent, so a repeat files nothing new). It must not pass --no-queue: a
run whose qa.json exists is never filed later (the sweeper and `run.py
--all` skip it), so a budget run on the VM with --no-queue would have kept
every measured run's flags out of the review queue for good. On the VM:
    sudo docker exec deploy-worker-1 python3 -u /app/engine/qa/budget.py --corpus

Measured 2026-09-29, Windows dev box (32 logical CPUs, otherwise idle),
below-normal priority, analyzer qa/0.1.0, on a copy of engine/sim_results:
  largest result (8.9 MB, 16 shim games), 20 runs: median 0.52 s, p95 0.56 s,
      max 0.61 s: PASS
  all 61 results, one run each: median 0.39 s, p95 0.56 s, max 0.61 s (the
      5.7 MB stdout result)
  CPU time of one run on the largest: 0.73 s (user 0.55, kernel 0.19)
Not yet measured on the VM. Contended, the picture is different: beside one
busy nice-0 thread (Forge), CFS gives nice 10 about 110/1134 of a core, which
puts 0.73 s of CPU at about 7.6 s of wall on this box's cores and more on the
VM's slower ones. A Windows stand-in (the analyzer sharing one CPU with nine
busy loops) measured 23 to 65 s, inflated by wake-up latency after each file
read. Either way it stays under the worker's 120 s ceiling; the p95 under 10 s
is met when the worker is idle, and the VM run above is the real verdict.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
RUN = Path(__file__).resolve().parent / "run.py"
BUDGET_P95 = 10.0
NICE = 10


def _pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def time_one(path: Path, ddir: Path) -> tuple[float, int, dict]:
    # No --no-queue: see the module docstring. The queue write is part of what
    # the hook does, so it belongs in the timing too.
    cmd = [sys.executable, "-u", str(RUN), str(path), "--data-dir", str(ddir),
           "--quiet", "--nice", str(NICE)]
    kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    t0 = time.perf_counter()
    rc = subprocess.run(cmd, timeout=300, **kw).returncode
    secs = time.perf_counter() - t0
    stages = {}
    try:
        name = path.name[:-4] if path.name.endswith(".json.out") else path.name
        doc = json.loads((ddir / "simkb" / "runs" / name[:-5] / "qa.json").read_text(encoding="utf-8"))
        stages = {k: v.get("seconds") for k, v in (doc.get("detectors") or {}).items()}
        stages["analysis"] = doc.get("seconds")
    except (OSError, ValueError):
        pass
    return secs, rc, stages


def summary(xs: list[float]) -> dict:
    return {"n": len(xs), "min": round(min(xs), 3), "median": round(statistics.median(xs), 3),
            "p95": round(_pct(xs, 0.95), 3), "max": round(max(xs), 3)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", default=os.environ.get("MTG_DATA_DIR", str(ENGINE)))
    ap.add_argument("--repeat", type=int, default=20)
    ap.add_argument("--corpus", action="store_true")
    a = ap.parse_args(argv)
    ddir = Path(a.data_dir)
    files = sorted((ddir / "sim_results").glob("sim_*.json"))
    if not files:
        print(f"no sim_*.json under {ddir / 'sim_results'}", file=sys.stderr)
        return 2
    largest = max(files, key=lambda f: f.stat().st_size)
    out: dict = {"cpu_count": os.cpu_count(), "priority": f"nice {NICE}" if os.name != "nt"
                 else "BELOW_NORMAL_PRIORITY_CLASS", "budget_p95_s": BUDGET_P95}
    ok = True
    if a.repeat:
        secs, stages, rcs = [], [], []
        for _ in range(a.repeat):
            s, rc, st = time_one(largest, ddir)
            secs.append(s)
            stages.append(st)
            rcs.append(rc)
        out["largest"] = {"file": largest.name, "mb": round(largest.stat().st_size / 1e6, 2),
                          "exit_codes": sorted(set(rcs)), "wall": summary(secs),
                          "last_stages_s": stages[-1]}
        ok = _pct(secs, 0.95) < BUDGET_P95 and set(rcs) <= {0, 1}
        out["verdict"] = "PASS" if ok else "FAIL"
    if a.corpus:
        per = []
        for f in files:
            s, rc, _ = time_one(f, ddir)
            per.append({"file": f.name, "mb": round(f.stat().st_size / 1e6, 2),
                        "seconds": round(s, 3), "rc": rc})
        xs = [p["seconds"] for p in per]
        out["corpus"] = {"runs": len(per), "wall": summary(xs),
                         "exit_codes": {str(rc): sum(1 for p in per if p["rc"] == rc)
                                        for rc in sorted({p["rc"] for p in per})},
                         "slowest": sorted(per, key=lambda p: -p["seconds"])[:5]}
    print(json.dumps(out, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
