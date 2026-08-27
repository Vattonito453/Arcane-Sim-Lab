#!/usr/bin/env python3
"""Measure how often Forge actually blocks, from COMBAT log lines.

CLAUDE.md records "blocks 14% of the time" from an early measurement. This
re-measures across every committed shim run, because it is the mechanism the
prediction thesis rests on: if Forge under-blocks relative to a human table,
decks that win by attacking are systematically OVERRATED by the sim, and that
bias should appear as a correlation between a deck's aggression and its
sim-minus-human residual.

Forge phrases a block as "assigned <blockers> to block <attacker>." and a
non-block as "<player> didn't block <attacker>." -- NOT "blocked X with Y",
which is what an obvious-looking regex expects and which silently reports a
0% block rate. Attacker/blocker lists are split on each "(instance id)",
never on commas, because card names contain commas (CLAUDE.md).
"""
from __future__ import annotations
import glob, json, re, sys, collections

TO_ATTACK = re.compile(r"assigned (.+?) to attack (.+?)\.?$")
TO_BLOCK = re.compile(r"assigned (.+?) to block (.+?)\.?$")
NOBLOCK = re.compile(r"didn't block (.+?)\.?$")
REF = re.compile(r"\(\d+\)")


def n_refs(s):
    return max(1, len(REF.findall(s)))


def scan(patterns):
    files = []
    for p in patterns:
        files.extend(glob.glob(p, recursive=True))
    st = collections.Counter()
    for f in files:
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"COMBAT"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("rec") != "entry" or r.get("type") != "COMBAT":
                    continue
                for msg in (r.get("message") or "").split("\n"):
                    msg = msg.strip()
                    if not msg:
                        continue
                    m = TO_BLOCK.search(msg)
                    if m:
                        st["blocked_attackers"] += 1
                        st["blockers_used"] += n_refs(m.group(1))
                        continue
                    if NOBLOCK.search(msg):
                        st["unblocked_attackers"] += 1
                        continue
                    m = TO_ATTACK.search(msg)
                    if m:
                        st["attackers_declared"] += n_refs(m.group(1))
    return len(files), st


def main(patterns):
    nf, st = scan(patterns)
    dec = st["blocked_attackers"] + st["unblocked_attackers"]
    print(f"files              {nf}")
    print(f"attackers declared {st['attackers_declared']}")
    print(f"block decisions    {dec}  (blocked {st['blocked_attackers']}, "
          f"unblocked {st['unblocked_attackers']})")
    print(f"blockers committed {st['blockers_used']}")
    if dec:
        print(f"\nFORGE BLOCK RATE   {100*st['blocked_attackers']/dec:.1f}%"
              f"  of attacking creatures were blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["studies/**/*.jsonl"]))
