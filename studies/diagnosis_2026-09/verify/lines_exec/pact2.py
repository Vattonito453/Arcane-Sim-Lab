import glob, json, re, collections, os
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
res = []
for f in glob.glob(ROOT + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8") as fh:
        data = fh.read()
    if "Tainted Pact" not in data and "Demonic Consultation" not in data:
        continue
    recs = []
    for l in data.splitlines():
        try: recs.append(json.loads(l))
        except Exception: pass
    meta = next((r for r in recs if r.get("rec") == "meta"), {})
    ag = dict(zip(meta.get("players") or [], meta.get("agents") or []))
    zs = [r for r in recs if r.get("rec") == "zone"]
    for i, z in enumerate(zs):
        if z.get("card") not in ("Tainted Pact", "Demonic Consultation") or z.get("to") != "Stack":
            continue
        cid = z.get("cardId"); pl = z.get("fromPlayer"); g = z.get("game")
        # find when it leaves the stack
        j = i + 1
        while j < len(zs) and not (zs[j].get("cardId") == cid and zs[j].get("from") == "Stack" and zs[j].get("game") == g):
            j += 1
        if j >= len(zs):
            continue
        dest = zs[j].get("to")
        lib_ex = [q.get("card") for q in zs[i+1:j] if q.get("fromPlayer") == pl and q.get("from") == "Library" and q.get("to") == "Exile"]
        hand = [q.get("card") for q in zs[i+1:j] if q.get("toPlayer") == pl and q.get("to") == "Hand" and q.get("from") in ("Exile", "Library")]
        # if countered it goes to Graveyard/Exile without resolving; approximate: countered if no lib moves and dest != Graveyard
        res.append({"file": os.path.relpath(f, ROOT), "game": g, "turn": z.get("turn"), "card": z["card"], "player": pl, "agent": ag.get(pl),
                    "dest": dest, "lib_exiled": len(lib_ex), "to_hand": hand, "exiled": lib_ex[:8]})
json.dump(res, open("pact2.json", "w"), indent=1)
for card in ("Tainted Pact", "Demonic Consultation"):
    rs = [r for r in res if r["card"] == card]
    print(card, "stack entries", len(rs), "dest", collections.Counter(r["dest"] for r in rs), "agents", collections.Counter(r["agent"] for r in rs))
    gy = [r for r in rs if r["dest"] == "Graveyard"]
    print("  (dest Graveyard) library->exile dist:", sorted(collections.Counter(r["lib_exiled"] for r in gy).items()))
    print("  max exiled", max((r["lib_exiled"] for r in gy), default=None))
    print("  to_hand count dist:", sorted(collections.Counter(len(r["to_hand"]) for r in gy).items()))
