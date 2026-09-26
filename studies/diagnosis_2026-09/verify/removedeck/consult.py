import glob, json, collections
S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
held = collections.Counter(); casts = collections.Counter(); files = collections.Counter()
for f in glob.glob(S + "**/*.jsonl", recursive=True):
    txt = open(f, encoding="utf-8").read()
    if "Demonic Consultation" not in txt: continue
    agents = {}
    games = set(); cg = set()
    for l in txt.splitlines():
        if l.startswith('{"rec":"meta"'):
            m = json.loads(l); agents = dict(zip(m.get("players", []), m.get("agents", [])))
        elif "Demonic Consultation" in l:
            r = json.loads(l)
            if r.get("rec") == "zone" and r["card"] == "Demonic Consultation" and r["to"] == "Hand" and r.get("turn", 0) >= 1:
                games.add((r["game"], r["toPlayer"]))
            if r.get("rec") == "entry" and r["type"] == "STACK_ADD" and " cast Demonic Consultation" in r["message"]:
                who = r["message"].split(" cast ")[0]
                cg.add((r["game"], who)); casts[agents.get(who, "?")] += 1
    for g, p in games:
        held[agents.get(p, "?")] += 1
        files[f.split("studies")[1].rsplit("\\", 1)[0]] += 1
print("seat-games holding Consultation after turn 0 (drawn/tutored):", dict(held))
print("casts by agent:", dict(casts))
print(files)
