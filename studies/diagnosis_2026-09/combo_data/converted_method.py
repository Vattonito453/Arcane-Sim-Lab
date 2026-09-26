import json, glob, collections
from pathlib import Path
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
audit = {r["deck"]: r for r in json.load(open("plan_audit.json")) if "/" in r["deck"]}
def method(msgs):
    j = " ".join(msgs)
    if "won by spell" in j: return "spell"
    if "poison" in j: return "poison"
    if "generals" in j or "commander damage" in j: return "commander damage"
    if "empty library" in j: return "deckout"
    if "life total" in j: return "combat/life"
    return "other"
res = collections.defaultdict(collections.Counter)
seen_files = set()
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8", errors="replace") as fh:
        try: meta = json.loads(fh.readline())
        except: continue
        if meta.get("rec") != "meta" or not meta.get("decks"): continue
        seat = {}
        for p, d, a in zip(meta["players"], meta["decks"], meta.get("agents") or ["stock"]*4):
            if "human_ceiling" in d:
                parts = Path(d.replace("\\", "/")).parts
                t = parts[-3] + "/" + Path(d).stem
                if t in audit: seat[p] = (t, a)
        if not seat: continue
        bf = collections.defaultdict(dict); asm = set(); outcome = collections.defaultdict(list); winner = {}
        for line in fh:
            try: r = json.loads(line)
            except: continue
            g = r.get("game"); rec = r.get("rec")
            if rec == "zone":
                if r.get("from") == "Battlefield": bf[g].setdefault(r.get("fromPlayer"), {}).pop(r.get("cardId"), None)
                if r.get("to") == "Battlefield":
                    p = r.get("toPlayer"); bf[g].setdefault(p, {})[r.get("cardId")] = r.get("card")
                    if p in seat:
                        names = set(bf[g][p].values())
                        for i, ln in enumerate(audit[seat[p][0]]["lines"]):
                            if all(c in names for c in ln["cards"]): asm.add((g, p, i))
            elif rec == "entry" and r.get("type") == "GAME_OUTCOME":
                outcome[g].append(r.get("message", ""))
            elif rec == "result":
                winner[g] = r.get("winner")
        for (g, p, i) in asm:
            if winner.get(g) != p: continue
            ln = audit[seat[p][0]]["lines"][i]
            res[(seat[p][1], ln["cls"])][method(outcome[g])] += 1
for k, v in sorted(res.items()):
    tot = sum(v.values())
    print(k, tot, dict(v), f"combat share {v['combat/life']/tot:.0%}")
