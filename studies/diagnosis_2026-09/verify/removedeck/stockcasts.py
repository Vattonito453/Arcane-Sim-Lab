"""Every cast of an AI:RemoveDeck:All card by a stock-controlled seat: from which zone,
with what on the stack, and what the previous log entry was."""
import glob, json, re, collections
from remidx import load
idx = load()
S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
RX = re.compile(r"^(Ai\(\d\)-.+?) (cast|activated|triggered) (.+?)(?: targeting \[.*)?$")
out = collections.Counter(); examples = {}
byname = collections.Counter()
for f in glob.glob(S + "**/*.jsonl", recursive=True):
    agents = {}; entries = []; zfrom = collections.defaultdict(list)
    with open(f, encoding="utf-8") as fh:
        for l in fh:
            if l.startswith('{"rec":"meta"'):
                m = json.loads(l); agents = dict(zip(m.get("players", []), m.get("agents", [])))
            elif l.startswith('{"rec":"entry"'):
                if '"STACK_ADD"' in l or '"STACK_RESOLVE"' in l or '"TURN"' in l: entries.append(json.loads(l))
            elif l.startswith('{"rec":"zone"') and '"to":"Stack"' in l:
                r = json.loads(l); zfrom[(r["game"], r["cardId"])].append(r["from"])
    if "stock" not in agents.values(): continue
    depth = 0; prev = None; game = None; nth = collections.Counter()
    for r in entries:
        if r["game"] != game: game = r["game"]; depth = 0; nth = collections.Counter()
        if r["type"] == "TURN": depth = 0; prev = r; continue
        if r["type"] == "STACK_RESOLVE":
            depth = max(0, depth - 1); prev = r; continue
        m = RX.match(r["message"])
        if m and m.group(2) == "cast":
            who, _, name = m.groups()
            e = idx.get(name) or (idx.get(name.split(" // ")[0]) if " // " in name else None)
            if e and e["remAll"] and agents.get(who) == "stock":
                k = (r["game"], r.get("cardId"))
                zs = zfrom.get(k, [])
                z = zs[nth[k]] if nth[k] < len(zs) else "?"
                pm = RX.match(prev["message"]) if prev and prev["type"] == "STACK_ADD" else None
                ptrig = bool(pm and pm.group(2) == "triggered")
                cat = f"from={z} stackEmpty={depth==0} prevTriggered={ptrig}"
                out[cat] += 1
                byname[(cat, name)] += 1
                examples.setdefault(cat, (f.split("studies")[1], r["game"], r["seq"], r["message"][:100], prev["message"][:100] if prev else None))
        if m: 
            k = (r["game"], r.get("cardId"))
            if m.group(2) == "cast": nth[k] += 1
        depth += 1; prev = r
for k, v in out.most_common(): print(v, k, "\n     e.g.", examples[k])
print()
for k, v in byname.most_common(40): print(v, k)
