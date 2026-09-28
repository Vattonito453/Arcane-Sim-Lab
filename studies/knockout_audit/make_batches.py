#!/usr/bin/env python3
"""Split the reading set into the two passes' batches (PREREG.md, "Reading
passes and how they combine") and write one manifest per reader.

Pass A: games in descending evidence size, each to the lighter of A1 and A2.
Pass B: within each A batch (descending size), alternate games go to B1 and
B2, starting A1 with B1 and A2 with B2, so each B batch holds about half of
each A batch and no B batch equals an A batch. A readers read in game-key
order, B readers in reverse key order.

Usage:
    py studies/knockout_audit/make_batches.py <sample.json> <evidence_dir> <audit_dir>
writes <audit_dir>/batches/{A1,A2,B1,B2}.json and copies READER.md beside them.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    sample_p, ev_dir, audit_dir = (Path(a) for a in argv[:3])
    sample = json.loads(sample_p.read_text(encoding="utf-8"))
    keys = sample["reading_set"]
    size = {k: (ev_dir / f"{k}.txt").stat().st_size for k in keys}
    order = sorted(keys, key=lambda k: (-size[k], k))

    a = {"A1": [], "A2": []}
    tot = {"A1": 0, "A2": 0}
    for k in order:
        dest = "A1" if tot["A1"] <= tot["A2"] else "A2"
        a[dest].append(k)
        tot[dest] += size[k]

    b = {"B1": [], "B2": []}
    for src, first in (("A1", "B1"), ("A2", "B2")):
        second = "B2" if first == "B1" else "B1"
        for i, k in enumerate(sorted(a[src], key=lambda k: (-size[k], k))):
            b[first if i % 2 == 0 else second].append(k)

    batches = {"A1": sorted(a["A1"]), "A2": sorted(a["A2"]),
               "B1": sorted(b["B1"], reverse=True), "B2": sorted(b["B2"], reverse=True)}
    assert set(batches["A1"]) | set(batches["A2"]) == set(keys)
    assert set(batches["B1"]) | set(batches["B2"]) == set(keys)
    assert not set(batches["A1"]) & set(batches["A2"])
    assert not set(batches["B1"]) & set(batches["B2"])
    assert {frozenset(batches["B1"]), frozenset(batches["B2"])}.isdisjoint(
        {frozenset(batches["A1"]), frozenset(batches["A2"])})

    out = audit_dir / "batches"
    out.mkdir(parents=True, exist_ok=True)
    reader_md = Path(__file__).with_name("READER.md")
    shutil.copyfile(reader_md, out / "READER.md")
    (audit_dir / "readings").mkdir(exist_ok=True)
    for name, games in batches.items():
        manifest = {
            "reader": name,
            "pass": name[0],
            "instructions": str((out / "READER.md").resolve()),
            "output": str((audit_dir / "readings" / f"{name}.json").resolve()),
            "games": [{"game": k,
                       "evidence": str((ev_dir / f"{k}.txt").resolve()),
                       "turning_point_requested": sample["games"][k]["turning_point_requested"]}
                      for k in games],
            "bytes": sum(size[k] for k in games),
        }
        (out / f"{name}.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(f"{name}: {len(games)} games, {manifest['bytes'] / 1024:.0f} KB: {', '.join(games)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
