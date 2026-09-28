"""Freeze the reader outputs into studies/knockout_audit/readings/ (step 3 of PREREG "Order of work").

    py studies/knockout_audit/freeze_readings.py <scratch_readings_dir>

The scratch folder holds each reader's full output, including an `evidence`
field that quotes Forge's log (for run R that is Richard's private game log)
and a free-text `reason`. PREREG "Freeze": the committed readings hold turns,
causes, seat names and card names only, no log text. So this keeps, per
elimination: player, turn, cause, killer, card, confidence; per turning point:
turn, card, confidence. Everything else is dropped. Values are kept exactly as
the reader returned them (turns arrive as digit strings from passes A and B;
score.py parses them), so the frozen file is a faithful subset.

Run once, before engine/qa/knockouts.py is run on the audited files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "readings"

READERS = {  # reader id -> (pass, scratch file stem)
    "A1": ("A", "A1"),
    "A2": ("A", "A2"),
    "B1": ("B", "B1"),
    "B2": ("B", "B2"),
    "C": ("C", "C"),
}
ELIM_KEEP = ("player", "turn", "cause", "killer", "card", "confidence")
TP_KEEP = ("turn", "card", "confidence")


def _subset(d: dict, keys: tuple) -> dict:
    return {k: d[k] for k in keys if k in d}


def main(src: Path) -> None:
    OUT.mkdir(exist_ok=True)
    for rid, (pas, stem) in READERS.items():
        raw = json.loads((src / f"{stem}.json").read_text(encoding="utf-8"))
        games = []
        for g in raw["readings"]:
            tp = g.get("turning_point")
            games.append({
                "game": g["game"],
                "eliminations": [_subset(e, ELIM_KEEP) for e in g.get("eliminations", [])],
                "turning_point": _subset(tp, TP_KEEP) if tp else None,
            })
        doc = {"reader": rid, "pass": pas, "games": games}
        (OUT / f"{rid}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
        print(f"{rid}: {len(games)} games -> {OUT / (rid + '.json')}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
