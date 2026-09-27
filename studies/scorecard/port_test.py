#!/usr/bin/env python3
"""Port test: does a ported QA detector reproduce the diagnosis figure it was
ported for? (tasks/25-repair-plan.md WS1 task 5; G0a precondition for tutors)

Each manifest in manifests/ names the exact run files behind a figure (path
and md5) and the figures to recompute. This script re-runs the detector on
exactly those files and compares:

  PASS     every figure lands within the manifest's relative tolerance (5%)
  FAIL     a figure is outside it (the detector's results are held)
  SKIPPED  the test could not be run as specified: a run file is missing or
           differs from its md5, or a required input (the Forge index) is not
           built. SKIPPED lists what is missing and is never a pass.

Run files are study output; most are gitignored, so a fresh clone or a
worktree has only some of them. Point --root at the checkout that holds
them (the dev box's main working tree).

Usage:
    py studies/scorecard/port_test.py [--root DIR] [--manifest NAME ...]
        [--forge-index DIR] [--card-cache PATH] [--json]

Exit status: 0 all PASS, 1 any FAIL, 2 any SKIPPED (and none failed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "engine"))

MANIFESTS = HERE / "manifests"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dig(obj, dotted: str):
    """"by_seat.magda.plan.closer_overrides" -> the value, or 0 when a
    level is absent (a count nobody incremented is zero)."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return 0
        cur = cur[part]
    return cur


def within(got: float, want: float, tol: float) -> bool:
    if want == 0:
        return got == 0
    return abs(got - want) / abs(want) <= tol


def selected(runs: list[dict], spec) -> list[dict]:
    if spec in (None, "all"):
        return runs
    prefixes = [spec] if isinstance(spec, str) else list(spec)
    return [r for r in runs if any(r["path"].startswith(p) for p in prefixes)]


def detector_for(name: str):
    if name.endswith("qa/tutors.py"):
        from qa import tutors
        return tutors
    raise SystemExit(f"unknown detector in manifest: {name}")


def run_manifest(path: Path, root: Path, forge, facts) -> dict:
    from qa import context as qctx
    m = json.loads(path.read_text(encoding="utf-8"))
    report = {"manifest": path.name, "figure": m.get("figure"), "status": None,
              "missing": [], "changed": [], "figures": []}
    runs = m.get("runs") or []
    for r in runs:
        p = root / r["path"]
        if not p.is_file():
            report["missing"].append(r["path"])
        elif md5_of(p) != r["md5"]:
            report["changed"].append(r["path"])
    needs_forge = any("Forge index" in x for x in m.get("requires") or [])
    if report["missing"] or report["changed"]:
        report["status"] = "SKIPPED"
        report["why"] = (f"{len(report['missing'])} of {len(runs)} run files missing and "
                         f"{len(report['changed'])} changed under {root}")
        return report
    if needs_forge and forge is None:
        report["status"] = "SKIPPED"
        report["why"] = ("no Forge index is built (py engine/forge_index.py build, or pass "
                         "--forge-index); tutor reach cannot be read without it")
        return report
    det = detector_for(m["detector"])
    per_run: dict[str, dict] = {}
    for r in runs:
        ctx = qctx.from_path(root / r["path"], facts=facts, forge=forge)
        metrics, _flags = det.detect(ctx)
        per_run[r["path"]] = metrics
    tol = float(m.get("tolerance_relative", 0.05))
    ok = True
    for fig in m.get("figures") or []:
        chosen = selected(runs, fig.get("runs"))
        combined = det.combine([per_run[r["path"]] for r in chosen])
        got = [dig(combined, fig["numerator"])]
        if fig.get("denominator"):
            got.append(dig(combined, fig["denominator"]))
        want = fig["expect"]
        passed = all(within(g, w, tol) for g, w in zip(got, want))
        ok = ok and passed
        report["figures"].append({"name": fig["name"], "runs": len(chosen), "expect": want,
                                  "got": got, "pass": passed})
    report["status"] = "PASS" if ok else "FAIL"
    report["not_gated"] = m.get("not_gated") or []
    return report


def main(argv: list[str] | None = None) -> int:
    from qa import context as qctx
    ap = argparse.ArgumentParser(description="Recompute diagnosis figures with the QA detectors.")
    ap.add_argument("--root", default=str(REPO),
                    help="checkout holding the run files (default: this repo)")
    ap.add_argument("--manifest", action="append",
                    help="manifest name or path (default: every manifests/*.json)")
    ap.add_argument("--forge-index", help="a built Forge index directory (default: the local one)")
    ap.add_argument("--card-cache", help="card cache to read (default: engine/card_cache.json)")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    a = ap.parse_args(argv)

    paths = []
    for name in a.manifest or []:
        p = Path(name)
        paths.append(p if p.is_file() else MANIFESTS / (name if name.endswith(".json") else name + ".json"))
    if not paths:
        paths = sorted(MANIFESTS.glob("*.json"))
    forge = qctx.load_forge_index(a.forge_index)
    facts = qctx.CardFacts.load(a.card_cache)
    root = Path(a.root)
    reports = [run_manifest(p, root, forge, facts) for p in paths]

    if a.json:
        print(json.dumps(reports, indent=1))
    else:
        for r in reports:
            print(f"{r['status']:8s} {r['manifest']}")
            if r["status"] == "SKIPPED":
                print(f"         {r['why']}")
                for p in r["missing"]:
                    print(f"         missing: {p}")
                for p in r["changed"]:
                    print(f"         changed: {p}")
            for f in r["figures"]:
                exp = "/".join(str(x) for x in f["expect"])
                got = "/".join(str(x) for x in f["got"])
                print(f"         {'ok  ' if f['pass'] else 'MISS'} {got:>10s} vs {exp:<10s} "
                      f"{f['name']} ({f['runs']} runs)")
            for n in r.get("not_gated") or []:
                print(f"         note {n['detector']} vs {n['diagnosis']} {n['name']} (not gated)")
    statuses = {r["status"] for r in reports}
    if "FAIL" in statuses:
        return 1
    if "SKIPPED" in statuses:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
