#!/usr/bin/env python3
"""E2 reader (see PREREG.md): the pre-registered reading of run_e2.py's output.

    py studies/e2_seeding/read_e2.py [--json reading.json]

Primary: game 0 of replicate a against replicate b, per seed, on the opening
deal, the first player and the first mulligan decision; E2 passes at 10/10.
Secondary: each pair's first divergence point (events, log, agent streams,
turn <= the cap). Informative: I1 (second game of a cell), I2 (seed + g x
stride across JVMs), I3 (G0a's own C/T pairing, read from $G0A_OUT/runs) and
I4 (stock seats). Richard's pod appears in I3 as counts only: their
decklists are user data, so no card name from it is ever printed.
"""
from __future__ import annotations

import json, re, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_e2 import ARMS, G0A, MAX_TURNS, OUT, STRIDE, git, out_path, seed  # noqa: E402

TAP = {"zone", "tap", "counters", "attach", "rubric"}
TURN_RE = re.compile(r"^Turn (\d+) \((.*)\)$")
STREAMS = ("events", "log", "agent")


def load(path: Path):
    """(meta, {game: {events, log, agent, result}}), or (None, {}) if absent."""
    meta, games = None, {}
    if not path.exists():
        return None, games
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rec = r.get("rec")
        if rec == "meta":
            meta = r
            continue
        g = r.get("game")
        if g is None:
            continue
        d = games.setdefault(g, {"events": [], "log": [], "agent": [], "result": None})
        if rec in TAP:
            d["events"].append(r)
        elif rec == "entry":
            d["log"].append(r)
        elif rec == "agent":
            d["agent"].append(r)
        elif rec == "result":
            d["result"] = r
    for d in games.values():
        d["log"].sort(key=lambda e: e.get("seq", 0))
    return meta, games


def primary(game, players):
    """The pre-registered object, or (None, reason) when malformed."""
    if game is None or game["result"] is None:
        return None, "no game record"
    deal = []
    for r in game["events"]:
        if r.get("rec") != "zone":
            continue
        if r.get("turn") == 0 and r.get("from") == "Library" and r.get("to") == "Hand":
            deal.append((r.get("toPlayer"), r.get("cardId"), r.get("card")))
        else:
            break
    counts = Counter(p for p, _, _ in deal)
    if players and dict(counts) != {p: 7 for p in players}:
        return None, f"deal is not 7 per seat: {dict(counts)}"
    first = next((e.get("message") for e in game["log"] if e.get("type") == "TURN"), None)
    decision = next((e.get("message") for e in game["log"] if e.get("type") == "MULLIGAN"), None)
    if first is None or decision is None:
        return None, "no TURN or MULLIGAN entry"
    m = TURN_RE.match(first)
    return {"deal": deal, "first_player": m.group(2) if m else first,
            "first_decision": decision}, None


def _strip(r):
    return {k: v for k, v in r.items() if k != "game"}


def streams(game, cap):
    """Each stream as [(turn, phase, comparable)], records with turn <= cap."""
    out = {s: [] for s in STREAMS}
    t = 0
    for r in game["events"]:
        t = r.get("turn", t)
        if t <= cap:
            out["events"].append((t, r.get("phase", ""), _strip(r)))
    t, phase = 0, ""
    for e in game["log"]:
        if e.get("type") == "TURN":
            m = TURN_RE.match(e.get("message", ""))
            if m:
                t = int(m.group(1))
        elif e.get("type") == "PHASE":
            phase = e.get("message", "")
        if t <= cap:
            out["log"].append((t, phase, (e.get("type"), e.get("message"), e.get("card"), e.get("cardId"))))
    t = 0
    for r in game["agent"]:
        t = r.get("turn", t)
        if t <= cap:
            out["agent"].append((t, "", _strip(r)))
    return out


def _short(x, n=240):
    s = json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x
    return s if len(s) <= n else s[: n - 3] + "..."


def first_diff(sa, sb):
    for i in range(max(len(sa), len(sb))):
        a = sa[i] if i < len(sa) else None
        b = sb[i] if i < len(sb) else None
        if a is None or b is None or a[2] != b[2]:
            return {"index": i,
                    "turn_a": a and a[0], "turn_b": b and b[0],
                    "phase_a": a and a[1], "phase_b": b and b[1],
                    "rec_a": None if a is None else a[2], "rec_b": None if b is None else b[2],
                    "len_a": len(sa), "len_b": len(sb)}
    return None


def divergence(ga, gb, cap):
    sa, sb = streams(ga, cap), streams(gb, cap)
    per = {s: first_diff(sa[s], sb[s]) for s in STREAMS}
    turns = [t for d in per.values() if d for t in (d["turn_a"], d["turn_b"]) if t is not None]
    return {"streams": per, "first_turn": min(turns) if turns else None,
            "lens": {s: (len(sa[s]), len(sb[s])) for s in STREAMS}}


def result_of(game):
    r = (game or {}).get("result") or {}
    return {k: r.get(k) for k in ("winner", "turns", "turnCapped", "timedOut", "killFailed", "error")
            if k in r}


def compare_pair(ga, gb, players, cap, names=True):
    pa, ra = primary(ga, players)
    pb, rb = primary(gb, players)
    row = {"identical": pa is not None and pb is not None and pa == pb,
           "malformed": [x for x in (ra, rb) if x]}
    if pa and pb:
        row["deal_same"] = pa["deal"] == pb["deal"]
        row["first_player_same"] = pa["first_player"] == pb["first_player"]
        row["first_decision_same"] = pa["first_decision"] == pb["first_decision"]
        if names:
            row["first_player"] = [pa["first_player"], pb["first_player"]]
            row["first_decision"] = [pa["first_decision"], pb["first_decision"]]
    if ga is not None and gb is not None and ga["result"] and gb["result"]:
        div = divergence(ga, gb, cap)
        row["first_divergence_turn"] = div["first_turn"]
        row["lens"] = div["lens"]
        if names:
            row["divergence"] = div["streams"]
        else:  # counts only (user data): no records
            row["divergence"] = {s: d and {k: d[k] for k in ("index", "turn_a", "turn_b")}
                                 for s, d in div["streams"].items()}
        row["results"] = [result_of(ga), result_of(gb)]
    return row


def cell_meta(path: Path):
    p = path.with_suffix(".cell.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- readings

def read_pairs(arm, game_index):
    rows = []
    for k in ARMS[arm][2]:
        ma, ga = load(out_path(arm, k, "a"))
        mb, gb = load(out_path(arm, k, "b"))
        players = (ma or mb or {}).get("players")
        row = {"k": k, "seed": seed(k),
               "seed_echo": [(ma or {}).get("seedForge"), (mb or {}).get("seedForge")],
               "cells": [cell_meta(out_path(arm, k, r)) and
                         {x: cell_meta(out_path(arm, k, r))[x] for x in ("rc", "attempt", "started", "games_with_result")}
                         for r in ("a", "b")]}
        row.update(compare_pair(ga.get(game_index), gb.get(game_index), players, MAX_TURNS))
        rows.append(row)
    return rows


def read_i2():
    rows = []
    ks = ARMS["E2"][2]
    for k in ks[:-1]:
        for rep in ("a", "b"):
            m1, g1 = load(out_path("E2", k, rep))
            m0, g0 = load(out_path("E2", k + 1, rep))
            players = (m1 or m0 or {}).get("players")
            p1, r1 = primary(g1.get(1), players)
            p0, r0 = primary(g0.get(0), players)
            row = {"k": k, "rep": rep, "forge_seed": seed(k) + STRIDE, "vs_seed": seed(k + 1),
                   "malformed": [x for x in (r1, r0) if x]}
            if p1 and p0:
                row["deal_same"] = p1["deal"] == p0["deal"]
                row["deal_names_same"] = [(p, c) for p, _, c in p1["deal"]] == [(p, c) for p, _, c in p0["deal"]]
                row["first_player_same"] = p1["first_player"] == p0["first_player"]
                row["first_decision_same"] = p1["first_decision"] == p0["first_decision"]
            rows.append(row)
    return rows


def _seed_flag(cell):
    cmd = (cell or {}).get("cmd", [])
    return cmd[cmd.index("--seed-forge") + 1] if "--seed-forge" in cmd else None


def read_i3():
    """G0a's C/T pairing, from G0a's own output (no new games)."""
    out = {"cells": [], "by_bed": {}}
    tdir, cdir = G0A / "runs" / "T", G0A / "runs" / "C"
    for tf in sorted(tdir.glob("*.jsonl")):
        cf = cdir / tf.name
        if not cf.exists():
            continue
        bed = tf.stem.rsplit("_rot", 1)[0]
        names = bed != "richard"
        tc, cc = cell_meta(tf), cell_meta(cf)
        mt, gt = load(tf)
        mc, gc = load(cf)
        players = (mt or {}).get("players")
        cap = (mt or {}).get("maxTurns") or 120
        seeds = [_seed_flag(cc), _seed_flag(tc)]
        for g in sorted(set(gt) & set(gc)):
            row = compare_pair(gc[g], gt[g], players, cap, names=False)
            row.update({"bed": bed, "cell": tf.stem, "game": g, "seeds_CT": seeds,
                        "seed_same": seeds[0] is not None and seeds[0] == seeds[1]})
            # what ended the game before this one in each arm (a kill that
            # failed could leave a thread drawing from this game's generator)
            row["prev_end_CT"] = [result_of(gc.get(g - 1)) if g else None,
                                  result_of(gt.get(g - 1)) if g else None]
            row.pop("first_player", None)
            row.pop("first_decision", None)
            out["cells"].append(row)
        out["by_bed"].setdefault(bed, Counter())
    for row in out["cells"]:
        b = out["by_bed"][row["bed"]]
        b["games"] += 1
        b["seed_same"] += row["seed_same"]
        for f in ("deal_same", "first_player_same", "first_decision_same", "identical"):
            b[f] += bool(row.get(f))
    out["by_bed"] = {k: dict(v) for k, v in out["by_bed"].items()}
    def _bin(t):
        return "none" if t is None else ("0" if t == 0 else "1-4" if t <= 4 else "5-12" if t <= 12 else "13+")

    ft = Counter()
    per_stream = {s: Counter() for s in STREAMS}
    for row in out["cells"]:
        ft[_bin(row.get("first_divergence_turn"))] += 1
        # Per stream: C and T log different agent-event details by design
        # (version-2 tutor_skip reasons), so the events stream is the one
        # that says where play itself first parted.
        for s in STREAMS:
            d = (row.get("divergence") or {}).get(s)
            per_stream[s][_bin(None if d is None else min(t for t in (d["turn_a"], d["turn_b"]) if t is not None))] += 1
    out["first_divergence_turn_bins"] = dict(ft)
    out["first_divergence_turn_bins_by_stream"] = {s: dict(c) for s, c in per_stream.items()}
    # E2 game 0 at s_k against G0a's n7WpsqsZtdQ rotation-0 game k, both arms.
    deep = []
    for arm in ("T", "C"):
        mg, gg = load(G0A / "runs" / arm / "n7WpsqsZtdQ_rot0.jsonl")
        for k in range(8):
            me, ge = load(out_path("E2", k, "a"))
            players = (me or {}).get("players")
            pe, re_ = primary(ge.get(0), players)
            pg, rg = primary(gg.get(k), players)
            row = {"arm": arm, "k": k, "seed": seed(k), "malformed": [x for x in (re_, rg) if x]}
            if pe and pg:
                row["deal_same"] = pe["deal"] == pg["deal"]
                row["first_player_same"] = pe["first_player"] == pg["first_player"]
                row["first_decision_same"] = pe["first_decision"] == pg["first_decision"]
            row["g0a_prev_end"] = result_of(gg.get(k - 1)) if k else None
            deep.append(row)
    out["deep"] = deep
    return out


def distinct_deals(rows_arm="E2"):
    ds = set()
    for k in ARMS[rows_arm][2]:
        m, g = load(out_path(rows_arm, k, "a"))
        p, _ = primary(g.get(0), (m or {}).get("players"))
        if p:
            ds.add(tuple(p["deal"]))
    return len(ds)


# ---------------------------------------------------------------- report

def _yn(x):
    return "yes" if x else ("no" if x is not None else "-")


def _div_cell(row):
    t = row.get("first_divergence_turn")
    if "first_divergence_turn" not in row:
        return "n/a"
    if t is None:
        return f"none through turn {MAX_TURNS}"
    parts = []
    for s, d in row["divergence"].items():
        if d:
            parts.append(f"{s}#{d['index']}@t{d['turn_a']}/{d['turn_b']}")
    return f"turn {t} ({', '.join(parts)})"


def main():
    prereg = git("log", "-1", "--format=%H", "--", "studies/e2_seeding/PREREG.md").stdout.strip()
    reading = {"prereg_commit": prereg}
    primary_rows = read_pairs("E2", 0)
    n_ok = sum(r["identical"] for r in primary_rows)
    verdict = "PASS" if n_ok == 10 and len(primary_rows) == 10 else "FAIL"
    reading.update({"primary": primary_rows, "identical": n_ok, "verdict": verdict})
    bad_prereg = [(r["k"], c.get("prereg_commit")) for r in primary_rows for c in
                  [cell_meta(out_path("E2", r["k"], x)) for x in ("a", "b")] if c and not
                  str(c.get("prereg_commit", "")).startswith(prereg)]

    print(f"E2 primary (game 0, replicate a vs b): {n_ok}/{len(primary_rows)} identical -> {verdict}")
    if bad_prereg:
        print("  WARNING cells not run under the current PREREG commit:", bad_prereg)
    for r in primary_rows:
        print(f"  k={r['k']} seed={r['seed']} echo={r['seed_echo']} identical={_yn(r['identical'])}"
              f" deal={_yn(r.get('deal_same'))} first={_yn(r.get('first_player_same'))}"
              f" decision={_yn(r.get('first_decision_same'))} malformed={r['malformed']}")
        print(f"      first player {r.get('first_player')}; first decision {r.get('first_decision')}")
        print(f"      divergence: {_div_cell(r)}; results {r.get('results')}; lens {r.get('lens')}")
        for s, d in (r.get("divergence") or {}).items():
            if d:
                print(f"        {s} #{d['index']} a(t{d['turn_a']} {d['phase_a']}): {_short(d['rec_a'])}")
                print(f"        {s} #{d['index']} b(t{d['turn_b']} {d['phase_b']}): {_short(d['rec_b'])}")
        print(f"      cells {r['cells']}")
    print(f"  sanity: distinct game-0 deals across the 10 seeds: {distinct_deals()}")

    i1 = read_pairs("E2", 1)
    reading["I1"] = i1
    print(f"\nI1 (game 1, the second game in each JVM, a vs b): {sum(r['identical'] for r in i1)}/{len(i1)} identical")
    for r in i1:
        print(f"  k={r['k']} identical={_yn(r['identical'])} divergence: {_div_cell(r)}; results {r.get('results')}")
        for s, d in (r.get("divergence") or {}).items():
            if d:
                print(f"        {s} #{d['index']} a(t{d['turn_a']} {d['phase_a']}): {_short(d['rec_a'])}")
                print(f"        {s} #{d['index']} b(t{d['turn_b']} {d['phase_b']}): {_short(d['rec_b'])}")

    i2 = read_i2()
    reading["I2"] = i2
    print(f"\nI2 (game 1 of run k vs game 0 of run k+1, same Forge seed): deal same "
          f"{sum(bool(r.get('deal_same')) for r in i2)}/{len(i2)}, first player same "
          f"{sum(bool(r.get('first_player_same')) for r in i2)}/{len(i2)}, first decision same "
          f"{sum(bool(r.get('first_decision_same')) for r in i2)}/{len(i2)}")
    for r in i2:
        if not (r.get("deal_same") and r.get("first_player_same")):
            print("  differs:", r)

    i3 = read_i3()
    reading["I3"] = i3
    print("\nI3a (G0a arm C vs arm T, same cell and game index):")
    for bed, c in i3["by_bed"].items():
        print(f"  {bed}: {c}")
    print(f"  first divergence turn (C vs T, whole game to the cap): {i3['first_divergence_turn_bins']}")
    for s, bins in i3["first_divergence_turn_bins_by_stream"].items():
        print(f"    {s} stream: {bins}")
    for row in i3["cells"]:
        if not (row.get("deal_same") and row.get("first_player_same")):
            print(f"  deal or first player differs: {row['cell']} game {row['game']} seeds {row['seeds_CT']}"
                  f" prev_end {row['prev_end_CT']} malformed {row['malformed']}")
    print("I3b (E2 game 0 at s_k vs G0a n7WpsqsZtdQ rot0 game k):")
    for row in i3["deep"]:
        print(f"  {row['arm']} k={row['k']} deal={_yn(row.get('deal_same'))} first={_yn(row.get('first_player_same'))}"
              f" decision={_yn(row.get('first_decision_same'))} g0a_prev_end={row['g0a_prev_end']}"
              f" malformed={row['malformed']}")

    i4 = read_pairs("S", 0)
    reading["I4"] = i4
    print(f"\nI4 (stock seats, game 0, a vs b): {sum(r['identical'] for r in i4)}/{len(i4)} identical")
    for r in i4:
        print(f"  k={r['k']} identical={_yn(r['identical'])} divergence: {_div_cell(r)}; results {r.get('results')}")
        for s, d in (r.get("divergence") or {}).items():
            if d:
                print(f"        {s} #{d['index']} a(t{d['turn_a']} {d['phase_a']}): {_short(d['rec_a'])}")
                print(f"        {s} #{d['index']} b(t{d['turn_b']} {d['phase_b']}): {_short(d['rec_b'])}")

    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps(reading, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
