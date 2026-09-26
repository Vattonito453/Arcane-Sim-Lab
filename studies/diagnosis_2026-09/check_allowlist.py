#!/usr/bin/env python3
"""Allowlist check for studies/diagnosis_2026-09 (repair plan WS0 task 1,
Appendix B task 3).

Every file git tracks under this folder must be:
  - a .py, .md, .json or .txt file (the folder's own .gitignore is the one
    exception; Appendix B task 3 requires it);
  - at most 1 MB (1,048,576 bytes);
  - free of Forge-derived content markers: the class-file magic bytes
    CA FE BA BE, a javap header, or a Java package declaration for forge or
    simlab.
It also fails if any tracked path sits in a folder that must stay off-repo
(gs/, gs2/, jarx/, shimcopy/, richard/, local/, __pycache__/).

Content is read from the git index, so the check judges what a commit would
contain, not what happens to be on disk. Stage first, then run:

    git add studies/diagnosis_2026-09
    py studies/diagnosis_2026-09/check_allowlist.py

Options:
  --all      also check untracked files git would pick up (not ignored), read
             from disk, so a problem is caught before `git add`.
  --archive  also verify the off-repo archive named in README.md exists and
             matches the SHA-256 recorded there (only meaningful on the dev box).

Exit 0 and "ALLOWLIST CHECK PASSED" when clean; exit 1 and one line per
violation otherwise. Stdlib only; runs on the dev box's Python 3.8.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWED_EXT = {".py", ".md", ".json", ".txt"}
ALLOWED_EXTRA = {".gitignore"}          # exact relative paths, folder root only
MAX_BYTES = 1024 * 1024
# Built by concatenation so this file does not trip its own content check.
MARKERS = [
    (bytes.fromhex("cafebabe"), "class-file magic bytes CAFEBABE"),
    (b"Compiled" + b" from", "javap header"),
    (b"package" + b" forge", "Java package declaration (forge)"),
    (b"package" + b" simlab", "Java package declaration (simlab)"),
]
FORBIDDEN_DIRS = {"gs", "gs2", "jarx", "shimcopy", "richard", "local", "__pycache__"}


def _git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(HERE), *args], input=data,
                          capture_output=True, check=True).stdout


def tracked() -> list[tuple[str, str, str]]:
    """(mode, blob sha, path relative to this folder) for every index entry."""
    out = []
    for rec in _git("ls-files", "-s", "-z", "--", ".").split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, sha, _stage = meta.decode().split()
        out.append((mode, sha, path.decode("utf-8")))
    return out


def untracked() -> list[str]:
    raw = _git("ls-files", "-z", "--others", "--exclude-standard", "--", ".")
    return [p.decode("utf-8") for p in raw.split(b"\0") if p]


def read_blobs(shas: list[str]) -> dict[str, bytes]:
    """Read many blobs through one `git cat-file --batch` process."""
    if not shas:
        return {}
    raw = _git("cat-file", "--batch", data=("\n".join(shas) + "\n").encode())
    blobs, i = {}, 0
    for sha in shas:
        nl = raw.index(b"\n", i)
        header = raw[i:nl].split()
        size = int(header[2])
        blobs[sha] = raw[nl + 1:nl + 1 + size]
        i = nl + 1 + size + 1
    return blobs


def violations(path: str, data: bytes, mode: str = "100644") -> list[str]:
    bad = []
    parts = path.split("/")
    if set(parts[:-1]) & FORBIDDEN_DIRS:
        bad.append("inside an off-repo folder (" +
                   ", ".join(sorted(set(parts[:-1]) & FORBIDDEN_DIRS)) + ")")
    if mode not in ("100644", "100755"):
        bad.append(f"not a regular file (mode {mode})")
    suffix = Path(path).suffix.lower()
    if path not in ALLOWED_EXTRA and suffix not in ALLOWED_EXT:
        bad.append(f"extension {suffix or '(none)'} is not .py/.md/.json/.txt")
    if len(data) > MAX_BYTES:
        bad.append(f"{len(data):,} bytes is over the 1 MB cap")
    for marker, label in MARKERS:
        if marker in data:
            bad.append(f"contains {label}")
    return bad


def check_archive() -> list[str]:
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    m_path = re.search(r"`(C:\\[^`]*diagnosis_2026-09\.zip)`", readme)
    m_hash = re.search(r"\b([0-9a-f]{64})\b", readme)
    if not (m_path and m_hash):
        return ["README.md does not record the archive path and SHA-256"]
    zpath = Path(m_path.group(1))
    if not zpath.is_file():
        return [f"archive not found at {zpath}"]
    h = hashlib.sha256()
    with open(zpath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != m_hash.group(1):
        return [f"archive SHA-256 {h.hexdigest()} does not match README {m_hash.group(1)}"]
    return []


def main(argv: list[str]) -> int:
    problems: list[str] = []
    entries = tracked()
    blobs = read_blobs([sha for _mode, sha, _p in entries])
    for mode, sha, path in entries:
        problems += [f"{path}: {v}" for v in violations(path, blobs[sha], mode)]
    extra = untracked() if "--all" in argv else []
    for path in extra:
        data = (HERE / path).read_bytes()
        problems += [f"{path} (untracked): {v}" for v in violations(path, data)]
    if "--archive" in argv:
        problems += [f"archive: {p}" for p in check_archive()]

    if not entries:
        problems.append("no tracked files under this folder (stage them first)")
    for p in problems:
        print("FAIL  " + p)
    if problems:
        print(f"allowlist check FAILED: {len(problems)} problem(s)")
        return 1
    note = f", {len(extra)} untracked" if extra else ""
    print(f"{len(entries)} tracked files{note} checked")
    print("ALLOWLIST CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
