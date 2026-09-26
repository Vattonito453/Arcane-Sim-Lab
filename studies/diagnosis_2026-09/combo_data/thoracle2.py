import json, glob, re, collections
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = glob.glob(R + "/**/*.jsonl", recursive=True)
PIECES = {"Thassa's Oracle": "O", "Demonic Consultation": "C", "Tainted Pact": "P"}
agg = collections.Counter(); per_arm = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list)
for f in files:
    meta = None
    casts = collections.defaultdict(list)     # (game, player) -> [(seq, code)]
    agent = collections.defaultdict(list)
    outcome = {}                               # (game, player) -> message
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try: r = json.loads(line)
            except: continue
            rec = r.get("rec")
            if rec == "meta": meta = r; continue
            g = r.get("game")
            if rec == "agent" and r.get("event") == "combo_cast":
                for n, c in PIECES.items():
                    if r.get("detail","").startswith(n): agent[(g, r["player"])].append((r.get("turn"), c, r["detail"]))
            elif rec == "entry":
                m = r.get("message", "")
                t = r.get("type")
                if t == "STACK_ADD":
                    mm = re.match(r"^(Ai\(\d\)-\S+) cast (.+?)(?: targeting|$)", m)
                    if mm and mm.group(2) in PIECES:
                        casts[(g, mm.group(1))].append((r.get("seq"), PIECES[mm.group(2)]))
                elif t == "GAME_OUTCOME":
                    mm = re.match(r"^(Ai\(\d\)-\S+) has (won|lost)(.*)$", m)
                    if mm: outcome[(g, mm.group(1))] = mm.group(2) + mm.group(3)
    arm = f.split("studies")[1].rsplit("\\", 1)[0]
    for key, seq in casts.items():
        if not agent.get(key):
            continue  # stock seat or agent didn't push it
        order = "".join(c for _, c in sorted(seq))
        oc = outcome.get(key, "unfinished")
        if "Thassa" in oc and "won" in oc[:4]: res = "WON by Oracle"
        elif "empty library" in oc: res = "LOST decked"
        elif oc.startswith("won"): res = "won other"
        elif oc == "unfinished": res = "no outcome"
        else: res = "lost other"
        firstO = order.find("O"); firstC = min([i for i in (order.find("C"), order.find("P")) if i >= 0] or [99])
        seqkind = ("O-first" if 0 <= firstO < firstC else ("C/P-first" if firstC < 99 else "O-only")) if firstO >= 0 else "no-Oracle-cast"
        agg[(seqkind, res)] += 1
        per_arm[arm][(seqkind, res)] += 1
        if len(examples[(seqkind, res)]) < 3:
            examples[(seqkind, res)].append((f.split("studies")[1], key, order, agent[key][:4], oc))
print("agent seats that cast a Thoracle-line piece via combo pursuit: (cast order, player outcome)")
for k, v in sorted(agg.items(), key=lambda kv: -kv[1]): print(f"  {v:4d}  {k}")
print()
for k, ex in examples.items():
    print(k)
    for e in ex: print("    ", e)
