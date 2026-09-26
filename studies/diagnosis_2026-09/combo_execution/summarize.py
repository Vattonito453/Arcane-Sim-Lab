import collections, json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "funnel_rows.json"), encoding="utf-8"))
STAGES = ["S0 never_sighted", "S1 sighted_no_cast", "S2 cast_not_assembled",
          "S3 assembled_no_win<=2", "S4 assembled_won<=2"]

rows = [r for r in rows if r["n_lines"] > 0]
groups = collections.defaultdict(list)
for r in rows:
    groups[(r["arm"], r["agent"])].append(r)

print("=== FUNNEL (seat-games of decks that HAVE lines; stage = best line) ===")
for (arm, ag), rs in sorted(groups.items()):
    c = collections.Counter(r["stage"] for r in rs)
    wins = collections.Counter(r["stage"] for r in rs if r["won"])
    n = len(rs)
    print(f"\n{arm} / {ag}: seat-games={n} wins={sum(r['won'] for r in rs)}")
    for s in range(5):
        print(f"   {STAGES[s]:28s} {c[s]:4d} ({100*c[s]/n:5.1f}%)  wins in bucket={wins[s]}")
    asm = [r for r in rs if r["best"] and r["best"]["assembled"] is not None]
    if asm:
        at = [r["best"]["assembled"] for r in asm]
        print(f"   assembled: n={len(asm)} median assembly turn={statistics.median(at)} "
              f"(~round {statistics.median(at)/4:.1f}); of these won={sum(r['won'] for r in asm)}")
        # rounds from assembly to win for winners
        d = [(r["final_turn"] - r["best"]["assembled"]) / 4 for r in asm if r["won"]]
        if d:
            print(f"   assembled->game end (winners): median {statistics.median(d):.1f} rounds, "
                  f"min {min(d):.1f} max {max(d):.1f}")
    meth = collections.Counter(r["method"] for r in rs if r["won"])
    print("   win methods:", dict(meth))

print("\n=== LINES assembled: which lines, and did anything activate after? ===")
lc = collections.Counter(); lw = collections.Counter(); lact = collections.Counter()
for r in rows:
    for ln in r["lines"]:
        if ln["assembled"] is not None:
            k = (ln["line"], r["agent"])
            lc[k] += 1
            if r["won"]:
                lw[k] += 1
            if ln["acts_after"]:
                lact[k] += 1
for k, n in lc.most_common(40):
    print(f"  {n:3d} assembled, won {lw[k]:3d}, any piece activated after {lact[k]:3d}  [{k[1]}] {k[0]}")
