import glob, json, re, collections, os
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
res = []
for f in glob.glob(ROOT + "/**/*.jsonl", recursive=True):
    txt = None
    with open(f, encoding="utf-8") as fh:
        data = fh.read()
    if "Tainted Pact" not in data and "Demonic Consultation" not in data:
        continue
    recs = []
    for l in data.splitlines():
        try: recs.append(json.loads(l))
        except Exception: pass
    meta = next((r for r in recs if r.get("rec") == "meta"), {})
    players = meta.get("players") or []; agents = meta.get("agents") or []
    ag = dict(zip(players, agents))
    for i, r in enumerate(recs):
        if r.get("rec") != "entry" or r.get("type") != "STACK_ADD":
            continue
        m = re.match(r"^(Ai\(\d\)-\S+) cast (Tainted Pact|Demonic Consultation)", r.get("message", ""))
        if not m:
            continue
        pl, card = m.group(1), m.group(2)
        # find resolve
        j = i + 1; resolved = False; countered = False
        while j < len(recs) and j < i + 4000:
            q = recs[j]
            if q.get("game") != r.get("game"):
                break
            if q.get("rec") == "entry" and q.get("type") == "STACK_RESOLVE" and q.get("message", "").startswith(card + " ("):
                resolved = True; break
            if q.get("rec") == "entry" and q.get("type") == "ZONE_CHANGE" and "countered" in q.get("message", ""):
                pass
            j += 1
        if not resolved:
            res.append({"file": f, "card": card, "player": pl, "agent": ag.get(pl), "resolved": False})
            continue
        # count zone moves for the player from cast to the next STACK_ADD/STACK_RESOLVE after j
        k = j + 1
        while k < len(recs) and not (recs[k].get("rec") == "entry" and recs[k].get("type") in ("STACK_ADD", "STACK_RESOLVE", "TURN", "PHASE")):
            k += 1
        lib_ex = 0; to_hand = 0; names = []
        for q in recs[i:k]:
            if q.get("rec") == "zone" and q.get("fromPlayer") == pl:
                if q.get("from") == "Library" and q.get("to") == "Exile":
                    lib_ex += 1; names.append(q.get("card"))
                if q.get("to") == "Hand" and q.get("from") in ("Exile", "Library"):
                    to_hand += 1
        res.append({"file": os.path.relpath(f, ROOT), "card": card, "player": pl, "agent": ag.get(pl),
                    "resolved": True, "lib_exiled": lib_ex, "to_hand": to_hand, "names": names[:5]})
json.dump(res, open("pact.json", "w"), indent=1)
for card in ("Tainted Pact", "Demonic Consultation"):
    rs = [r for r in res if r["card"] == card]
    rv = [r for r in rs if r["resolved"]]
    print(card, "casts", len(rs), "resolved", len(rv), "by agent", collections.Counter(r["agent"] for r in rv))
    print("  library->exile count distribution:", sorted(collections.Counter(r["lib_exiled"] for r in rv).items()))
    print("  to_hand distribution:", sorted(collections.Counter(r["to_hand"] for r in rv).items()))
