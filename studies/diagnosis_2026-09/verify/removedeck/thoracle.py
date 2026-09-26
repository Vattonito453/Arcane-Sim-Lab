import glob, json, collections
S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
c = collections.Counter()
for f in glob.glob(S + "**/*.jsonl", recursive=True):
    txt = open(f, encoding="utf-8").read()
    if "cast Thassa's Oracle" not in txt: continue
    agents = {}; casts = {}; winners = {}
    for l in txt.splitlines():
        if l.startswith('{"rec":"meta"'):
            m = json.loads(l); agents = dict(zip(m.get("players", []), m.get("agents", [])))
        elif "cast Thassa's Oracle" in l:
            r = json.loads(l); casts.setdefault(r["game"], set()).add(r["message"].split(" cast ")[0])
        elif l.startswith('{"rec":"result"'):
            r = json.loads(l); winners[r["game"]] = r.get("winner")
    for g, whos in casts.items():
        for w in whos:
            c[(agents.get(w, "?"), "caster won" if winners.get(g) == w else "caster did not win")] += 1
print(c)
