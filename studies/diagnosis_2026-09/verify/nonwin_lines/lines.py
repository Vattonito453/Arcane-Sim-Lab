import json, glob, re, collections, sys
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
for src in [ROOT+"behavior_rubric/plans_*.json", ROOT+"behavior_rubric/runs_agent_shipping/plans/plans_*.json", ROOT+"agent_viability/runs_015_default/plans_*.json", ROOT+"agent_viability/runs_016_engine/plans_*.json"]:
    files = sorted(glob.glob(src))
    tot = nw = 0; decks = 0; zero = []; prodc = collections.Counter(); allprod = collections.Counter(); prodnw = collections.Counter()
    for f in files:
        d = json.load(open(f, encoding="utf-8"))["decks"]
        for name, p in d.items():
            decks += 1
            L = p.get("lines", [])
            w = 0
            for l in L:
                s = " ; ".join(l.get("produces", []))
                tot += 1
                for x in l.get("produces", []): allprod[x] += 1
                if WIN.search(s): w += 1
                else:
                    nw += 1; prodnw[s] += 1
                    for x in l.get("produces", []): prodc[x] += 1
            if w == 0: zero.append((name, len(L)))
    print(src.split("studies/")[1], "files", len(files), "decks", decks, "lines", tot, "nonwin", nw, f"{100*nw/max(tot,1):.1f}%")
    print("  zero-win decks:", zero)
    if "behavior_rubric/plans" in src:
        print("  top nonwin produce-sets:")
        for k, v in prodnw.most_common(25): print("   ", v, k[:160])
        print("  all distinct produces strings (count):")
        for k, v in sorted(allprod.items(), key=lambda x: -x[1]): print("   ", v, ("WIN " if WIN.search(k) else "    ") + k[:150])
