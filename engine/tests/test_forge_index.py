#!/usr/bin/env python3
"""forge_index: names, layouts, AI flags and searches, read from card scripts.

Offline by construction: every card script here is a tiny synthetic one written
by this test (invented names, only the script KEYS Forge uses), zipped into a
temp directory. Forge's own cardsfolder is GPL and is never read or committed
by a test. Also asserts that no generated index file is tracked by git.

Run: py engine/tests/test_forge_index.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent
sys.path.insert(0, str(ENGINE))

import forge_index as fi  # noqa: E402

SCRIPTS = {
    # single-faced, flagged spell
    "g/grim_consult.txt": "Name:Grim Consult\nManaCost:B\nTypes:Instant\n"
                          "A:SP$ Dig | DigNum$ 6 | SpellDescription$ x\nAI:RemoveDeck:All\n",
    # library-top tutor: a search with Destination Library
    "t/top_tutor.txt": "Name:Top Tutor\nTypes:Instant\n"
                       "A:SP$ ChangeZone | Origin$ Library | Destination$ Library | "
                       "LibraryPosition$ 0 | ChangeType$ Card | ChangeNum$ 1\nAI:RemoveDeck:All\n"
                       "AI:RemoveDeck:Random\n",
    # flagged counterspell: Forge's pre-pass still casts it
    "n/null_pact.txt": "Name:Null Pact\nTypes:Instant\n"
                       "A:SP$ Counter | TargetType$ Spell | ValidTgts$ Card\nAI:RemoveDeck:All\n",
    # flagged artifact with a non-mana activation, and one with a mana ability
    "t/tick_clock.txt": "Name:Tick Clock\nTypes:Artifact\n"
                        "A:AB$ Untap | Cost$ tapXType<2/Artifact> | ValidTgts$ Artifact\n"
                        "AI:RemoveDeck:All\n",
    "e/eye_gem.txt": "Name:Eye Gem\nTypes:Artifact\n"
                     "A:AB$ Mana | Cost$ Sac<1/CARDNAME> | Produced$ Any | Amount$ 3\n"
                     "AI:RemoveDeck:All\n",
    # flagged legendary creature: a commander nobody's AI casts
    "w/wintry_schemer.txt": "Name:Wintry Schemer\nTypes:Legendary Creature Human Warlock\n"
                            "PT:2/5\nAI:RemoveDeck:All\n",
    # flagged land: still played, only its activation is filtered
    "f/flag_vault.txt": "Name:Flag Vault\nTypes:Land\n"
                        "A:AB$ Draw | Cost$ T | NumCards$ 1\nAI:RemoveDeck:All\n",
    # unflagged combo piece; its "search" is a Dig, not a ChangeZone
    "o/oracle_of_tides.txt": "Name:Oracle of Tides\nTypes:Creature Merfolk Wizard\n"
                             "T:Mode$ ChangesZone | Execute$ TrigDig\n"
                             "SVar:TrigDig:DB$ Dig | DigNum$ X | ChangeNum$ 1\n",
    # transform DFC (the Ral case)
    "s/storm_mage_storm_prodigy.txt":
        "Name:Storm Mage\nTypes:Legendary Creature Human Wizard\nAlternateMode:DoubleFaced\n"
        "\nALTERNATE\n\nName:Storm Prodigy\nTypes:Legendary Planeswalker Storm\n",
    # modal DFC with a land back (the Sea Gate case)
    "t/tide_restoration_tide_reborn.txt":
        "Name:Tide Restoration\nTypes:Sorcery\nAlternateMode:Modal\n"
        "\nALTERNATE\n\nName:Tide, Reborn\nTypes:Land\n",
    # split card: Forge names it "A // B"
    "h/heat_chill.txt": "Name:Heat\nTypes:Instant\nAlternateMode:Split\n"
                        "\nALTERNATE\n\nName:Chill\nTypes:Instant\n",
    # a second split card sharing the face "Heat", borrowed with CopyFaceFrom
    "b/begin_heat.txt": "CopyFaceFrom:Begin\nAlternateMode:Split\n"
                        "\nALTERNATE\n\nCopyFaceFrom:Heat\n",
    # adventure: Forge loads it by the creature face
    "g/giant_stomper_stomp.txt": "Name:Giant Stomper\nTypes:Creature Giant\n"
                                 "AlternateMode:Adventure\n\nALTERNATE\n\n"
                                 "Name:Stomp\nTypes:Instant Adventure\n",
    # a real card whose name is also another card's face: the real card wins
    "c/chill.txt": "Name:Chill\nTypes:Enchantment\n",
    # specialize: several faces, loaded by the base face
    "a/ally_rogue.txt": "Name:Ally Rogue\nTypes:Legendary Creature Halfling Rogue\n"
                        "AlternateMode:Specialize\n\nSPECIALIZE:WHITE\n\n"
                        "Name:Ally, White Rogue\nTypes:Legendary Creature Halfling Rogue\n",
    # accented name
    "l/lim_dul_s_hoard.txt": "Name:Lim-Dûl's Hoard\nTypes:Instant\n",
    # activated tutor, trigger tutor via SVar, transmute and typecycling
    "p/pod_engine.txt": "Name:Pod Engine\nTypes:Artifact\n"
                        "A:AB$ ChangeZone | Cost$ 1 T Sac<1/Creature> | Origin$ Library | "
                        "Destination$ Battlefield | ChangeType$ Creature.cmcEQX | ChangeNum$ 1\n",
    "b/bandit_lord.txt": "Name:Bandit Lord\nTypes:Legendary Creature Human\n"
                         "SVar:TrigTutor:DB$ ChangeZone | Origin$ Library | Destination$ "
                         "Battlefield | ChangeType$ Equipment | ChangeNum$ 1\n"
                         # a Defined move from the library is not a search
                         "SVar:TrigTop:DB$ ChangeZone | Defined$ TopOfLibrary | Origin$ Library | "
                         "Destination$ Hand\n"
                         # a graveyard move is not a library search
                         "SVar:TrigYard:DB$ ChangeZone | Origin$ Graveyard | Destination$ Hand | "
                         "ChangeType$ Card\n",
    "m/muddle_spell.txt": "Name:Muddle Spell\nTypes:Instant\n"
                          "A:SP$ Counter | TargetType$ Spell | ValidTgts$ Instant\n"
                          "K:Transmute:1 U U\n",
    "s/swamp_cycler.txt": "Name:Swamp Cycler\nTypes:Creature Horror\nK:TypeCycling:Swamp:2\n",
    "k/king_background.txt": "Name:Noble Background\nTypes:Legendary Enchantment Background\n",
    "p/plain_rock.txt": "Name:Plain Rock\nTypes:Artifact\n",
}


def make_zip(folder: Path) -> Path:
    z = folder / "res" / "cardsfolder" / "cardsfolder.zip"
    z.parent.mkdir(parents=True)
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/", "")
        for name, text in SCRIPTS.items():
            zf.writestr(name, text)
    return z


def make_dir(folder: Path) -> Path:
    d = folder / "res" / "cardsfolder"
    for name, text in SCRIPTS.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


def check_data(cards, flags, tutors, counts):
    assert counts["scripts"] == len(SCRIPTS) and counts["unparsed"] == 0, counts
    # canonical names: split joined, everything else by its first face
    assert cards["Storm Mage"]["mode"] == "DoubleFaced", cards["Storm Mage"]
    assert cards["Storm Mage"]["faces"] == ["Storm Mage", "Storm Prodigy"]
    assert cards["Tide Restoration"]["mode"] == "Modal"
    assert cards["Heat // Chill"]["mode"] == "Split"
    assert cards["Begin // Heat"]["faces"] == ["Begin", "Heat"]
    assert cards["Giant Stomper"]["mode"] == "Adventure"
    assert cards["Ally Rogue"]["mode"] == "Specialize"
    assert cards["Plain Rock"] == {"mode": None, "types": "Artifact"}, cards["Plain Rock"]
    assert "Storm Prodigy" not in cards and "Heat" not in cards
    # flags: what the RemoveDeck filter takes away
    assert set(flags) == {"Grim Consult", "Top Tutor", "Null Pact", "Tick Clock", "Eye Gem",
                          "Wintry Schemer", "Flag Vault"}, sorted(flags)
    assert flags["Grim Consult"]["kinds"] == ["spell"]
    assert flags["Null Pact"]["kinds"] == ["counterspell"]
    assert flags["Tick Clock"]["kinds"] == ["spell", "activation"]
    assert flags["Eye Gem"]["kinds"] == ["spell", "mana"]
    assert flags["Wintry Schemer"]["kinds"] == ["spell", "commander"]
    assert flags["Flag Vault"] == {"remove": "All", "kinds": ["activation"], "land": True}
    assert "Oracle of Tides" not in flags
    assert counts["flagged_all"] == 7 and counts["flagged_random"] == 1, counts
    # searches
    assert tutors["Top Tutor"] == [{"face": "Top Tutor", "via": "SP", "api": "ChangeZone",
                                    "origin": "Library", "destination": "Library",
                                    "change_type": "Card", "change_num": "1",
                                    "library_position": "0"}], tutors["Top Tutor"]
    assert tutors["Pod Engine"][0]["via"] == "AB"
    assert tutors["Pod Engine"][0]["cost"] == "1 T Sac<1/Creature>"
    assert [t.get("svar") for t in tutors["Bandit Lord"]] == ["TrigTutor"], tutors["Bandit Lord"]
    assert tutors["Muddle Spell"][0]["keyword"] == "Transmute"
    assert tutors["Swamp Cycler"][0]["change_type"] == "Swamp"
    assert "Oracle of Tides" not in tutors and "Grim Consult" not in tutors


def test_build_data_zip_and_dir_agree():
    with tempfile.TemporaryDirectory() as d:
        z = make_zip(Path(d) / "zip")
        from_zip = fi.build_data(z)
        check_data(*from_zip)
        folder = make_dir(Path(d) / "dir")
        from_dir = fi.build_data(folder)
        assert from_zip[:3] == from_dir[:3], "zip and unzipped folder must index the same"


def test_version_from_jar_name():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d)
        make_zip(home)
        (home / "forge-gui-desktop-9.9.9-jar-with-dependencies.jar").write_bytes(b"")
        saved = {k: os.environ.pop(k, None) for k in ("FORGE_JAR", "FORGE_HOME")}
        try:
            os.environ["FORGE_HOME"] = str(home)
            assert fi.find_forge_home() == home
            assert fi.find_cardsfolder(home).name == "cardsfolder.zip"
            assert fi.forge_version(home) == "9.9.9", fi.forge_version(home)
            # the container points FORGE_JAR at a version-less symlink; the
            # version comes from its target (symlinks may need privileges on
            # Windows, so this half is best-effort)
            link = home / "forge.jar"
            try:
                link.symlink_to(home / "forge-gui-desktop-9.9.9-jar-with-dependencies.jar")
                os.environ["FORGE_JAR"] = str(link)
                assert fi.forge_version(home) == "9.9.9"
            except (OSError, NotImplementedError):
                pass
            os.environ.pop("FORGE_JAR", None)
            (home / "forge-gui-desktop-9.9.9-jar-with-dependencies.jar").unlink()
            v = fi.forge_version(home)
            assert v.startswith("unknown-"), v     # no jar: a content-derived tag
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


class _Root:
    """Point the module at a temp data dir and a temp Forge home."""

    def __init__(self, home: Path | None, data: Path) -> None:
        self.home, self.data = home, data

    def __enter__(self):
        self.saved_root = fi.INDEX_ROOT
        self.saved_env = {k: os.environ.pop(k, None) for k in ("FORGE_JAR", "FORGE_HOME")}
        self.saved_cands = fi.FORGE_HOME_CANDIDATES
        fi.INDEX_ROOT = self.data / "forge_index"
        fi.FORGE_HOME_CANDIDATES = ()
        fi._loaded.clear()
        if self.home is not None:
            os.environ["FORGE_HOME"] = str(self.home)
        return self

    def __exit__(self, *exc):
        fi.INDEX_ROOT = self.saved_root
        fi.FORGE_HOME_CANDIDATES = self.saved_cands
        fi._loaded.clear()
        for k, v in self.saved_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_ensure_build_load_and_resolve():
    with tempfile.TemporaryDirectory() as d:
        home, data = Path(d) / "forge", Path(d) / "data"
        make_zip(home)
        (home / "forge-gui-desktop-1.2.3-jar-with-dependencies.jar").write_bytes(b"")
        with _Root(home, data):
            assert fi.load_index() is None                     # nothing built yet
            res = fi.ensure_index()
            assert res["status"] == "built" and res["version"] == "1.2.3", res
            out = data / "forge_index" / "1.2.3"
            assert sorted(p.name for p in out.iterdir()) == [
                "cards.json", "flags.json", "meta.json", "tutors.json"]
            meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
            assert meta["schema"] == fi.INDEX_SCHEMA and meta["forge_version"] == "1.2.3"
            assert fi.ensure_index()["status"] == "ok"         # present: no rebuild
            # no leftover temp directories
            assert [p.name for p in (data / "forge_index").iterdir()] == ["1.2.3"]

            idx = fi.load_index()
            assert idx is not None and idx.version == "1.2.3"
            assert fi.load_index() is idx                      # reused while unchanged
            r = idx.resolve
            assert r("Storm Mage // Storm Prodigy") == "Storm Mage"   # transform -> front
            assert r("Tide Restoration // Tide, Reborn") == "Tide Restoration"  # modal land
            assert r("Giant Stomper // Stomp") == "Giant Stomper"     # adventure
            assert r("Heat // Chill") == "Heat // Chill"              # split keeps " // "
            assert r("heat // chill") == "Heat // Chill"              # case-insensitive
            assert r("Storm Prodigy") == "Storm Mage"                 # a lone back face
            assert r("Chill") == "Chill"                              # the real card wins
            assert r("Heat") is None                                  # face of two cards
            assert r("Lim-Dul's Hoard") == "Lim-Dûl's Hoard"     # accents folded
            assert r("Ally, White Rogue") == "Ally Rogue"
            assert r("Nothing Like This") is None
            assert r("Storm Mage // Wrong Back") == "Storm Mage"
            assert r("Plain Rock // Other") is None                   # not a multi-face card
            assert idx.flag("Wintry Schemer")["kinds"] == ["spell", "commander"]
            assert idx.tutors()["Top Tutor"][0]["destination"] == "Library"

            # schema mismatch: not an index any more, and ensure rebuilds it
            meta["schema"] = fi.INDEX_SCHEMA + 99
            (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            assert not fi.is_built("1.2.3") and fi.load_index() is None
            assert fi.ensure_index()["status"] == "built"
            assert fi.is_built("1.2.3")

            # a directory without meta.json (a half-written index) is ignored
            (out / "meta.json").unlink()
            assert fi.load_index() is None


def test_api_side_reads_newest_without_forge():
    """The API container has no Forge: it reads the newest complete index on
    the shared volume, which the worker built."""
    with tempfile.TemporaryDirectory() as d:
        home, data = Path(d) / "forge", Path(d) / "data"
        make_zip(home)
        (home / "forge-gui-desktop-4.5.6-jar-with-dependencies.jar").write_bytes(b"")
        with _Root(home, data):
            assert fi.ensure_index()["status"] == "built"
        with _Root(None, data):
            assert fi.find_forge_home() is None
            idx = fi.load_index()
            assert idx is not None and idx.version == "4.5.6", idx


def test_worker_side_never_raises():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d) / "data"
        with _Root(None, data):
            assert fi.ensure_index()["status"] == "no_forge"
        home = Path(d) / "broken"
        z = home / "res" / "cardsfolder" / "cardsfolder.zip"
        z.parent.mkdir(parents=True)
        z.write_bytes(b"this is not a zip")
        with _Root(home, data):
            res = fi.ensure_index()
            assert res["status"] == "error" and "BadZipFile" in res["message"], res
            logs: list[str] = []
            t = fi.ensure_index_async(log=logs.append)
            t.join(timeout=30)
            assert not t.is_alive() and t.daemon
            assert logs and logs[0].startswith("forge_index: error"), logs
    # the async path builds when it can
    with tempfile.TemporaryDirectory() as d:
        home, data = Path(d) / "forge", Path(d) / "data"
        make_zip(home)
        with _Root(home, data):
            logs = []
            fi.ensure_index_async(log=logs.append).join(timeout=30)
            assert logs and logs[0].startswith("forge_index: built"), logs
            assert fi.load_index() is not None


def test_worker_startup_calls_it_without_blocking():
    """worker.loop() starts the index build before its first claim, on a
    daemon thread, and a failure to even import it is only logged."""
    import worker
    calls: list[str] = []
    real = fi.ensure_index_async
    fi.ensure_index_async = lambda log=print: calls.append("async")
    try:
        worker._start_forge_index()
        assert calls == ["async"], calls
        fi.ensure_index_async = lambda log=print: (_ for _ in ()).throw(RuntimeError("boom"))
        worker._start_forge_index()                          # must not raise
    finally:
        fi.ensure_index_async = real


def test_flagged_share_counting_rule():
    with tempfile.TemporaryDirectory() as d:
        home, data = Path(d) / "forge", Path(d) / "data"
        make_zip(home)
        with _Root(home, data):
            fi.ensure_index()
            idx = fi.load_index()
            deck = ("[metadata]\nName=t\n[Commander]\n1 Wintry Schemer|SET|1\n[Main]\n"
                    "1 Grim Consult\n2 Plain Rock\n1 Flag Vault\n1 Tide Restoration // Tide, Reborn\n"
                    "1 Nothing Like This\n[Sideboard]\n1 Top Tutor\n")
            res = fi.flagged_share(idx, [deck])
            # nonland: Schemer, Consult, 2x Rock, Tide (spell front) = 5; lands
            # and unknowns out; the sideboard is not the deck
            assert res["nonland"] == 5 and res["flagged"] == 2 and res["unknown"] == 1, res
            assert res["share"] == 0.4


def test_generated_index_is_never_tracked():
    """The index is derived from Forge's GPL scripts: never in git."""
    if shutil.which("git") is None or not (REPO / ".git").exists():
        print("  (git unavailable: tracked-file check skipped)")
        return
    tracked = subprocess.run(["git", "ls-files", "--", "engine/forge_index", "forge_index"],
                             cwd=REPO, capture_output=True, text=True).stdout.split()
    assert tracked == [], tracked
    ign = subprocess.run(["git", "check-ignore", "-q", "engine/forge_index/2.0.13/cards.json"],
                         cwd=REPO)
    assert ign.returncode == 0, "engine/forge_index/ must be gitignored"
    # and nothing that looks like a generated index file anywhere else
    all_tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                                 text=True).stdout.splitlines()
    leaked = [p for p in all_tracked if "/forge_index/" in f"/{p}"]
    assert leaked == [], leaked


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL ASSERTIONS PASSED")
