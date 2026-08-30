"""Re-adapt a finished run from its raw shim logs, in place.

The shim has emitted per-seat rubric records since 0.9.0, board-state streams
since 0.12.0 and zone phases since 0.13.0, but the ADAPTER only started
passing each of those through later. A run simulated with a new shim and
adapted with an older engine therefore has all of that data sitting in its
raw JSONL and none of it in the result file the product reads.

Re-adapting is a re-parse of logs that are already on disk, not a repair and
not a re-simulation: the same function that produced the result the first
time runs again over the same bytes. What changes is only which fields the
adapter keeps.

SAFETY. This rewrites a user's result file, so it refuses unless the re-parse
reproduces the run exactly: same game count, same players per game, same
winner, same draw flag, same turn count. If any of those differ, the raw logs
and the result are not the same run (or the adapter changed semantics) and
the file is left untouched. The original is copied to <name>.bak before the
swap either way.

Meta is PRESERVED from the existing result, not rebuilt: the raw shim logs do
not carry the deck paths, clock, or rotation accounting that run_sim wrote,
and salvage()'s reconstructed meta is deliberately marked incomplete. Only
the agent string is refreshed, because that is the one meta field the raw log
is authoritative for.

Usage:
  python3 engine/readapt.py --check <result.json> [...]   # report only
  python3 engine/readapt.py --write <result.json> [...]   # rewrite in place
  python3 engine/readapt.py --check --all                 # every result in the dir
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shim_log_adapter import parse_shim_jsonl  # noqa: E402

# sim_20260830_142314_f8d3537d66b1_rotated.json -> f8d3537d66b1
# The id slot is optional: results written before run ids existed are named
# sim_<stamp>_rotated.json, and the naive pattern captured "rotated" as the
# id for those. Harmless downstream (the glob then finds nothing) but wrong,
# and a stray shim_raw_rotated_*.jsonl would have matched the wrong run.
_RUN_ID = re.compile(r"^sim_\d{8}_\d{6}_([A-Za-z0-9_-]+?)(?:_rotated)?\.json$")


def _is_id(candidate: str) -> bool:
    return candidate != "rotated"

# Keys the newer adapter adds to each game. Absent from an older result, which
# is exactly what re-adapting recovers.
ENRICHING_KEYS = ("rubric", "boardfx", "zones")


def run_id_of(path: Path) -> str | None:
    m = _RUN_ID.match(path.name)
    if not m:
        return None
    return m.group(1) if _is_id(m.group(1)) else None


def raw_logs_for(path: Path, run_id: str) -> list[Path]:
    d = path.parent
    return (sorted(d.glob(f"shim_raw_{run_id}_rot*.jsonl"))
            or sorted(d.glob(f"shim_raw_{run_id}.jsonl")))


def _fingerprint(game: dict) -> tuple:
    """What must be identical for a re-parse to be the same game."""
    res = game.get("result") or {}
    return (
        tuple(game.get("players") or []),
        res.get("winner"),
        bool(res.get("draw")),
        len(game.get("turns") or []),
    )


def _counts(games: list[dict]) -> dict[str, int]:
    out = {k: 0 for k in ENRICHING_KEYS}
    for g in games:
        for k in ENRICHING_KEYS:
            out[k] += len(g.get(k) or [])
    return out


def readapt(path: Path, write: bool = False) -> dict:
    """Re-parse one result from its raw logs. Returns a report; never raises
    on a mismatch, so a batch run reports every file instead of stopping."""
    report: dict = {"file": path.name, "ok": False, "written": False}
    run_id = run_id_of(path)
    if not run_id:
        report["reason"] = "no run id in filename; raw logs cannot be located"
        return report
    logs = raw_logs_for(path, run_id)
    if not logs:
        report["reason"] = "no shim raw logs on disk for this run"
        return report

    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        report["reason"] = f"result unreadable: {e}"
        return report

    games: list[dict] = []
    agent = None
    for p in logs:
        try:
            sub = parse_shim_jsonl(p.read_text(encoding="utf-8", errors="replace"),
                                   source=p.name)
        except Exception as e:  # noqa: BLE001
            report["reason"] = f"raw log {p.name} unparseable: {e}"
            return report
        agent = (sub.get("meta") or {}).get("agent") or agent
        games.extend(g for g in (sub.get("games") or []) if g.get("result"))

    old_games = old.get("games") or []
    report["games_old"] = len(old_games)
    report["games_new"] = len(games)
    if len(games) != len(old_games):
        report["reason"] = (f"game count differs (result {len(old_games)}, "
                            f"raw {len(games)}); refusing to rewrite")
        return report
    for i, (a, b) in enumerate(zip(old_games, games)):
        if _fingerprint(a) != _fingerprint(b):
            report["reason"] = (f"game {i + 1} differs between result and raw "
                                f"logs; refusing to rewrite")
            report["detail"] = {"result": _fingerprint(a), "raw": _fingerprint(b)}
            return report

    before, after = _counts(old_games), _counts(games)
    report["before"] = before
    report["after"] = after
    report["gained"] = {k: after[k] - before[k] for k in ENRICHING_KEYS}
    report["ok"] = True
    if not any(v > 0 for v in report["gained"].values()):
        report["reason"] = "nothing to gain; already adapted with this engine"
        return report

    if not write:
        return report

    # Meta stays the caller's: raw logs carry no deck paths, clock, or
    # rotation accounting. Only the agent string is refreshed.
    merged = dict(old)
    merged["games"] = games
    meta = dict(old.get("meta") or {})
    if agent:
        meta["agent"] = agent
    meta["readapted"] = True
    merged["meta"] = meta

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(merged), encoding="utf-8")
    os.replace(tmp, path)
    report["written"] = True
    report["backup"] = backup.name
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="*", help="result .json paths")
    ap.add_argument("--all", action="store_true",
                    help="every sim_*.json in the results dir")
    ap.add_argument("--dir", default=None, help="results dir for --all")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="report only (default)")
    g.add_argument("--write", action="store_true", help="rewrite in place")
    args = ap.parse_args(argv)

    paths = [Path(p) for p in args.results]
    if args.all:
        base = Path(args.dir) if args.dir else Path(
            os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent))) / "sim_results"
        paths.extend(sorted(base.glob("sim_*.json")))
    if not paths:
        ap.print_help()
        return 2

    gained_any = 0
    for p in paths:
        r = readapt(p, write=args.write)
        if r["ok"] and any(v > 0 for v in r.get("gained", {}).values()):
            gained_any += 1
            g = r["gained"]
            print(f"{'REWROTE' if r['written'] else 'would gain'}  {r['file']}: "
                  + ", ".join(f"+{g[k]} {k}" for k in ENRICHING_KEYS if g[k] > 0))
        elif r["ok"]:
            print(f"up to date  {r['file']}")
        else:
            print(f"skipped     {r['file']}: {r.get('reason')}")
    print(f"\n{gained_any} of {len(paths)} result(s) "
          f"{'rewritten' if args.write else 'would gain data'}."
          + ("" if args.write else " Re-run with --write to apply."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
