"""Phase in which tutor SPELLS (SP$ ChangeZone Origin Library -> Hand/Library) are cast, by seat agent."""
import zipfile, re, json, glob, sys, collections
Z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
tut = {}
for n in Z.namelist():
    if not n.endswith(".txt"): continue
    t = Z.read(n).decode("utf-8", "replace")
    names = re.findall(r"^Name:(.+)$", t, re.M)
    sp = [l for l in t.splitlines() if l.startswith("A:SP$ ChangeZone") and "Origin$ Library" in l]
    if not sp: continue
    dest = "Hand" if any("Destination$ Hand" in l for l in sp) else ("Library" if any("Destination$ Library" in l for l in sp) else "other")
    logic = re.findall(r"AILogic\$ ?(\w+)", " ".join(sp))
    for nm in names: tut.setdefault(nm.strip(), (dest, logic))
R = "C:/Users/Vatto/Magic Rules Engine/studies/"
for fold in sys.argv[1:]:
    ph = collections.Counter(); drawn = collections.Counter(); castn = collections.Counter()
    handsize_note = collections.Counter()
    for f in glob.glob(R + fold + "/*.jsonl"):
        agent = {}
        for l in open(f, encoding="utf-8", errors="replace"):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("rec") == "meta":
                for p, a in zip(r.get("players", []), r.get("agents", [])): agent[p] = a
            elif r.get("rec") == "zone" and r.get("card") in tut:
                a = agent.get(r.get("fromPlayer") or r.get("toPlayer"), "?")
                d = tut[r["card"]][0]
                if r.get("from") == "Library" and r.get("to") == "Hand":
                    drawn[(a, d)] += 1
                if r.get("from") == "Hand" and r.get("to") == "Stack":
                    castn[(a, d)] += 1
                    ph[(a, d, r.get("phase") or "?")] += 1
    print("=== " + fold)
    for k in sorted(castn):
        tot = castn[k]
        byph = {p: c for (a, d, p), c in ph.items() if (a, d) == k}
        pre = sum(c for p, c in byph.items() if p in ("UPKEEP", "DRAW", "MAIN1", "COMBAT_BEGIN"))
        print("  agent=%-5s dest=%-7s drawn~=%4d cast=%4d  castBeforeMain2(own or opp turn)=%.2f  byPhase=%s" % (k[0], k[1], drawn[k], tot, pre / max(1, tot), dict(sorted(byph.items(), key=lambda kv: -kv[1]))))
