import json, sys
p = sys.argv[1]; names = sys.argv[2].split("|"); maxg = int(sys.argv[3])
r = json.load(open(p, encoding="utf-8"))
shown = 0
for gi, g in enumerate(r["games"], 1):
    zs = [z for z in g.get("zones", []) if z.get("card") in names and ("Battlefield" in (z.get("to"), z.get("from")))]
    have = {z["card"] for z in zs if z.get("to") == "Battlefield"}
    if len(have) < len(names): continue
    print(f"=== game {gi} players {g['players']}")
    for z in zs:
        print("   ZONE t%s %s: %s -> %s (%s) id=%s" % (z.get("turn"), z.get("card"), z.get("from"), z.get("to"), z.get("toPlayer") or z.get("fromPlayer"), z.get("cardId")))
    # text mentions
    for t in g["turns"]:
        for e in t["events"]:
            raw = e.get("raw","")
            if any(n in raw for n in names) and e.get("action") in ("stack_add","stack_resolve","zone_change","land_drop"):
                print("   TEXT t%s %s | %s" % (t["turn"], e.get("action"), raw[:140]))
    shown += 1
    if shown >= maxg: break
