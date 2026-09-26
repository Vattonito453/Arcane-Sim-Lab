import json, glob, collections, re, statistics
from classify import cls
def strip(p): return re.sub(r"^Ai\(\d+\)-", "", p or "")
base = "C:/Users/Vatto/Magic Rules Engine/studies/"
out = collections.defaultdict(list); lasts = []
for runs, plans_dir in [("behavior_rubric/runs_agent_shipping", "behavior_rubric/runs_agent_shipping/plans"),
                        ("agent_viability/runs_015_default", "agent_viability/runs_015_default"),
                        ("agent_viability/runs_winmax", "agent_viability/runs_winmax"),
                        ("agent_viability/runs_016_engine", "agent_viability/runs_016_engine")]:
    plans = {}
    for f in glob.glob(base + plans_dir + "/plans_*.json"):
        for name, plan in json.load(open(f, encoding="utf-8"))["decks"].items():
            plans[name] = [(frozenset(ln["cards"]), cls(ln.get("produces", []), "lenient")) for ln in plan["lines"]]
    for f in sorted(glob.glob(base + runs + "/*.jsonl")):
        games = collections.defaultdict(list); meta = None
        for l in open(f, encoding="utf-8"):
            try: r = json.loads(l)
            except: continue
            if r.get("rec") == "meta": meta = r
            elif r.get("rec") in ("zone", "result", "entry"): games[r["game"]].append(r)
        if not meta: print("nometa", f); continue
        agents = dict(zip(meta["players"], meta.get("agents", [])))
        for g, recs in games.items():
            bf = collections.defaultdict(dict); first = {}
            res = None; entries = []
            for r in recs:
                if r["rec"] == "result": res = r; continue
                if r["rec"] == "entry": entries.append(r); continue
                if r.get("from") == "Battlefield": bf[r.get("fromPlayer")].pop(r.get("cardId"), None)
                if r.get("to") == "Battlefield":
                    p = r.get("toPlayer"); bf[p][r.get("cardId")] = r["card"]; names = set(bf[p].values())
                    for ln, c in plans.get(strip(p), []):
                        if c == "resource" and ln <= names and p not in first:
                            first[p] = r.get("turn")
            if not res: continue
            for p, t in first.items():
                if agents.get(p) != "plan": continue
                out[runs].append(res["turns"] - t)
                if res.get("winner") == p:
                    dmg = [e["message"] for e in entries if e.get("type") in ("DAMAGE", "LIFE", "GAME_OUTCOME", "COMBAT")][-3:]
                    lasts.append((runs.split("/")[-1], strip(p), dmg))
for k, v in out.items():
    print(k, "n", len(v), "median turns from resource-line assembly to game end", statistics.median(v), "min", min(v), "max", max(v))
print(len(lasts))
for x in lasts[:12]: print(x)
