import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
f = ROOT + "agent_viability/runs_015_default/cell_2iA_Jt0d6sM_rot0.jsonl"
decks = json.load(open(ROOT + "agent_viability/runs_015_default/plans_2iA_Jt0d6sM.json", encoding="utf-8"))["decks"]
zone = {}; cur = None; n = 0; strict_n = 0
zt = {}  # cardId -> (to, ctl, card, turn)
for line in open(f, encoding="utf-8"):
    if '"rec":"zone"' in line:
        r = json.loads(line)
        if r["game"] != cur: zt = {}; cur = r["game"]
        zt[r["cardId"]] = (r["to"], r.get("toPlayer"), r["card"], r["turn"]); continue
    if '"search_seen"' in line:
        r = json.loads(line)
        p = r["player"]; plan = decks.get(p.split("-", 1)[1], {})
        B = {nm for (zn, ctl, nm, t) in zt.values() if zn == "Battlefield" and ctl == p}
        Bstrict = {nm for (zn, ctl, nm, t) in zt.values() if zn == "Battlefield" and ctl == p and t < r["turn"]}
        asm = [l["cards"] for l in plan.get("lines", []) if set(l["cards"]) <= B]
        asm2 = [l["cards"] for l in plan.get("lines", []) if set(l["cards"]) <= Bstrict]
        if asm:
            n += 1; strict_n += bool(asm2)
            if n <= 6: print(r["game"], r["turn"], p, asm, "| strict:", bool(asm2), "|", r["detail"][:120])
print(n, strict_n)
