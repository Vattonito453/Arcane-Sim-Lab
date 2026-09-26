import os, json, sys, collections, re
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
EV = ["combo_cast","tutor_cast","tutor_steer","search_seen","combo_hold","line_completion_seen","instant_hold","split","added_block","kingmaker_reaim","open_reaim","finisher_hold","counter_fire","counter_veto"]
agg = collections.OrderedDict()
def key_for(path):
    rel = os.path.relpath(path, ROOT).replace("\\","/")
    parts = rel.split("/")
    # study/rundir[/arm]
    if len(parts) >= 3 and parts[2] and not parts[2].endswith(".jsonl"):
        return "/".join(parts[:3])
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]
for dp, dn, fn in os.walk(ROOT):
    for f in fn:
        if not f.endswith(".jsonl"): continue
        p = os.path.join(dp, f)
        k = key_for(p)
        a = agg.setdefault(k, {"files":0,"games":0,"decided":0,"timeout":0,"turncap":0,"pop":collections.Counter(),"shim":collections.Counter(),"agents":collections.Counter(),"ev":collections.Counter(),"raw":0})
        a["files"] += 1
        israw = False
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    israw = True
                    m = json.loads(line)
                    decks = " ".join(m.get("decks") or []).lower()
                    if "human_ceiling" in decks: pop = "cEDH(human_ceiling)"
                    elif "engine\decks" in decks or "engine/decks" in decks: pop = "bundled"
                    elif "precon" in decks or "res\decks" in decks or "commander" in decks: pop = "precon"
                    else: pop = "other:" + (decks[:60])
                    a["pop"][pop] += 1
                    a["shim"][m.get("shim")] += 1
                    ag = m.get("agents")
                    if ag: a["agents"][",".join(ag)] += 1
                    else: a["agents"]["humanized=%s" % m.get("humanized")] += 1
                elif line.startswith('{"rec":"result"'):
                    r = json.loads(line)
                    a["games"] += 1
                    if r.get("timedOut"): a["timeout"] += 1
                    elif r.get("turnCapped"): a["turncap"] += 1
                    if not r.get("draw") and r.get("winner"): a["decided"] += 1
                elif line.startswith('{"rec":"agent"'):
                    mm = re.search(r'"event":"([a-z_]+)"', line)
                    if mm and mm.group(1) in EV: a["ev"][mm.group(1)] += 1
        if israw: a["raw"] += 1
out = []
for k, a in agg.items():
    pops = dict(a["pop"])
    print(f"{k:48s} files={a['files']:4d} raw={a['raw']:4d} games={a['games']:5d} decided={a['decided']:5d} to={a['timeout']:4d} cap={a['turncap']:3d} pop={pops} shim={dict(a['shim'])}")
    print("     ev:", dict(a["ev"]))
    out.append({"key":k, **{x:a[x] for x in ["files","raw","games","decided","timeout","turncap"]}, "pop":pops, "shim":dict(a["shim"]), "ev":dict(a["ev"])})
json.dump(out, open(os.path.join(os.path.dirname(__file__), "games_by_study.json"), "w"), indent=1)
