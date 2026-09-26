import zipfile, re, json, glob, sys, collections
Z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
tut = {}
for n in Z.namelist():
    if not n.endswith(".txt"): continue
    t = Z.read(n).decode("utf-8", "replace")
    names = re.findall(r"^Name:(.+)$", t, re.M)
    sp = [l for l in t.splitlines() if l.startswith("A:SP$ ChangeZone") and "Origin$ Library" in l and "Destination$ Hand" in l and "ChangeType$ Card " in l + " "]
    if sp:
        for nm in names: tut.setdefault(nm.strip(), True)
R = "C:/Users/Vatto/Magic Rules Engine/studies/"
for fold in sys.argv[1:]:
    picks = collections.Counter(); types = collections.Counter(); n = 0
    lines_by_deck = {}
    for f in glob.glob(R + fold + "/*.jsonl"):
        recs = []
        agent = {}
        for l in open(f, encoding="utf-8", errors="replace"):
            try: r = json.loads(l)
            except Exception: continue
            recs.append(r)
            if r.get("rec") == "meta":
                for p, a in zip(r.get("players", []), r.get("agents", [])): agent[p] = a
        for i, r in enumerate(recs):
            if r.get("rec") == "zone" and r.get("card") in tut and r.get("from") == "Stack" and r.get("to") == "Graveyard":
                p = r.get("toPlayer"); g = r.get("game")
                if agent.get(p) != "stock": continue
                for j in range(i - 1, max(0, i - 40), -1):
                    q = recs[j]
                    if q.get("rec") == "zone" and q.get("game") == g and q.get("from") == "Library" and q.get("to") == "Hand" and q.get("toPlayer") == p:
                        n += 1
                        picks[(r["card"], q["card"])] += 1
                        tl = q.get("types") or ""
                        types["Creature" if "Creature" in tl else ("Land" if "Land" in tl else tl.split()[0] if tl else "?")] += 1
                        break
    print("=== %s stock generic tutor-to-hand picks: n=%d types=%s" % (fold, n, dict(types)))
    for k, v in picks.most_common(25): print("   ", v, k)
