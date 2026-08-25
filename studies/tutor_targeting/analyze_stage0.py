#!/usr/bin/env python3
"""Task 20 Stage 0: tutor-target disagreement rate from shim search_seen events.

Reads raw shim JSONL files (shim_raw_*.jsonl) and reports, per seat and
overall:

  searches   every library search the seat resolved (the event denominator)
  ranked>0   searches where at least one legal option carried a plan weight,
             i.e. the plan had an opinion a ranking could act on
  agree      among ranked>0 searches, stock AI's pick already had top weight
  disagree   among ranked>0 searches, a plan-weight ranking would have
             changed the pick

The disagreement lines are printed in full for eyeballing (the task asks for
10). agree=na searches are the plan-coverage gap Stage 1 exists to close;
report them, never fold them into the agreement rate.

Requires shim >= 0.4.1 (events carry picked=/planPick=). Older events are
counted as 'pre-0.4.1' and excluded from rates.

Usage:
  python3 studies/tutor_targeting/analyze_stage0.py <shim_raw_*.jsonl ...>
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

FIELDS = re.compile(
    r"options=(?P<options>\d+) sighted=(?P<sighted>\w+) ranked=(?P<ranked>\d+)"
    r" agree=(?P<agree>\w+) pickedW=(?P<pickedw>\d+) planW=(?P<planw>\d+)"
    r" missing=(?P<missing>.*?) picked=(?P<picked>.*?) planPick=(?P<planpick>.*)$"
)


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__)
        return 2
    per_seat: dict[str, dict[str, int]] = defaultdict(
        lambda: {"searches": 0, "ranked": 0, "agree": 0, "disagree": 0, "old": 0}
    )
    disagreements: list[str] = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("rec") != "agent" or rec.get("event") != "search_seen":
                    continue
                seat = rec.get("player", "?")
                tally = per_seat[seat]
                tally["searches"] += 1
                m = FIELDS.search(rec.get("detail", ""))
                if not m:
                    tally["old"] += 1
                    continue
                agree = m.group("agree")
                if agree == "na":
                    continue
                tally["ranked"] += 1
                if agree == "true":
                    tally["agree"] += 1
                else:
                    tally["disagree"] += 1
                    disagreements.append(
                        f"{path} game={rec.get('game')} turn={rec.get('turn')} "
                        f"seat={seat} picked={m.group('picked')} "
                        f"planPick={m.group('planpick')} "
                        f"(w {m.group('pickedw')} vs {m.group('planw')}, "
                        f"options={m.group('options')})"
                    )
    total = {"searches": 0, "ranked": 0, "agree": 0, "disagree": 0, "old": 0}
    print(f"{'seat':40} {'searches':>8} {'ranked>0':>8} {'agree':>6} "
          f"{'disagree':>8} {'pre-0.4.1':>9}")
    for seat in sorted(per_seat):
        t = per_seat[seat]
        for k in total:
            total[k] += t[k]
        print(f"{seat:40} {t['searches']:>8} {t['ranked']:>8} {t['agree']:>6} "
              f"{t['disagree']:>8} {t['old']:>9}")
    print(f"{'TOTAL':40} {total['searches']:>8} {total['ranked']:>8} "
          f"{total['agree']:>6} {total['disagree']:>8} {total['old']:>9}")
    if total["ranked"]:
        rate = total["disagree"] / total["ranked"]
        print(f"\ndisagreement rate (ranked searches only): "
              f"{total['disagree']}/{total['ranked']} = {rate:.1%}")
    else:
        print("\nno search had a plan-ranked option: the plan-coverage gap is "
              "total. Stage 1 (weights for tutor targets) is the blocker, and "
              "this rate cannot justify or refute Stage 2 yet.")
    if total["searches"]:
        cov = (total["ranked"]) / max(1, total["searches"] - total["old"])
        print(f"plan coverage (searches with any ranked option): {cov:.1%}")
    if disagreements:
        print("\ndisagreements, for eyeballing:")
        for d in disagreements:
            print("  " + d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
