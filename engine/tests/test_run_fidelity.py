#!/usr/bin/env python3
"""run_sim input fidelity (repair plan WS4 task 4, Appendix B task 13).

Forge refuses a card it cannot load with one stderr line and plays the deck
without it; run_sim used to discard the shim's stderr on success, so both Ral
decks were simmed for 30 games with no commander and nothing said so. This
checks that:
  - the refusal line is parsed into meta.unsupported_cards (empty when clean)
    and attributed to the deck that lists the card;
  - the shim's stderr is kept on disk on success;
  - commander fidelity follows the owner's decision of 2026-09-27: a
    commander Forge REFUSED at load (or a Commander deck file that lists none)
    makes the run polluted (commander_missing); a commander that loaded but
    never appears in any zone record gets the commander_never_cast note, which
    has a visible reason and leaves the quality alone; a commander that was
    cast is clean. Every reason is em-dash free.

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
        # the old joseph_ral: Forge refused the joined name, so it was never cast
        # BECAUSE it never loaded. That is refused, not never_cast.
        assert fid["joseph_old.dck"]["refused"] == [RAL], fid
        assert fid["joseph_old.dck"]["never_cast"] == [], fid
        assert fid["joseph_old.dck"]["basis"] == "zone_stream", fid
        # the front-face cast from the command zone is what proves presence
        assert fid["joseph_new.dck"]["seen"] == {"Ral, Monsoon Mage": 1}, fid
        assert fid["joseph_new.dck"]["missing"] == []
        # the re-converted deck's front-face name is NOT refused just because
        # another deck's joined name was: Forge reports the name as requested
        assert fid["joseph_new.dck"]["refused"] == [] and fid["joseph_new.dck"]["never_cast"] == []
        # a deck that spells the full name also counts either face's records
        full = Path(d) / "full.dck"
        full.write_text(OLD_DCK.replace("joseph_old", "joseph_new"), encoding="utf-8")
        f = run_sim.fidelity_meta(games, [full], [])["commander_fidelity"][0]
        assert f["seen"] == {RAL: 2} and f["missing"] == [], f
        assert f["refused"] == [] and f["never_cast"] == [], f
        # the refusal match ignores case (Forge's own lookup does)
        f = run_sim.fidelity_meta([], [old], [RAL.upper()])["commander_fidelity"][0]
        assert f["refused"] == [RAL], f


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
        assert fid["Beta"]["never_cast"] == ["Shared Leader"] and fid["Beta"]["refused"] == []
        # a deck whose Name= matches no zone owner at all falls back to names
        c = Path(d) / "c.dck"
        c.write_text("[metadata]\nName=Renamed\n[Commander]\n1 Shared Leader\n", encoding="utf-8")
        fid = run_sim.fidelity_meta(games, [c], [])["commander_fidelity"]
        assert fid[0]["missing"] == [], fid


def test_stdout_path_reports_refusals_but_never_a_cast_claim():
    with tempfile.TemporaryDirectory() as d:
        p, old = Path(d) / "x.dck", Path(d) / "joseph_old.dck"
        p.write_text(NEW_DCK, encoding="utf-8")
        old.write_text(OLD_DCK, encoding="utf-8")
        # the stdout log never records a card entering play, so no seen /
        # missing / never_cast; a refusal comes from stderr and holds anyway
        meta = run_sim.fidelity_meta([{"turns": []}], [p, old], [RAL], "Commander")
        fid = {f["deck"]: f for f in meta["commander_fidelity"]}
        assert fid["x.dck"] == {"deck": "x.dck", "player": "joseph_new",
                                "commanders": ["Ral, Monsoon Mage"], "refused": [],
                                "basis": "stderr"}, fid
        assert fid["joseph_old.dck"]["refused"] == [RAL], fid
        assert not {"seen", "missing", "never_cast"} & set(fid["joseph_old.dck"]), fid


def test_a_commander_deck_file_with_no_commander():
    with tempfile.TemporaryDirectory() as d:
        bare = Path(d) / "bare.dck"
        bare.write_text("[metadata]\nName=Bare\n[Main]\n1 Sol Ring\n99 Island\n",
                        encoding="utf-8")
        games = [{"zones": [zone("Sol Ring", "Bare", "Hand", "Battlefield")]}]
        f = run_sim.fidelity_meta(games, [bare], [], "Commander")["commander_fidelity"]
        assert f == [{"deck": "bare.dck", "player": "Bare", "commanders": [], "refused": [],
                      "no_commander": True, "basis": "zone_stream"}], f
        # a constructed run has no commander to miss, and an unreadable file
        # supports no claim either way
        assert run_sim.fidelity_meta(games, [bare], [], "Constructed")[
            "commander_fidelity"] == []
        assert run_sim.fidelity_meta(games, [Path(d) / "gone.dck"], [], "Commander")[
            "commander_fidelity"] == []


BASE = {"source": "rotated", "humanized": True, "clock": 900}
GAMES = [{"result": {"winner": "Ai(1)-x", "duration_ms": 1000}}] * 8
WINTER = "Winter, Cynical Opportunist"


def _assess(fid, unsupported=()):
    return validity.assess({"meta": {**BASE, "commander_fidelity": fid,
                                     "unsupported_cards": list(unsupported)},
                            "games": GAMES})


def _reason(v, flag):
    r = v["reasons"][v["flags"].index(flag)]
    assert "—" not in r, r            # no em dash in copy (CLAUDE.md)
    return r


def test_validity_refused_commander_is_polluted():
    # the joseph_ral case: Forge refused "Ral, Monsoon Mage // Ral, Leyline Prodigy"
    fid = [{"deck": "joseph_old.dck", "player": "joseph_old", "commanders": [RAL],
            "refused": [RAL], "basis": "zone_stream", "seen": {RAL: 0}, "missing": [RAL],
            "never_cast": [], "games": 8}]
    v = _assess(fid, [RAL])
    assert v["flags"] == ["commander_missing"] and v["quality"] == validity.POLLUTED, v
    assert not v["usable_for_ranking"]
    reason = _reason(v, "commander_missing")
    assert reason == (f"Forge refused to load joseph_old's commander ({RAL}) and played "
                      f"that deck without its commander. These results do not describe "
                      f"the deck as built."), reason
    # the stdout path carries the refusal without zone fields, and still pollutes
    v = _assess([{"deck": "joseph_old.dck", "player": "joseph_old", "commanders": [RAL],
                  "refused": [RAL], "basis": "stderr"}], [RAL])
    assert v["flags"] == ["commander_missing"] and v["quality"] == validity.POLLUTED, v
    # a Commander deck file that lists no commander: the same verdict
    v = _assess([{"deck": "bare.dck", "player": "Bare", "commanders": [], "refused": [],
                  "no_commander": True, "basis": "zone_stream"}])
    assert v["flags"] == ["commander_missing"] and v["quality"] == validity.POLLUTED, v
    assert "Bare's deck file lists no commander" in _reason(v, "commander_missing")


def test_validity_loaded_but_never_cast_is_a_note():
    # Winter, Cynical Opportunist: loads, and Forge's AI never casts it
    fid = [{"deck": "winter.dck", "player": "Winter Precon", "commanders": [WINTER],
            "refused": [], "basis": "zone_stream", "seen": {WINTER: 0},
            "missing": [WINTER], "never_cast": [WINTER], "games": 8}]
    v = _assess(fid)
    assert v["flags"] == ["commander_never_cast"], v
    assert v["quality"] == validity.CLEAN and v["usable_for_ranking"], v
    reason = _reason(v, "commander_never_cast")
    assert reason.startswith(f"Winter Precon's commander ({WINTER}) loaded, but Forge's AI "
                             f"never cast it in any of the 8 games"), reason
    assert "refused" not in reason and "not describe" not in reason, reason
    assert validity.summarize_flags(v) == "clean: commander_never_cast"
    # one game: the count reads naturally
    v = _assess([{**fid[0], "games": 1}])
    assert "never cast it in the one game played" in _reason(v, "commander_never_cast")
    # the note rides alongside a real verdict without softening it
    both = _assess(fid + [{"deck": "joseph_old.dck", "player": "joseph_old",
                           "commanders": [RAL], "refused": [RAL], "basis": "zone_stream",
                           "seen": {RAL: 0}, "missing": [RAL], "never_cast": [],
                           "games": 8}], [RAL])
    assert both["flags"] == ["commander_missing", "commander_never_cast"], both
    assert both["quality"] == validity.POLLUTED, both
    # zero games covered: nothing to say about casting
    assert _assess([{**fid[0], "games": 0}])["flags"] == []


def test_validity_cast_commander_is_clean():
    fid = [{"deck": "joseph_new.dck", "player": "joseph_new",
            "commanders": ["Ral, Monsoon Mage"], "refused": [], "basis": "zone_stream",
            "seen": {"Ral, Monsoon Mage": 5}, "missing": [], "never_cast": [], "games": 8}]
    v = _assess(fid)
    assert v["flags"] == [] and v["reasons"] == [] and v["quality"] == validity.CLEAN, v
    assert validity.summarize_flags(v) == "clean"
    # results from before the field existed: clean
    assert validity.assess({"meta": dict(BASE), "games": GAMES})["flags"] == []
    assert validity.VALIDITY_VERSION >= 3


def test_validity_reads_rows_written_before_the_split():
    """Rows from 2026-09-26 carry `missing` only. The split comes from the
    refusal list: Ral (refused) still pollutes, Winter (loaded) is a note."""
    old_ral = [{"deck": "joseph_old.dck", "player": "joseph_old", "commanders": [RAL],
                "seen": {RAL: 0}, "missing": [RAL], "games": 2}]
    v = _assess(old_ral, [RAL])
    assert v["flags"] == ["commander_missing"] and v["quality"] == validity.POLLUTED, v
    old_winter = [{"deck": "w.dck", "player": "w", "commanders": [WINTER],
                   "seen": {WINTER: 0}, "missing": [WINTER], "games": 2}]
    v = _assess(old_winter, [])
    assert v["flags"] == ["commander_never_cast"] and v["quality"] == validity.CLEAN, v


def test_end_to_end_from_zone_records():
    """fidelity_meta -> validity.assess for all three cases on one pod."""
    with tempfile.TemporaryDirectory() as d:
        old, new, win = (Path(d) / n for n in ("joseph_old.dck", "joseph_new.dck", "w.dck"))
        old.write_text(OLD_DCK, encoding="utf-8")
        new.write_text(NEW_DCK, encoding="utf-8")
        win.write_text(f"[metadata]\nName=Winter Precon\n[Commander]\n1 {WINTER}\n"
                       f"[Main]\n1 Sol Ring\n", encoding="utf-8")
        games = [{"zones": [zone("Ral, Monsoon Mage", "joseph_new", seat=2),
                            zone("Sol Ring", "Winter Precon", "Hand", "Battlefield", seat=3)],
                  "result": {"winner": "Ai(2)-joseph_new", "duration_ms": 1000}}] * 4
        run = lambda decks, refused: {"meta": {**BASE, **run_sim.fidelity_meta(  # noqa: E731
            games, decks, refused, "Commander")}, "games": games}
        # refused: polluted
        v = validity.assess(run([old, new], [RAL]))
        assert v["flags"] == ["commander_missing"] and v["quality"] == validity.POLLUTED, v
        assert "joseph_old" in _reason(v, "commander_missing")
        # loaded, never cast: a note, still clean
        v = validity.assess(run([new, win], []))
        assert v["flags"] == ["commander_never_cast"] and v["quality"] == validity.CLEAN, v
        assert "in any of the 4 games" in _reason(v, "commander_never_cast")
        # cast: clean, nothing to say
        v = validity.assess(run([new], []))
        assert v["flags"] == [] and v["quality"] == validity.CLEAN, v


def test_warn_fidelity_says_warning_or_note():
    import contextlib
    import io
    meta = {"commander_fidelity": [
        {"player": "joseph_old", "refused": [RAL], "never_cast": [], "games": 2},
        {"player": "Bare", "refused": [], "no_commander": True},
        {"player": "Winter Precon", "refused": [], "never_cast": [WINTER], "games": 2},
        {"player": "joseph_new", "refused": [], "never_cast": [], "games": 2}]}
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        run_sim._warn_fidelity(meta)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 3, lines
    assert lines[0].startswith("WARNING: Forge refused to load joseph_old's commander"), lines
    assert lines[1].startswith("WARNING: Bare's deck file lists no commander"), lines
    assert lines[2].startswith("NOTE: Winter Precon's commander loaded"), lines


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
