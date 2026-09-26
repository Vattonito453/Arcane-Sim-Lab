import json, glob, re, collections, os, sys, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    from lenient import classify, ORDER, WIN
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
agg = collections.defaultdict(collections.Counter)
wd = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))  # within-deck fetch conversion
for arm, d in ARMS.items():
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        pf = (glob.glob(ROOT + d + f"/plans_{m.group(1)}.json") + glob.glob(ROOT + d + f"/plans/plans_{m.group(1)}.json"))[0]
        decks = json.load(open(pf, encoding="utf-8"))["decks"]
        meta = None; Z = collections.defaultdict(list); R = {}
        for line in open(f, encoding="utf-8"):
            if '"rec":"zone"' in line: r = json.loads(line); Z[r["game"]].append(r)
            elif '"rec":"result"' in line: r = json.loads(line); R[r["game"]] = r
            elif '"rec":"meta"' in line: meta = json.loads(line)
        n = len(meta["players"])
        plan_seats = [p for p, a in zip(meta["players"], meta["agents"]) if a == "plan"]
        for g, res in R.items():
            for p in plan_seats:
                plan = decks.get(p.split("-", 1)[1], {}); cards = set(plan.get("roles", {}).keys())
                L = plan.get("lines", [])
                zone = {}; first = {}
                for z in Z[g]:
                    zone[z["cardId"]] = (z["to"], z.get("toPlayer"), z["card"])
                    if z["to"] != "Battlefield": continue
                    B = {nm for (zn, ctl, nm) in zone.values() if zn == "Battlefield" and ctl == p}
                    for l in L:
                        if set(l["cards"]) <= B:
                            c = classify(l, cards)
                            if c not in first: first[c] = z["turn"]
                won = res.get("winner") == p
                wr = (res["turns"] - 1) // n + 1
                agg["any game"]["n"] += 1; agg["any game"]["won"] += won
                best = None
                for c in ORDER:
                    if c in first: best = c; break
                key = best or "no line assembled"
                agg[key]["n"] += 1; agg[key]["won"] += won
                if best:
                    ar = (first[best] - 1) // n + 1
                    agg[key]["soon"] += won and wr - ar <= 2
print("plan-seat games by best line class ever fully on own battlefield (pooled 4 arms):")
for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
    s = f" won<=2 rounds after assembly={v['soon']} ({100*v['soon']/v['n']:.0f}%)" if 'soon' in v or k not in ('any game','no line assembled') else ""
    print(f"   {k:32s} games={v['n']:4d} won={v['won']:4d} ({100*v['won']/v['n']:.0f}%)" + s)
