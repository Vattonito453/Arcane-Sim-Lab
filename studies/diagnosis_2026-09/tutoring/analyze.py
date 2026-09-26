import json, collections, statistics, sys
from pathlib import Path
HERE = Path(__file__).parent

ARMS = sys.argv[1:] or ["tt_stock", "tt_stage0", "tt_stage1", "tt_stage2", "av015", "avwinmax", "av016", "rubric_ship"]
SPELL_MODES = {"spell"}

def pct(a, b):
    return f"{a}/{b} ({100*a/b:.0f}%)" if b else f"{a}/0"

def med(xs):
    xs = [x for x in xs if x is not None]
    return f"{statistics.median(xs):.1f}" if xs else "-"

for arm in ARMS:
    d = json.load(open(HERE / f"v2_{arm}.json"))
    C, S, G = d["casts"], d["searches"], d["games"]
    print(f"\n==================== {arm}: games={len(G)} shim={G[0]['shim'] if G else '?'}")
    for ag in ("plan", "stock"):
        cc = [c for c in C if c.get("agent") == ag and c.get("decider") != "shim_unmatched"]
        if not cc:
            continue
        cast = [c for c in cc if c.get("cast_turn") is not None]
        spells = [c for c in cast if c.get("mode") in SPELL_MODES]
        stranded = [c for c in cc if c.get("cast_turn") is None]
        print(f"-- {ag} seats: tutor cards reaching hand={len(cc)}  cast={len(cast)}  never cast={pct(len(stranded), len(cc))}")
        # never-cast breakdown by end zone
        ez = collections.Counter(c.get("end_zone") for c in stranded)
        print("   never-cast end zones:", dict(ez))
        # by tutor spell (mode spell) timing
        r14 = sum(1 for c in spells if c["cast_round"] <= 4)
        print(f"   tutor SPELL casts={len(spells)} rounds1-4={pct(r14, len(spells))} median cast round={med([c['cast_round'] for c in spells])}"
              f" median held rounds={med([c['cast_round']-c['drawn_round'] for c in spells if c.get('drawn_round') is not None])}")
        ot = sum(1 for c in spells if c.get("own_turn") is False)
        print(f"   off-turn tutor spell casts={pct(ot, len(spells))}")
        ph = collections.Counter(c.get("phase") for c in spells)
        print("   phases:", dict(ph.most_common(6)))
        dec = collections.Counter(c.get("decider") for c in cast)
        print("   decider (all casts):", dict(dec))
        # rounds histogram
        h = collections.Counter(min(c["cast_round"], 12) for c in spells)
        print("   round hist (12=12+):", [h.get(i, 0) for i in range(1, 13)])
        unm = [c for c in C if c.get("agent") == ag and c.get("decider") == "shim_unmatched"]
        if unm:
            print("   tutor_cast events with no matching zone cast:", len(unm), collections.Counter(u['tutor'] for u in unm).most_common(5))
    for ag in ("plan", "stock"):
        ss = [s for s in S if s.get("agent") == ag]
        if not ss:
            continue
        tk = [s for s in ss if s.get("taken") and s.get("taken") != "-"]
        lp = sum(1 for s in tk if s.get("taken_line_piece"))
        wl = sum(1 for s in tk if s.get("taken_win_line_piece"))
        used = sum(1 for s in tk if s.get("taken_used_turn") is not None)
        r14 = sum(1 for s in ss if s["round"] <= 4)
        print(f"-- {ag} searches={len(ss)} rounds1-4={pct(r14, len(ss))} median round={med([s['round'] for s in ss])}"
              f" taken known={len(tk)} line-piece={pct(lp, len(tk))} win-line-piece={pct(wl, len(tk))} taken-later-cast/entered={pct(used, len(tk))}")
        st = [s for s in ss if s.get("steer")]
        if ag == "plan":
            modes = collections.Counter(s["steer"]["mode"] for s in st)
            sighted = sum(1 for s in ss if s.get("seen", {}).get("sighted") == "true")
            cp = sum(1 for s in ss if s.get("seen", {}).get("comboPick") == "yes")
            print(f"   search_seen joined={sum(1 for s in ss if s.get('seen'))} sighted={sighted} comboPick={cp} steers={dict(modes)}")
