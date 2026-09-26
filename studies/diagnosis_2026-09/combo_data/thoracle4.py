import json, glob, re, collections
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = glob.glob(R + "/**/*.jsonl", recursive=True)
PIECES = {"Thassa's Oracle": "O", "Demonic Consultation": "C", "Tainted Pact": "P"}
agg = collections.Counter(); ex = collections.defaultdict(list)
stock_agg = collections.Counter()
for f in files:
    meta = None; turn = collections.defaultdict(int)
    casts = collections.defaultdict(list); agentseat = set(); outcome = {}
    oracle_etb = collections.defaultdict(list)
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try: r = json.loads(line)
            except: continue
            rec = r.get("rec"); g = r.get("game")
            if rec == "meta": meta = r; continue
            if rec == "agent" and r.get("event") == "combo_cast" and any(r.get("detail","").startswith(n) for n in PIECES):
                agentseat.add((g, r["player"]))
            if rec != "entry": continue
            m = r.get("message", ""); t = r.get("type")
            if t == "TURN":
                mm = re.match(r"Turn (\d+)", m); 
                if mm: turn[g] = int(mm.group(1))
            elif t == "STACK_ADD":
                mm = re.match(r"^(Ai\(\d\)-\S+) cast (.+?)(?: targeting|$)", m)
                if mm and mm.group(2) in PIECES:
                    casts[(g, mm.group(1))].append((r.get("seq"), turn[g], PIECES[mm.group(2)]))
            elif t == "GAME_OUTCOME":
                mm = re.match(r"^(Ai\(\d\)-\S+) has (won|lost)(.*)$", m)
                if mm: outcome[(g, mm.group(1))] = mm.group(2) + mm.group(3)
    plan_players = set()
    if meta:
        for p, a in zip(meta.get("players", []), meta.get("agents", [])):
            if a == "plan": plan_players.add(p)
    for key, seq in casts.items():
        seq.sort()
        o = [x for x in seq if x[2] == "O"]; cp = [x for x in seq if x[2] in "CP"]
        if not o or not cp: continue
        oc = outcome.get(key, "unfinished")
        res = ("WON Oracle" if ("Thassa" in oc and oc.startswith("won")) else "LOST decked" if "empty library" in oc
               else "won other" if oc.startswith("won") else "unfinished" if oc == "unfinished" else "lost other")
        o0, c0 = o[0], cp[0]
        if o0[0] < c0[0]:
            kind = "Oracle first, tutor SAME turn" if o0[1] == c0[1] else "Oracle first, tutor LATER turn"
        else:
            kind = "Consult/Pact first"
        who = "agent" if key[1] in plan_players else "stock"
        if who == "agent": agg[(f.split("studies")[1].rsplit(chr(92),1)[0], kind, res)] += 1
        else: stock_agg[(f.split("studies")[1].rsplit(chr(92),1)[0], kind, res)] += 1
        if len(ex[(who, kind, res)]) < 2: ex[(who, kind, res)].append((f.split("studies")[1], key, seq, oc))
print("AGENT seats (plan) with both Oracle and Consultation/Pact cast:")
for k, v in sorted(agg.items()): print(f"  {v:4d}  {k}")
print("STOCK seats with both cast:")
for k, v in sorted(stock_agg.items()): print(f"  {v:4d}  {k}")
for k, e in ex.items():
    if "LATER" in k[1]:
        print(k); [print("    ", x) for x in e]
