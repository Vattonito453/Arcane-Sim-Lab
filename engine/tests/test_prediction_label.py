#!/usr/bin/env python3
"""The prediction says which pilot it was fit on, and a failed rank check
withholds it (repair plan WS11 task 11, decision 19).

Cases: the run's pilot matches the model's arm; it does not and no rank check
exists for it; the latest check for it passed; the latest check failed
(suppressed, no figures); the record file is missing (fail closed). Plus the
pilot ids engine/pilot.py derives from each meta shape, and the adapter and
rotated-merge carrying plan versions so an R1 run is identifiable.

Run: py engine/tests/test_prediction_label.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mtg_engine  # noqa: E402
import pilot  # noqa: E402
import predict  # noqa: E402
import run_sim  # noqa: E402
from shim_log_adapter import parse_shim_jsonl  # noqa: E402

V2_FLAGS = {"tutorReach": True, "commanderTutorZone": True,
            "noForcedChoices": True, "graveyardDest": True}
R1 = "plan/0.17.0/v2"


def _plan_meta(shim="0.17.0", versions=(2, 2, 2, 2), flags=V2_FLAGS, agents=None):
    """A rotated production run's meta, shaped like run_sim writes it."""
    agents = agents or ["plan"] * 4
    rot = {"seats": ["a.dck", "b.dck", "c.dck", "d.dck"],
           "agent": f"simlab-forge-shim/{shim}", "agents": agents,
           "profiles": ["SimLabHuman"] * 4}
    if versions is not None:
        rot["planVersions"] = list(versions)
        rot["fixFlags"] = [dict(flags) for _ in versions]
    return {"source": "rotated", "agent": f"simlab-forge-shim/{shim}",
            "humanized": all(a == "plan" for a in agents),
            "rotations_detail": [dict(rot) for _ in range(4)]}


def _record(pilot_id, passed, date="2026-10-16", release="R1", value=0.47):
    return {"release": release, "date": date, "pilot": pilot_id,
            "jar_sha": "c2273bef", "metric": "spearman(predicted, human)",
            "value": value, "threshold": 0.40, "pass": passed}


# ---- engine/pilot.py -------------------------------------------------

def test_pilot_ids_for_every_meta_shape():
    assert pilot.run_pilot({})["id"] == "stock"                       # stdout path
    assert pilot.run_pilot({"agent": "forge"})["id"] == "stock"       # salvaged stock
    stock_shim = _plan_meta(agents=["stock"] * 4, versions=None)
    assert pilot.run_pilot(stock_shim)["id"] == "stock"
    assert pilot.run_pilot(_plan_meta())["id"] == R1
    # Before 0.17.0 no shim reads a plan version: version 1 by construction.
    old = pilot.run_pilot(_plan_meta(shim="0.16.0", versions=None))
    assert old["id"] == "plan/0.16.0/v1" and old["plan_version"] == 1, old
    # Richard's run: shim 0.15.0, per-rotation agents, no top-level agents.
    assert pilot.run_pilot(_plan_meta(shim="0.15.0", versions=None))["id"] == "plan/0.15.0/v1"
    # 0.17.0 with version-1 plans is G0a's arm C, a different pilot from R1.
    assert pilot.run_pilot(_plan_meta(versions=(1, 1, 1, 1),
                                      flags={}))["id"] == "plan/0.17.0/v1"
    none = pilot.run_pilot(_plan_meta(flags={k: False for k in V2_FLAGS}))
    assert none["id"] == "plan/0.17.0/v2/fix=none", none
    one = pilot.run_pilot(_plan_meta(flags=dict(V2_FLAGS, commanderTutorZone=False,
                                                 noForcedChoices=False,
                                                 graveyardDest=False)))
    assert one["id"] == "plan/0.17.0/v2/fix=tutorReach", one
    # A 0.17.0 run adapted before plan versions were carried is not assumed R1.
    assert pilot.run_pilot(_plan_meta(versions=None))["id"] == "plan/0.17.0/v-unrecorded"
    mixed = pilot.run_pilot(_plan_meta(agents=["plan", "stock", "stock", "stock"]))
    assert mixed["kind"] == "mixed" and mixed["id"] == "mixed/0.17.0/v2", mixed
    # Only plan seats' versions count toward the pilot.
    m = _plan_meta(agents=["plan", "stock", "stock", "stock"], versions=(2, 1, 1, 1))
    assert pilot.run_pilot(m)["id"] == "mixed/0.17.0/v2"
    # Older shims with only the pod-level bool.
    assert pilot.run_pilot({"agent": "simlab-forge-shim/0.9.0",
                            "humanized": True})["id"] == "plan/0.9.0/v1"
    assert pilot.run_pilot({"agent": "simlab-forge-shim/0.9.0"})["id"] == "unknown"
    # Rotations on two shims are not one pilot.
    two = _plan_meta(shim="0.16.0", versions=None)
    two["agent"] = "simlab-forge-shim"
    two["rotations_detail"][1]["agent"] = "simlab-forge-shim/0.17.0"
    assert pilot.run_pilot(two)["id"].startswith("plan/mixed-shims/"), pilot.run_pilot(two)


def test_pilot_text_is_copy():
    for meta in ({}, _plan_meta(), _plan_meta(versions=None),
                 _plan_meta(agents=["plan", "stock", "stock", "stock"]),
                 {"agent": "simlab-forge-shim/0.9.0"}):
        text = pilot.run_pilot(meta)["text"]
        assert text and "—" not in text, text
    assert pilot.run_pilot(_plan_meta())["text"] == \
        "Sim Lab's pilot (shim 0.17.0, version-2 plans)"


# ---- predict.pilot_honesty ------------------------------------------

MODEL = {"arm": "stock Forge, decided games", "arm_pilot": "stock"}


def test_match_needs_no_check():
    h = predict.pilot_honesty(MODEL, pilot.run_pilot({}), [])
    assert h["pilot_match"] is True and h["suppressed"] is False, h
    assert h["label"] == "Fit on stock Forge games; this run used stock Forge too.", h
    assert h["rank_check"]["status"] == "model_arm", h
    assert h["model_arm"] == {"text": "stock Forge, decided games", "pilot": "stock"}
    # Matching never depends on the record: even a missing file is fine.
    assert predict.pilot_honesty(MODEL, pilot.run_pilot({}), None)["suppressed"] is False


def test_mismatch_without_a_check_keeps_the_label():
    h = predict.pilot_honesty(MODEL, pilot.run_pilot(_plan_meta()),
                              [_record("plan/0.16.0/v1", False)])
    assert h["pilot_match"] is False and h["suppressed"] is False, h
    assert h["label"] == "Fit on stock Forge games; this run used Sim Lab's pilot.", h
    assert h["rank_check"]["status"] == "none", h
    assert h["rank_check"]["text"] == "No rank check has been run for this pilot yet.", h


def test_latest_pass_keeps_the_label_and_says_so():
    checks = [_record(R1, False, date="2026-10-16"), _record(R1, True, date="2026-12-16",
                                                             release="R2.1", value=0.52)]
    h = predict.pilot_honesty(MODEL, pilot.run_pilot(_plan_meta()), checks)
    assert h["suppressed"] is False and h["rank_check"]["status"] == "pass", h
    assert "R2.1, 2026-12-16" in h["rank_check"]["text"], h
    assert "0.52" in h["rank_check"]["text"] and "0.40" in h["rank_check"]["text"], h


def test_latest_fail_suppresses():
    checks = [_record(R1, True, date="2026-10-16"), _record(R1, False, date="2026-10-16",
                                                            value=0.21)]
    h = predict.pilot_honesty(MODEL, pilot.run_pilot(_plan_meta()), checks)
    assert h["suppressed"] is True and h["suppressed_by"] == "rank_check", h
    assert h["rank_check"]["status"] == "fail", h
    assert "0.21" in h["suppressed_reason"] and "withheld" in h["suppressed_reason"], h
    # A record without an explicit pass is not a pass.
    rec = _record(R1, True)
    del rec["pass"]
    h2 = predict.pilot_honesty(MODEL, pilot.run_pilot(_plan_meta()), [rec])
    assert h2["suppressed"] is True, h2


def test_missing_record_fails_closed_for_other_pilots():
    h = predict.pilot_honesty(MODEL, pilot.run_pilot(_plan_meta()), None)
    assert h["suppressed"] is True and h["suppressed_by"] == "rank_record_missing", h
    with tempfile.TemporaryDirectory() as d:
        assert predict.load_rank_checks(Path(d) / "absent.json") is None
        bad = Path(d) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert predict.load_rank_checks(bad) is None
        bare = Path(d) / "bare.json"
        bare.write_text(json.dumps([_record(R1, True)]), encoding="utf-8")
        assert len(predict.load_rank_checks(bare)) == 1


def test_committed_record_and_model_are_consistent():
    checks = predict.load_rank_checks()
    assert isinstance(checks, list), "engine/models/rank_checks.json must parse"
    need = {"release", "date", "pilot", "jar_sha", "metric", "value", "threshold", "pass"}
    for c in checks:
        assert need <= set(c), (sorted(need - set(c)), c)
        assert isinstance(c["pass"], bool), c
    m = predict.Predictor.load()
    assert m is not None and predict.model_pilot(m.m) == "stock"


def test_copy_has_no_em_dash():
    metas = [{}, _plan_meta(), _plan_meta(agents=["plan", "stock", "stock", "stock"]),
             {"agent": "simlab-forge-shim/0.9.0"}]
    for checks in ([], [_record(R1, True)], [_record(R1, False)], None):
        for meta in metas:
            h = predict.pilot_honesty(MODEL, pilot.run_pilot(meta), checks)
            for s in (h["label"], h["rank_check"]["text"], h["suppressed_reason"] or ""):
                assert "—" not in s, s


# ---- the endpoint ---------------------------------------------------

def _serve(meta, checks):
    """_read_result_prediction over a synthetic two-deck run."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for name in ("Alpha", "Beta"):
            (tmp / f"{name.lower()}.dck").write_text(
                f"[metadata]\nName={name}\n[Commander]\n1 X\n[Main]\n1 Y\n",
                encoding="utf-8")
        game = {"result": {"winner": "Ai(1)-Alpha", "seats": [
            {"name": "Ai(1)-Alpha", "alive": True},
            {"name": "Ai(2)-Beta", "alive": False}]}, "turns": []}
        result = {"meta": dict(meta, decks=[str(tmp / "alpha.dck"), str(tmp / "beta.dck")]),
                  "games": [game, game],
                  "summary": {"win_rates": {"Alpha": 1.0, "Beta": 0.0}}}
        (tmp / "sim_test.json").write_text(json.dumps(result), encoding="utf-8")
        rc = tmp / "rank_checks.json"
        if checks is not None:
            rc.write_text(json.dumps({"checks": checks}), encoding="utf-8")
        saved = (mtg_engine.RESULTS_DIR, mtg_engine._deck_dirs, predict.deck_features,
                 predict.DEFAULT_RANK_CHECKS)
        mtg_engine.RESULTS_DIR = tmp
        mtg_engine._deck_dirs = lambda: [tmp]
        predict.deck_features = lambda path: {"creatures": 30, "avg_cmc": 3.5}
        predict.DEFAULT_RANK_CHECKS = rc
        try:
            return mtg_engine._read_result_prediction("sim_test.json")
        finally:
            (mtg_engine.RESULTS_DIR, mtg_engine._deck_dirs, predict.deck_features,
             predict.DEFAULT_RANK_CHECKS) = saved


def test_endpoint_match():
    out = _serve({}, [])
    assert out["available"] is True and out["pilot_match"] is True, out
    assert out["pilot"]["id"] == "stock" and out["suppressed"] is False
    assert [d["deck"] for d in out["decks"]] == ["Alpha", "Beta"], out["decks"]
    assert all(d["available"] for d in out["decks"]), out["decks"]


def test_endpoint_mismatch_no_check_yet():
    out = _serve(_plan_meta(), [])
    assert out["available"] is True and out["pilot_match"] is False, out
    assert out["label"] == "Fit on stock Forge games; this run used Sim Lab's pilot."
    assert out["rank_check"]["status"] == "none"
    assert out["model_arm"]["text"] == "stock Forge, decided games"
    assert all("expected_win_rate" in d for d in out["decks"]), out["decks"]


def test_endpoint_suppressed_has_no_figures():
    out = _serve(_plan_meta(), [_record(R1, False, value=0.21)])
    assert out["available"] is False and out["suppressed"] is True, out
    assert out["decks"] == [] and out["reason"] == out["suppressed_reason"], out
    blob = json.dumps(out)
    assert "expected_win_rate" not in blob and "sim_win_rate" not in blob, blob
    # The same record does not touch a different pilot.
    other = _serve(_plan_meta(shim="0.16.0", versions=None), [_record(R1, False)])
    assert other["available"] is True and other["rank_check"]["status"] == "none", other


def test_endpoint_missing_record_file():
    out = _serve(_plan_meta(), None)
    assert out["available"] is False and out["suppressed_by"] == "rank_record_missing", out
    assert _serve({}, None)["available"] is True


# ---- plan versions reach the result ----------------------------------

def test_adapter_and_rotated_merge_carry_plan_versions():
    meta = {"rec": "meta", "shim": "0.17.0", "humanized": True,
            "agents": ["plan", "plan"], "profiles": ["SimLabHuman"] * 2,
            "planVersions": [2, 2], "fixFlags": [V2_FLAGS, V2_FLAGS],
            "players": ["Ai(1)-A", "Ai(2)-B"]}
    res = {"rec": "result", "game": 0, "draw": False, "winner": "Ai(1)-A",
           "turns": 3, "timedOut": False, "seats": [
               {"name": "Ai(1)-A", "life": 20, "alive": True},
               {"name": "Ai(2)-B", "life": 0, "alive": False}], "ms": 1000}
    parsed = parse_shim_jsonl("\n".join(json.dumps(r) for r in (meta, res)), source="t")
    assert parsed["meta"]["planVersions"] == [2, 2], parsed["meta"]
    assert parsed["meta"]["fixFlags"][0] == V2_FLAGS
    assert pilot.run_pilot(parsed["meta"])["id"] == "plan/0.17.0/v2"
    merged = run_sim._merged_shim_meta([parsed["meta"], parsed["meta"]],
                                       [["A", "B"], ["B", "A"]])
    assert merged["rotations_detail"][1]["planVersions"] == [2, 2], merged
    whole = {"source": "rotated", "agent": "simlab-forge-shim", "humanized": True, **merged}
    assert pilot.run_pilot(whole)["id"] == "plan/0.17.0/v2", pilot.run_pilot(whole)


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
