#!/usr/bin/env python3
"""run_sim input fidelity (repair plan WS4 task 4, Appendix B task 13).

Forge refuses a card it cannot load with one stderr line and plays the deck
without it; run_sim used to discard the shim's stderr on success, so both Ral
decks were simmed for 30 games with no commander and nothing said so. This
checks that:
  - the refusal line is parsed into meta.unsupported_cards (empty when clean)
    and attributed to the deck that lists the card;
  - the shim's stderr is kept on disk on success;
  - a seat whose commander never appears in any zone record is recorded, and
    validity.py marks such a run polluted with a visible, em-dash-free reason.

Offline: Java is replaced by a fake process. Run:
    py engine/tests/test_run_fidelity.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_sim  # noqa: E402
import validity  # noqa: E402

# The exact shape Forge 2.0.13's CardPool prints (string constants read from
# CardPool.class): 'An unsupported card was requested: "<name>" from "<set>". '
REFUSAL = 'An unsupported card was requested: "{}" from "". '
RAL = "Ral, Monsoon Mage // Ral, Leyline Prodigy"

OLD_DCK = f"""[metadata]
Name=joseph_old
[Commander]
1 {RAL}
[Main]
1 Sol Ring
1 _____ Goblin
1 Birgi, God of Storytelling // Harnfel, Horn of Bounty
"""
NEW_DCK = """[metadata]
Name=joseph_new
[Commander]
1 Ral, Monsoon Mage
[Main]
1 Sol Ring
1 _____ Goblin
1 Birgi, God of Storytelling
"""


def zone(card, owner, frm="Command", to="Stack", seat=1):
    return {"turn": 3, "phase": "MAIN1", "card": card, "cardId": 7, "from": frm, "to": to,
            "fromPlayer": f"Ai({seat})-{owner}", "toPlayer": ""}


def test_parse_refusal_lines():
    lines = ["shim: game 1 of 2", REFUSAL.format(RAL),
             REFUSAL.format("_____ Goblin") + "\n", REFUSAL.format(RAL),
             "Alchemy card not found for 'X'. Trying to get its non-Alchemy equivalent.",
             "java.lang.Exception: unrelated"]
    assert run_sim.unsupported_cards(lines) == [RAL, "_____ Goblin"]
    assert run_sim.unsupported_cards(["all clean", ""]) == []


def test_fidelity_meta_shim_path():
    with tempfile.TemporaryDirectory() as d:
        old, new = Path(d) / "joseph_old.dck", Path(d) / "joseph_new.dck"
        old.write_text(OLD_DCK, encoding="utf-8")
        new.write_text(NEW_DCK, encoding="utf-8")
        games = [{"zones": [zone("Ral, Monsoon Mage", "joseph_new", seat=2),
                            zone("Sol Ring", "joseph_old", "Hand", "Battlefield")]},
                 {"zones": [zone("Ral, Leyline Prodigy", "joseph_new", "Exile", "Battlefield",
                                 seat=1)]}]
        meta = run_sim.fidelity_meta(games, [old, new, old], [RAL, "_____ Goblin",
                                                              "Birgi, God of Storytelling // "
                                                              "Harnfel, Horn of Bounty"])
        assert meta["unsupported_cards"][0] == RAL
        assert meta["unsupported_by_deck"] == {
            "joseph_old.dck": [RAL, "_____ Goblin",
                               "Birgi, God of Storytelling // Harnfel, Horn of Bounty"],
            "joseph_new.dck": ["_____ Goblin"]}, meta["unsupported_by_deck"]
        fid = {f["deck"]: f for f in meta["commander_fidelity"]}
        assert list(fid) == ["joseph_old.dck", "joseph_new.dck"]   # one row per deck
        assert fid["joseph_old.dck"]["missing"] == [RAL], fid
        assert fid["joseph_old.dck"]["games"] == 2
        # the front-face cast from the command zone is what proves presence
        assert fid["joseph_new.dck"]["seen"] == {"Ral, Monsoon Mage": 1}, fid
        assert fid["joseph_new.dck"]["missing"] == []
        # a deck that spells the full name also counts either face's records
        full = Path(d) / "full.dck"
        full.write_text(OLD_DCK.replace("joseph_old", "joseph_new"), encoding="utf-8")
        f = run_sim.fidelity_meta(games, [full], [])["commander_fidelity"][0]
        assert f["seen"] == {RAL: 2} and f["missing"] == [], f


def test_a_shared_commander_cannot_vouch_for_another_seat():
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "a.dck", Path(d) / "b.dck"
        a.write_text("[metadata]\nName=Alpha\n[Commander]\n1 Shared Leader\n", encoding="utf-8")
        b.write_text("[metadata]\nName=Beta\n[Commander]\n1 Shared Leader\n", encoding="utf-8")
        games = [{"zones": [zone("Shared Leader", "Alpha"),
                            zone("Forest", "Beta", "Hand", "Battlefield", seat=2)]}]
        fid = {f["player"]: f for f in run_sim.fidelity_meta(games, [a, b], [])
               ["commander_fidelity"]}
        assert fid["Alpha"]["missing"] == [] and fid["Beta"]["missing"] == ["Shared Leader"], fid
        # a deck whose Name= matches no zone owner at all falls back to names
        c = Path(d) / "c.dck"
        c.write_text("[metadata]\nName=Renamed\n[Commander]\n1 Shared Leader\n", encoding="utf-8")
        fid = run_sim.fidelity_meta(games, [c], [])["commander_fidelity"]
        assert fid[0]["missing"] == [], fid


def test_stdout_path_has_no_commander_claim():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.dck"
        p.write_text(NEW_DCK, encoding="utf-8")
        meta = run_sim.fidelity_meta([{"turns": []}], [p], [])
        assert meta == {"unsupported_cards": [], "unsupported_by_deck": {}}, meta


def test_validity_marks_a_missing_commander():
    base = {"source": "rotated", "humanized": True, "clock": 900}
    games = [{"result": {"winner": "Ai(1)-x", "duration_ms": 1000}}] * 2
    fid_missing = [{"deck": "joseph_old.dck", "player": "joseph_old", "commanders": [RAL],
                    "seen": {RAL: 0}, "missing": [RAL], "games": 2}]
    v = validity.assess({"meta": {**base, "commander_fidelity": fid_missing,
                                  "unsupported_cards": [RAL]}, "games": games})
    assert "commander_missing" in v["flags"] and v["quality"] == validity.POLLUTED, v
    assert not v["usable_for_ranking"]
    reason = v["reasons"][v["flags"].index("commander_missing")]
    assert "joseph_old" in reason and "refused to load" in reason, reason
    assert "without its commander" in reason and "—" not in reason, reason
    # loaded but never cast (a commander Forge's AI refuses to play)
    fid_uncast = [{**fid_missing[0], "commanders": ["Winter, Cynical Opportunist"],
                   "missing": ["Winter, Cynical Opportunist"]}]
    v = validity.assess({"meta": {**base, "commander_fidelity": fid_uncast,
                                  "unsupported_cards": []}, "games": games})
    reason = v["reasons"][v["flags"].index("commander_missing")]
    assert "never casts" in reason and "refused to load" not in reason, reason
    # present commanders, and results from before the field existed: clean
    ok = [{**fid_missing[0], "seen": {RAL: 3}, "missing": []}]
    assert validity.assess({"meta": {**base, "commander_fidelity": ok},
                            "games": games})["flags"] == []
    assert validity.assess({"meta": dict(base), "games": games})["flags"] == []
    assert validity.VALIDITY_VERSION >= 2


class _FakeShim:
    """Stands in for the shim JVM: writes a one-game JSONL, speaks on stderr."""
    stderr_lines: list[str] = []

    def __init__(self, cmd, **kw):
        out = Path(cmd[cmd.index("--out") + 1])
        recs = [{"rec": "meta", "shim": "0.16.0", "humanized": False,
                 "players": ["Ai(1)-joseph_old", "Ai(2)-joseph_new"]},
                {"rec": "entry", "game": 0, "seq": 0, "type": "TURN",
                 "message": "Turn 1 (Ai(1)-joseph_old)"},
                {"rec": "zone", "game": 0, **zone("Ral, Monsoon Mage", "joseph_new", seat=2)},
                {"rec": "result", "game": 0, "winner": "Ai(2)-joseph_new", "ms": 1000}]
        out.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
        self.stderr = iter(self.stderr_lines)
        self.returncode = 0

    def wait(self, timeout=None):
        return 0


def test_run_shim_once_keeps_stderr_on_success():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "results"
        out.mkdir()
        args = argparse.Namespace(heap="1g", clock=900, run_id="job_1", format="Commander",
                                  max_turns=120, plans_file=None)
        _FakeShim.stderr_lines = ["shim: game 1 of 1\n", REFUSAL.format(RAL) + "\n",
                                  "some java warning\n"]
        orig = run_sim.subprocess.Popen
        run_sim.subprocess.Popen = _FakeShim
        try:
            parsed = run_sim._run_shim_once(args, str(Path(d) / "forge.jar"), "shim.jar", out,
                                            ["joseph_old.dck", "joseph_new.dck"], 1,
                                            rotate_index=0)
            _FakeShim.stderr_lines = ["shim: game 1 of 1\n"]
            clean = run_sim._run_shim_once(args, str(Path(d) / "forge.jar"), "shim.jar", out,
                                           ["joseph_new.dck"], 1, rotate_index=1)
        finally:
            run_sim.subprocess.Popen = orig
        assert parsed["meta"]["unsupported_cards"] == [RAL], parsed["meta"]
        kept = out / "shim_stderr_job_1_rot0.log"
        assert parsed["meta"]["stderr_log"] == kept.name
        text = kept.read_text(encoding="utf-8")
        assert "An unsupported card was requested" in text and "some java warning" in text
        assert "shim: game" not in text                  # progress lines are not kept
        assert clean["meta"]["unsupported_cards"] == []  # present and empty when clean
        # the kept log never matches the live-view globs for raw logs
        assert not list(out.glob("forge_raw_job_1*.log"))
        assert [p.name for p in out.glob("shim_raw_job_1*.jsonl")] == [
            "shim_raw_job_1_rot0.jsonl", "shim_raw_job_1_rot1.jsonl"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL ASSERTIONS PASSED")
