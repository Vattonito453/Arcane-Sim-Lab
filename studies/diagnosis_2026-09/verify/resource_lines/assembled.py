import json, glob, collections, re, sys, os
from classify import cls
def strip(p): return re.sub(r"^Ai\(\d+\)-", "", p or "")
def run(RUNS, PLANS):
    plans = {}
    for f in glob.glob(PLANS + "/plans_*.json"):
        d = json.load(open(f, encoding="utf-8"))
        for name, plan in d["decks"].items():
            plans[name] = [(frozenset(ln["cards"]), cls(ln.get("produces", []), "lenient"), ln.get("produces", [])) for ln in plan["lines"]]
    stats = collections.Counter(); examples = []
    for f in sorted(glob.glob(RUNS + "/*.jsonl")):
        games = collections.defaultdict(list)
        meta = None
        for l in open(f, encoding="utf-8"):
            try: r = json.loads(l)
            except: continue
            if r.get("rec") == "meta": meta = r
            elif r.get("rec") in ("zone", "result"): games[r["game"]].append(r)
        agents = dict(zip(meta["players"], meta.get("agents", []))) if meta else {}
        for g, recs in games.items():
            bf = collections.defaultdict(dict)  # player -> cardId -> name
            assembled = {}  # (player, line) -> (turn, class)
            result = None
            for r in recs:
                if r["rec"] == "result": result = r; continue
                if r.get("from") == "Battlefield":
                    bf[r.get("fromPlayer")].pop(r.get("cardId"), None)
                if r.get("to") == "Battlefield":
                    bf[r.get("toPlayer")][r.get("cardId")] = r["card"]
                    p = r.get("toPlayer"); names = set(bf[p].values())
                    for ln, c, prod in plans.get(strip(p), []):
                        if ln <= names and (p, ln) not in assembled:
                            assembled[(p, ln)] = (r.get("turn"), c, prod)
            if not result: continue
            for p, ag in agents.items():
                if ag != "plan": continue
                mine = {ln: v for (pp, ln), v in assembled.items() if pp == p}
                won = result.get("winner") == p
                kinds = {v[1] for v in mine.values()}
                key = ("win_line" if "win" in kinds else "resource_only" if kinds else "none")
                stats[(key, won)] += 1
                if key == "resource_only" and len(examples) < 8:
                    ln, v = next(iter(mine.items()))
                    examples.append((os.path.basename(f), g, strip(p), " + ".join(sorted(ln)), v[0], v[2][:3], "WON" if won else "lost, winner " + strip(result.get("winner"))))
    return stats, examples
if __name__ == "__main__":
    base = "C:/Users/Vatto/Magic Rules Engine/studies/"
    for runs, plans in [("behavior_rubric/runs_agent_shipping", "behavior_rubric/runs_agent_shipping/plans"),
                        ("agent_viability/runs_015_default", "agent_viability/runs_015_default"),
                        ("agent_viability/runs_winmax", "agent_viability/runs_winmax"),
                        ("agent_viability/runs_016_engine", "agent_viability/runs_016_engine")]:
        s, ex = run(base + runs, base + plans)
        print(runs)
        for k in sorted(s): print("   ", k, s[k])
        for e in ex[:5]: print("     ex:", e)
