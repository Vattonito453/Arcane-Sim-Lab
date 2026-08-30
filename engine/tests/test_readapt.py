#!/usr/bin/env python3
"""Re-adapt safety: it must recover data, and refuse rather than corrupt.

Run: python3 engine/tests/test_readapt.py   ->  ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import readapt  # noqa: E402

RAW = """\
{"rec":"meta","shim":"0.13.0","format":"Commander","games":1,\
"players":["Ai(1)-Alpha","Ai(2)-Beta"],"agents":["plan","plan"]}
{"rec":"entry","game":0,"type":"TURN","message":"Turn 1 (Ai(1)-Alpha)"}
{"rec":"rubric","game":0,"kind":"mull","player":"Ai(1)-Alpha","mulls":0,"hand":7,"lands":3}
{"rec":"rubric","game":0,"kind":"block","player":"Ai(2)-Beta","incoming":2,"blocked":1,\
"legalMissed":1,"v3":1,"v2":0,"v1":0,"v0":0,"freeTaken":1,"freeMissed":0,\
"safeMissed":0,"lifeTaken":3}
{"rec":"zone","game":0,"turn":1,"phase":"DRAW","card":"Forest","cardId":1,\
"from":"Library","to":"Hand","fromPlayer":"Ai(1)-Alpha","toPlayer":"Ai(1)-Alpha"}
{"rec":"tap","game":0,"turn":1,"phase":"MAIN1","cardId":1,"card":"Forest","tapped":true}
{"rec":"result","game":0,"draw":false,"winner":"Ai(1)-Alpha","turns":1,\
"timedOut":false,"turnCapped":false,"seats":[{"name":"Ai(1)-Alpha","life":40,\
"alive":true},{"name":"Ai(2)-Beta","life":0,"alive":false}],"ms":100}
"""


def _fixture(tmp: Path, *, strip=True, name="sim_20260830_142314_run01.json"):
    """A raw log plus a result adapted as an OLDER engine would have."""
    (tmp / "shim_raw_run01_rot0.jsonl").write_text(RAW, encoding="utf-8")
    from shim_log_adapter import parse_shim_jsonl
    full = parse_shim_jsonl(RAW, source="fixture")
    if strip:
        for g in full["games"]:
            for k in readapt.ENRICHING_KEYS:
                g.pop(k, None)
    full["meta"]["decks"] = ["alpha.dck", "beta.dck"]
    full["meta"]["clock"] = 900
    p = tmp / name
    p.write_text(json.dumps(full), encoding="utf-8")
    return p


def test_recovers_dropped_records():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _fixture(tmp)
        before = json.loads(p.read_text(encoding="utf-8"))
        assert not before["games"][0].get("rubric")

        r = readapt.readapt(p, write=True)
        assert r["ok"] and r["written"], r
        assert r["gained"]["rubric"] == 2, r["gained"]
        assert r["gained"]["zones"] == 1, r["gained"]

        after = json.loads(p.read_text(encoding="utf-8"))
        assert len(after["games"][0]["rubric"]) == 2
        # meta the raw log cannot know is preserved
        assert after["meta"]["decks"] == ["alpha.dck", "beta.dck"]
        assert after["meta"]["clock"] == 900
        assert after["meta"]["readapted"] is True
        assert (tmp / (p.name + ".bak")).is_file()


def test_idempotent():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _fixture(tmp)
        readapt.readapt(p, write=True)
        again = readapt.readapt(p, write=True)
        assert again["ok"] is True
        assert again["written"] is False, "a second pass must not rewrite"
        assert "nothing to gain" in again.get("reason", "")


def test_refuses_when_game_count_differs():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _fixture(tmp)
        data = json.loads(p.read_text(encoding="utf-8"))
        data["games"].append(dict(data["games"][0]))  # result claims 2 games
        p.write_text(json.dumps(data), encoding="utf-8")
        r = readapt.readapt(p, write=True)
        assert r["ok"] is False and not r["written"], r
        assert "game count differs" in r["reason"], r["reason"]
        # untouched: still 2 games, still no backup written
        assert len(json.loads(p.read_text(encoding="utf-8"))["games"]) == 2
        assert not (tmp / (p.name + ".bak")).exists()


def test_refuses_when_winner_differs():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _fixture(tmp)
        data = json.loads(p.read_text(encoding="utf-8"))
        data["games"][0]["result"]["winner"] = "Ai(2)-Beta"  # not what the log says
        p.write_text(json.dumps(data), encoding="utf-8")
        r = readapt.readapt(p, write=True)
        assert r["ok"] is False and not r["written"], r
        assert "differs between result and raw" in r["reason"], r["reason"]
        assert json.loads(p.read_text(encoding="utf-8"))["games"][0]["result"][
            "winner"] == "Ai(2)-Beta", "the file must be left exactly as found"


def test_refuses_without_raw_logs():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _fixture(tmp)
        (tmp / "shim_raw_run01_rot0.jsonl").unlink()
        r = readapt.readapt(p, write=True)
        assert r["ok"] is False and not r["written"]
        assert "no shim raw logs" in r["reason"], r["reason"]


def test_refuses_unparseable_filename():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p = _fixture(tmp, name="handmade.json")
        r = readapt.readapt(p, write=True)
        assert r["ok"] is False and not r["written"]
        assert "no run id" in r["reason"], r["reason"]


def test_run_id_parsing():
    assert readapt.run_id_of(Path("sim_20260830_142314_f8d3537d66b1_rotated.json")) \
        == "f8d3537d66b1"
    assert readapt.run_id_of(Path("sim_20260830_142314_abc123.json")) == "abc123"
    assert readapt.run_id_of(Path("sim_20260724_094940_rotated.json")) is None
    assert readapt.run_id_of(Path("nonsense.json")) is None


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
