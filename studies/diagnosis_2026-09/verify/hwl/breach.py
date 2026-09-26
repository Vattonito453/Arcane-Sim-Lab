import json, glob, os, collections, re
S = r"C:/Users/Vatto/Magic Rules Engine/studies"
dirs = sorted(set(os.path.dirname(p) for p in glob.glob(S + "/**/*.jsonl", recursive=True)))
out = []
for d in dirs:
    files = glob.glob(d + "/*.jsonl")
    agg = collections.Counter()
    agents = set()
    for f in files:
        breach_bf = collections.defaultdict(set)  # (game) -> players with Breach on BF
        for line in open(f, encoding="utf-8", errors="replace"):
            if '"rec"' not in line: continue
            if ("Brain Freeze" not in line and "Underworld Breach" not in line and "Lion's Eye" not in line
                and '"rec":"meta"' not in line and '"rec":"result"' not in line and "Jeska's Will" not in line):
                continue
            try: r = json.loads(line)
            except Exception: continue
            rec = r.get("rec")
            if rec == "meta":
                agents.add(tuple(r.get("agents") or []))
                continue
            g = r.get("game")
            if rec == "zone":
                c = r.get("card")
                if c == "Underworld Breach":
                    if r.get("to") == "Battlefield": breach_bf[g].add(r.get("toPlayer")); agg["breach_enters_bf"] += 1
                    elif r.get("from") == "Battlefield": breach_bf[g].discard(r.get("fromPlayer"))
                if c in ("Brain Freeze", "Lion's Eye Diamond", "Jeska's Will") and r.get("to") == "Stack":
                    agg[f"{c}|from_{r.get('from')}"] += 1
                    if r.get("from") == "Graveyard":
                        agg[f"{c}|from_Graveyard_with_breach"] += (r.get("fromPlayer") in breach_bf[g])
            elif rec == "entry" and r.get("type") == "STACK_ADD":
                m = r.get("message", "")
                mm = re.match(r"(Ai\(\d\)-\S+) cast Brain Freeze targeting \[(.*)\]", m)
                if mm:
                    agg["bf_cast_msgs"] += 1
                    if mm.group(1) == mm.group(2): agg["bf_self_target"] += 1
            elif rec == "agent":
                det = r.get("detail", "")
                if r.get("event") in ("combo_cast", "tutor_cast", "combo_hold") and any(x in det for x in ("Brain Freeze", "Underworld Breach", "Lion's Eye")):
                    agg[f"agent_{r.get('event')}:{det.split(' (')[0].split(' vs')[0].split(' seeking')[0]}"] += 1
    if agg:
        out.append((os.path.relpath(d, S), len(files), sorted(agents)[:2], dict(agg)))
for o in out:
    print(o[0], "files", o[1], "agents", o[2])
    for k, v in sorted(o[3].items()): print("    ", k, v)
