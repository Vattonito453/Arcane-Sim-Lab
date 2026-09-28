"""Run engine/qa/knockouts.py on the audited games (PREREG "Order of work", step 5).

    py studies/knockout_audit/run_analyzer.py <runs_dir> <out.json>

Checks each audited file's md5 against PREREG.md, runs
knockouts.analyse_game() on every game of the reading set, and writes
{"blob", "context_blob", "games": {game key: {"knockouts", "turning_point"}}}.
The blob is the git blob of engine/qa/knockouts.py as it sits on disk when run
(computed the way git does, so it matches `git rev-parse HEAD:engine/qa/knockouts.py`
on a clean tree).

The output keeps only fields score.py and RESULTS.md need. Forge's loss text
(`reason`) and `cast_before` are dropped so that nothing copied from the log of
Richard's games lands in a file that may be committed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "engine" / "qa"))

import knockouts as K  # noqa: E402

RUNS = {  # label -> (file, md5), PREREG "The runs"
    "R": ("sim_20260925_003803_d0eb966b8d33_rotated.json", "396ef82b5d818f67298682af924df3a2"),
    "S": ("sim_20260801_193328.json", "df282cd5cb44527001e9f229c447d6bd"),
    "T": ("sim_20260723_101044.json", "340c7b65b953ff3f7497be7bf275345c"),
}
KO_KEEP = ("player", "turn", "round", "cause", "by", "card", "basis", "dated_by", "amount")
TP_KEEP = ("turn", "round", "seat", "shift", "basis", "inferred", "event_hint",
           "event_by", "share_before", "share_after")


def git_blob(path: Path) -> str:
    # A Windows checkout with core.autocrlf=true holds CRLF; git stores LF, so
    # normalise before hashing or the blob never matches the committed one.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main(runs_dir: Path, out: Path) -> None:
    sample = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
    games_out = {}
    for label, (fname, md5) in RUNS.items():
        p = runs_dir / fname
        got = hashlib.md5(p.read_bytes()).hexdigest()
        if got != md5:
            raise SystemExit(f"{fname}: md5 {got} != registered {md5}")
        result = json.loads(p.read_text(encoding="utf-8"))
        for key in sample["reading_set"]:
            if not key.startswith(label + "-"):
                continue
            n = int(key.split("-g")[1])
            one = K.analyse_game(result["games"][n - 1])
            tp = one["turning_point"]
            games_out[key] = {
                "knockouts": [{k: ko.get(k) for k in KO_KEEP if k in ko}
                              for ko in one["knockouts"]],
                "turning_point": None if tp is None else {k: tp.get(k) for k in TP_KEEP},
            }
    doc = {
        "blob": git_blob(ROOT / "engine" / "qa" / "knockouts.py"),
        "context_blob": git_blob(ROOT / "engine" / "qa" / "context.py"),
        "games": games_out,
    }
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"knockouts.py blob {doc['blob']}; {len(games_out)} games -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
