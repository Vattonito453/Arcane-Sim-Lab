# For mixed-pod arms: in games censored WITH the re-ask loop signature, who was ahead at the clock?
import os, json, collections, glob, sys
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
dirs = sys.argv[1:]
for d in dirs:
    files = glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True)
    stats = collections.Counter()
    life = collections.defaultdict(list)
    looper_pilot = collections.Counter()
    for p in files:
        agents = {}; results = {}; reaim = collections.Counter()
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    m = json.loads(line); agents = dict(zip(m["players"], m.get("agents") or []))
                elif line.startswith('{"rec":"result"'):
                    r = json.loads(line); results[r["game"]] = r
                elif line.startswith('{"rec":"agent"') and '"kingmaker_reaim"' in line:
                    r = json.loads(line); reaim[(r["game"], r["turn"], r["player"])] += 1
        loopg = {}
        for (g,t,pl),c in reaim.items():
            if c > 1: loopg.setdefault(g, set()).add(pl)
        for g, r in results.items():
            cat = ("loopTO" if g in loopg else "TO") if r.get("timedOut") else ("decided" if r.get("winner") else "draw")
            stats[cat] += 1
            if r.get("winner"):
                stats[cat+"_win_"+agents.get(r["winner"],"?")] += 1
            if r.get("timedOut"):
                for s in r["seats"]:
                    pil = agents.get(s["name"], "?")
                    life[(cat, pil)].append(s["life"] if s["alive"] else None)
                if g in loopg:
                    for pl in loopg[g]: looper_pilot[agents.get(pl,"?")] += 1
    print("==", d, dict(stats))
    print("   looping seat pilot:", dict(looper_pilot))
    for k, v in sorted(life.items()):
        alive = [x for x in v if x is not None]
        print(f"   {k}: seats={len(v)} alive={len(alive)} ({100*len(alive)/max(1,len(v)):.0f}%) mean life alive={sum(alive)/max(1,len(alive)):.1f}")
