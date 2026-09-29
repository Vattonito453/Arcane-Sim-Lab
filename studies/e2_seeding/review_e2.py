#!/usr/bin/env python3
"""E2 review, post hoc (NOT pre-registered): two checks on E2's drift reading.

    py studies/e2_seeding/review_e2.py scan    # unseeded random sources in Forge's jar
    py studies/e2_seeding/review_e2.py tap     # E2 pairs with tap order normalized

scan: reads the Forge 2.0.13 jar at runtime (nothing is copied) and lists every
class under forge/ai and forge/game whose constant pool references a random
source that --seed-forge (MyRandom.setRandom) does not replace. The one E2's
own scan missed is java.util.Collections.shuffle(List): the one-argument form
draws from a private static Random in java.util.Collections, seeded from the
clock once per JVM.

tap: re-reads E2's runs with read_e2's own streams, first raw (the
pre-registered secondary measure) and then with every maximal run of
consecutive `tap` records (events) and consecutive MANA entries (log) sorted,
so a pair that tapped the same sources for one payment in a different order
is not counted as having parted. Output: $E2_OUT/runs, never into git.
"""
from __future__ import annotations

import json, struct, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_e2 as R  # noqa: E402
from run_e2 import ARMS, FORGE, MAX_TURNS, out_path  # noqa: E402

UNSEEDED = {
    ("java/util/Collections", "shuffle", "(Ljava/util/List;)V"): "Collections.shuffle(List)",
    ("java/lang/Math", "random", "()D"): "Math.random()",
    ("java/util/Random", "<init>", "()V"): "new Random()",
}
UNSEEDED_CLASSES = {"java/util/concurrent/ThreadLocalRandom": "ThreadLocalRandom",
                    "java/security/SecureRandom": "SecureRandom",
                    "java/util/SplittableRandom": "SplittableRandom"}


def member_refs(data: bytes):
    """(class, name, descriptor) of every Fieldref/Methodref in a class file."""
    n = struct.unpack(">H", data[8:10])[0]
    cp, i, pos = [None] * n, 1, 10
    sizes = {3: 5, 4: 5, 8: 3, 15: 4, 16: 3, 17: 5, 18: 5, 19: 3, 20: 3}
    while i < n:
        tag = data[pos]
        if tag == 1:
            ln = struct.unpack(">H", data[pos + 1:pos + 3])[0]
            cp[i] = data[pos + 3:pos + 3 + ln].decode("utf-8", "replace")
            pos += 3 + ln
        elif tag in (5, 6):
            pos, i = pos + 9, i + 1
        elif tag == 7:
            cp[i] = ("class", struct.unpack(">H", data[pos + 1:pos + 3])[0])
            pos += 3
        elif tag in (9, 10, 11, 12):
            cp[i] = (tag,) + struct.unpack(">HH", data[pos + 1:pos + 5])
            pos += 5
        else:
            pos += sizes[tag]
        i += 1
    out = []
    for e in cp:
        if isinstance(e, tuple) and e[0] in (9, 10, 11):
            nt = cp[e[2]]
            out.append((cp[cp[e[1]][1]], cp[nt[1]], cp[nt[2]]))
    return out


def scan():
    z = zipfile.ZipFile(FORGE)
    hits, myrandom = {}, 0
    for name in sorted(z.namelist()):
        if not (name.endswith(".class") and name.startswith(("forge/ai/", "forge/game/"))):
            continue
        refs = member_refs(z.read(name))
        myrandom += any(c == "forge/util/MyRandom" for c, _, _ in refs)
        for c, m, d in refs:
            what = UNSEEDED.get((c, m, d)) or UNSEEDED_CLASSES.get(c)
            if what:
                hits.setdefault(what, set()).add(name[:-6].replace("/", "."))
    print(f"{FORGE.name}: classes under forge/ai and forge/game that reference MyRandom: {myrandom}")
    print("references to a random source --seed-forge does not replace:")
    for what, classes in sorted(hits.items()):
        print(f"  {what}: {', '.join(sorted(classes))}")
    if not hits:
        print("  none")


def _norm(stream, is_run):
    out, run = [], []
    key = lambda x: json.dumps(x[2], sort_keys=True, default=str)
    for item in stream:
        if is_run(item[2]):
            run.append(item)
            continue
        out += sorted(run, key=key) + [item]
        run = []
    return out + sorted(run, key=key)


def _is_tap(r):
    return isinstance(r, dict) and r.get("rec") == "tap"


def _is_mana(r):
    return isinstance(r, tuple) and r[0] == "MANA"


def first_turn(ga, gb, normalize):
    sa, sb = R.streams(ga, MAX_TURNS), R.streams(gb, MAX_TURNS)
    if normalize:
        for s in (sa, sb):
            s["events"] = _norm(s["events"], _is_tap)
            s["log"] = _norm(s["log"], _is_mana)
    turns = []
    for st in R.STREAMS:
        d = R.first_diff(sa[st], sb[st])
        if d:
            turns += [t for t in (d["turn_a"], d["turn_b"]) if t is not None]
    return min(turns) if turns else None


def tap():
    for label, arm, game in (("E2 game 0", "E2", 0), ("E2 game 1 (I1)", "E2", 1), ("stock seats (I4)", "S", 0)):
        raw_same = norm_same = n = 0
        rows = []
        for k in ARMS[arm][2]:
            _, ga = R.load(out_path(arm, k, "a"))
            _, gb = R.load(out_path(arm, k, "b"))
            if game not in ga or game not in gb:
                rows.append(f"k={k} missing")
                continue
            t_raw, t_norm = first_turn(ga[game], gb[game], False), first_turn(ga[game], gb[game], True)
            n += 1
            raw_same += t_raw is None
            norm_same += t_norm is None
            if t_raw is not None:
                rows.append(f"k={k} first difference turn {t_raw}; after sorting tap runs: "
                            + ("none" if t_norm is None else f"turn {t_norm}"))
        print(f"{label}: identical through turn {MAX_TURNS} raw {raw_same}/{n}, "
              f"with tap order normalized {norm_same}/{n}")
        for r in rows:
            print("   ", r)


if __name__ == "__main__":
    {"scan": scan, "tap": tap}[sys.argv[1]]()
