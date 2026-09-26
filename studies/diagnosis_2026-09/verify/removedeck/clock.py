import glob, json, collections, re
S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
tot = collections.Counter(); real_entries = 0; copy_entries = 0; files = 0
for f in glob.glob(S + "**/*.jsonl", recursive=True):
    txt = open(f, encoding="utf-8").read()
    if "Clock of Omens" not in txt: continue
    files += 1
    names = collections.defaultdict(set)   # cardId -> names ever carried (all games; ids stable per seat/deck in a file)
    acts = []; entries = []
    for l in txt.splitlines():
        if l.startswith('{"rec":"zone"'):
            r = json.loads(l); names[r["cardId"]].add(r["card"])
            if r["card"] == "Clock of Omens" and r["to"] == "Battlefield": entries.append(r)
        elif '"STACK_ADD"' in l and "activated Clock of Omens" in l:
            acts.append(json.loads(l))
    for r in acts:
        others = names[r["cardId"]] - {"Clock of Omens"}
        tot["copy:" + "/".join(sorted(others)) if others else "printed-only-id"] += 1
    for r in entries:
        if names[r["cardId"]] - {"Clock of Omens"}: copy_entries += 1
        else: real_entries += 1
print("files", files)
for k, v in tot.most_common(): print(v, k)
print("Clock battlefield entries: printed-card ids", real_entries, " copy-capable ids", copy_entries)
