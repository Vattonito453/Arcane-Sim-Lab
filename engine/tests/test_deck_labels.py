#!/usr/bin/env python3
"""A deck picker must never render a server path.

Run: python3 engine/tests/test_deck_labels.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mtg_engine  # noqa: E402


def test_reads_the_dck_name_when_the_file_exists():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "skrat_s_revenge_239c6293.dck").write_text(
            "[metadata]\nName=Skrat's Revenge\n[Commander]\n", encoding="utf-8")
        orig = mtg_engine._deck_dirs
        mtg_engine._deck_dirs = lambda: [tmp]
        try:
            got = mtg_engine._deck_labels(
                ["/data/decks/skrat_s_revenge_239c6293.dck"])
        finally:
            mtg_engine._deck_dirs = orig
        assert got == ["Skrat's Revenge"], got


def test_falls_back_without_the_file_and_never_returns_a_path():
    with tempfile.TemporaryDirectory() as d:
        orig = mtg_engine._deck_dirs
        mtg_engine._deck_dirs = lambda: [Path(d)]
        try:
            got = mtg_engine._deck_labels([
                "/data/decks/skrat_s_revenge_239c6293.dck",
                "/app/engine/decks/kilo_helm_final.dck",
            ])
        finally:
            mtg_engine._deck_dirs = orig
    # The 8 hex import suffix is dropped; underscores become spaces.
    assert got == ["Skrat S Revenge", "Kilo Helm Final"], got
    for label in got:
        assert "/" not in label and "\\" not in label, label
        assert not label.endswith(".dck"), label


def test_parallel_to_input_and_tolerates_empty():
    assert mtg_engine._deck_labels([]) == []
    assert mtg_engine._deck_labels(None) == []
    got = mtg_engine._deck_labels(["a.dck", "b.dck", "c.dck"])
    assert len(got) == 3, got


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
