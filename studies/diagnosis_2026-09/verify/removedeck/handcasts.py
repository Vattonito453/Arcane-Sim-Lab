import glob, json, re, collections
from remidx import load
idx = load()
S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
RX = re.compile(r"^(Ai\(\d\)-.+?) (cast|activated|triggered) (.+?)(?: targeting \[.*)?$")
COUNTERS = {"Swan Song", "Pact of Negation"}
shown = 0
for f in glob.glob(S + "**/*.jsonl", recursive=True):
    agents = {}; lines = []
    with open(f, encoding="utf-8") as fh:
        for l in fh:
            if l.startswith('{"rec":"meta"'):
                m = json.loads(l); agents = dict(zip(m.get("players", []), m.get("agents", [])))
            elif l.startswith('{"rec":"entry"'):
                lines.append(l)
            elif l.startswith('{"rec":"zone"') and '"from":"Hand","to":"Stack"' in l:
                lines.append(l)
    if "stock" not in agents.values(): continue
    hand = set()
    for l in lines:
        if l.startswith('{"rec":"zone"'):
            r = json.loads(l); hand.add((r["game"], r["cardId"]))
    ents = [json.loads(l) for l in lines if l.startswith('{"rec":"entry"')]
    for i, r in enumerate(ents):
        if r["type"] != "STACK_ADD": continue
        m = RX.match(r["message"])
        if not m or m.group(2) != "cast": continue
        who, _, name = m.groups()
        if agents.get(who) != "stock" or name in COUNTERS: continue
        e = idx.get(name)
        if not (e and e["remAll"]): continue
        if (r["game"], r.get("cardId")) not in hand: continue
        print("==", f.split("studies")[1], "g", r["game"], "seq", r["seq"])
        for x in ents[max(0, i-6):i+2]:
            print("    ", x["type"], x["message"][:150])
        shown += 1
print("shown", shown)
