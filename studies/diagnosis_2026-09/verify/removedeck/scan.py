"""Scan every study JSONL: casts/activations of AI:RemoveDeck:All cards by seat agent,
real object vs copy; battlefield entries of flagged cards. Own implementation."""
import glob, json, re, os, sys, collections, time
from remidx import load
idx = load()
def flag(n):
    e = idx.get(n)
    if e is None and " // " in n: e = idx.get(n.split(" // ")[0])
    return e
S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
files = sorted(glob.glob(S + "**/*.jsonl", recursive=True))
RX = re.compile(r"^(Ai\(\d\)-.+?) (cast|activated) (.+?)(?: targeting \[.*)?$")
casts = collections.Counter()      # (card, agent) printed-name casts of flagged cards
acts = collections.Counter()       # (card, agent, real/copy)
acts_by_origin = collections.Counter()
bf = collections.Counter()         # (card, agent, real/copy) battlefield entries
files_with_flag_in_deck = collections.Counter()
t0 = time.time()
agent_of_file_counts = collections.Counter()
for fi, f in enumerate(files):
    agents = {}
    stack = []; zones = []
    with open(f, encoding="utf-8") as fh:
        for l in fh:
            if '"rec":"meta"' in l[:20]:
                m = json.loads(l)
                for p, a in zip(m.get("players", []), m.get("agents", [])):
                    agents[p] = a
            elif '"STACK_ADD"' in l:
                stack.append(l)
            elif l.startswith('{"rec":"zone"'):
                zones.append(l)
    if not agents:
        continue
    # origin name per (game, cardId): first zone record's card name, plus cast names
    origin = {}
    castname = {}
    for l in zones:
        r = json.loads(l)
        k = (r["game"], r["cardId"])
        if k not in origin:
            origin[k] = r["card"]
    srecs = [json.loads(l) for l in stack]
    for r in srecs:
        m = RX.match(r.get("message", ""))
        if m and m.group(2) == "cast":
            castname[(r["game"], r.get("cardId"))] = m.group(3)
    def real_name(g, cid):
        return castname.get((g, cid)) or origin.get((g, cid))
    for r in srecs:
        m = RX.match(r.get("message", ""))
        if not m: continue
        who, verb, name = m.groups()
        ag = agents.get(who, "?")
        if verb == "cast":
            e = flag(name)
            if e and e["remAll"]:
                casts[(name, ag)] += 1
        else:
            cur = r.get("card") or name
            e = flag(cur)
            if e and e["remAll"]:
                rn = real_name(r["game"], r.get("cardId"))
                kind = "real" if rn == cur else "copy"
                acts[(cur, ag, kind)] += 1
                acts_by_origin[(cur, rn, ag)] += 1
    for l in zones:
        r = json.loads(l)
        if r["to"] != "Battlefield": continue
        e = flag(r["card"])
        if not (e and e["remAll"]): continue
        ag = agents.get(r.get("toPlayer"), "?")
        rn = real_name(r["game"], r["cardId"])
        bf[(r["card"], ag, "real" if rn == r["card"] else "copy")] += 1
    if fi % 200 == 0:
        print(f"{fi}/{len(files)} {time.time()-t0:.0f}s", file=sys.stderr)
json.dump({"casts": [[*k, v] for k, v in casts.items()],
           "acts": [[*k, v] for k, v in acts.items()],
           "acts_by_origin": [[*k, v] for k, v in acts_by_origin.items()],
           "bf": [[*k, v] for k, v in bf.items()]}, open("scan_out.json", "w"), indent=0)
print("done", time.time() - t0)
