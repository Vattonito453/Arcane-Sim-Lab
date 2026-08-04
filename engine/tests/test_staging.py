#!/usr/bin/env python3
"""Deck-staging isolation tests.

Covers the failure that let two concurrent sims clobber each other's staged
decks in Forge's shared profile folder, and the stale-copy substitution that
could sim last month's decklist under the right name.

Run: python3 engine/tests/test_staging.py   (no network, no Forge, no JVM)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run_sim  # noqa: E402

DCK = "[metadata]\nName={name}\n[Commander]\n1 {cmd}\n[Main]\n99 Island\n"


def _reset() -> None:
    run_sim._PROFILE_BASE = None
    run_sim._PROFILE_IS_PRIVATE = False


def _deck(d: Path, fname: str, name: str, cmd: str = "Thassa, God of the Sea") -> None:
    (d / fname).write_text(DCK.format(name=name, cmd=cmd), encoding="utf-8")


def test_shim_runs_get_private_profiles(home: Path) -> None:
    """Two shim runs must never share a staging folder."""
    _reset()
    run_sim._init_profile("shim", "job-a")
    a, a_private = run_sim.forge_profile_deck_dir("Commander"), run_sim._PROFILE_IS_PRIVATE
    run_sim._cleanup_profile()

    _reset()
    run_sim._init_profile("shim", "job-b")
    b = run_sim.forge_profile_deck_dir("Commander")
    run_sim._cleanup_profile()

    assert a_private, "shim run should get a private profile"
    assert a != b, f"two shim runs shared a staging dir: {a}"
    # Same job id retried concurrently must still not collide.
    _reset()
    run_sim._init_profile("shim", "job-a")
    c = run_sim.forge_profile_deck_dir("Commander")
    run_sim._cleanup_profile()
    assert c != a, "a retried job id reused its staging dir"
    print("  private profiles per shim run: OK")


def test_concurrent_same_named_decks_do_not_clobber(home: Path) -> None:
    """The actual bug: same filename, different contents, both live at once."""
    src_a, src_b = home / "a", home / "b"
    src_a.mkdir(), src_b.mkdir()
    _deck(src_a, "deck.dck", "ALPHA")
    _deck(src_b, "deck.dck", "BETA")

    _reset()
    run_sim._init_profile("shim", "run-alpha")
    run_sim.stage_decks(["deck.dck"], str(src_a), "Commander")
    staged_a = run_sim.forge_profile_deck_dir("Commander") / "deck.dck"
    keep_a, base_a = staged_a.read_text(encoding="utf-8"), run_sim._PROFILE_BASE

    # Second run starts while the first is still "running" — do not clean up A.
    _reset()
    run_sim._init_profile("shim", "run-beta")
    run_sim.stage_decks(["deck.dck"], str(src_b), "Commander")
    staged_b = run_sim.forge_profile_deck_dir("Commander") / "deck.dck"
    base_b = run_sim._PROFILE_BASE

    assert "ALPHA" in keep_a and "BETA" in staged_b.read_text(encoding="utf-8")
    # The point: A's staged copy is untouched by B.
    assert "ALPHA" in staged_a.read_text(encoding="utf-8"), \
        "run B overwrote run A's staged deck -- the collision is back"
    run_sim._PROFILE_BASE, run_sim._PROFILE_IS_PRIVATE = base_a, True
    run_sim._cleanup_profile()
    run_sim._PROFILE_BASE, run_sim._PROFILE_IS_PRIVATE = base_b, True
    run_sim._cleanup_profile()
    print("  concurrent same-named decks stay separate: OK")


def test_missing_source_is_fatal_not_stale(home: Path) -> None:
    """A vanished deck must fail loudly, never fall back to an old staged copy."""
    src = home / "src"
    src.mkdir()
    _deck(src, "deck.dck", "ORIGINAL")

    _reset()
    run_sim._init_profile("shim", "run-1")
    shared = run_sim._PROFILE_BASE
    run_sim.stage_decks(["deck.dck"], str(src), "Commander")

    # Deck deleted after the job was queued; reuse the SAME profile so a stale
    # copy is present -- the exact condition the old code accepted silently.
    (src / "deck.dck").unlink()
    try:
        run_sim.stage_decks(["deck.dck"], str(src), "Commander")
    except SystemExit as e:
        assert "not found" in str(e), f"wrong error: {e}"
    else:
        raise AssertionError("missing deck silently reused a stale staged copy")
    run_sim._PROFILE_BASE, run_sim._PROFILE_IS_PRIVATE = shared, True
    run_sim._cleanup_profile()
    print("  missing source is fatal, no stale fallback: OK")


def test_cleanup_and_sweep(home: Path) -> None:
    """Private profiles are removed; crashed runs get swept later."""
    _reset()
    run_sim._init_profile("shim", "job-x")
    base = run_sim._PROFILE_BASE
    assert base and base.is_dir()
    run_sim._cleanup_profile()
    assert not base.exists(), "private profile survived cleanup"

    root = run_sim.platform_profile_base() / "simlab-runs"
    orphan = Path(tempfile.mkdtemp(prefix="crashed-", dir=root))
    old = time.time() - 48 * 3600
    os.utime(orphan, (old, old))
    assert run_sim.sweep_stale_profiles(root) >= 1
    assert not orphan.exists(), "stale profile not swept"
    print("  cleanup + stale sweep: OK")


def test_stock_agent_keeps_shared_profile(home: Path) -> None:
    """Stock Forge resolves -d from its real profile; never isolate it."""
    _reset()
    run_sim._init_profile("forge", "job-s")
    assert not run_sim._PROFILE_IS_PRIVATE, \
        "stock run was isolated; Forge would not find the decks"
    assert run_sim.forge_profile_deck_dir("Commander") == \
        run_sim.platform_profile_base() / "decks" / "commander"
    print("  stock agent keeps the shared profile: OK")


def test_pinned_forge_user_dir_is_honored(home: Path, real_base) -> None:
    """run_study.py pins FORGE_USER_DIR per worker; respect it verbatim.

    Uses the REAL platform_profile_base (the other tests stub it to sandbox the
    profile root, and that stub would mask the env var this test is about).
    """
    pinned = home / "pinned_profile"
    stub, run_sim.platform_profile_base = run_sim.platform_profile_base, real_base
    os.environ["FORGE_USER_DIR"] = str(pinned)
    try:
        _reset()
        run_sim._init_profile("shim", "job-p")
        assert not run_sim._PROFILE_IS_PRIVATE, "overrode a caller-pinned profile"
        assert run_sim.forge_profile_deck_dir("Commander") == \
            pinned / "decks" / "commander"
    finally:
        del os.environ["FORGE_USER_DIR"]
        run_sim.platform_profile_base = stub
    print("  pinned FORGE_USER_DIR honored: OK")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        # Sandbox the profile root so no test can touch a real Forge install.
        real_base = run_sim.platform_profile_base
        run_sim.platform_profile_base = lambda: home / "forge"  # type: ignore[assignment]
        try:
            for fn in (test_shim_runs_get_private_profiles,
                       test_concurrent_same_named_decks_do_not_clobber,
                       test_missing_source_is_fatal_not_stale,
                       test_cleanup_and_sweep,
                       test_stock_agent_keeps_shared_profile):
                fn(home)
            test_pinned_forge_user_dir_is_honored(home, real_base)
        finally:
            run_sim.platform_profile_base = real_base  # type: ignore[assignment]
    print("run_sim staging: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
