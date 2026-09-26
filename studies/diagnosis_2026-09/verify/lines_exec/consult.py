import json, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/"
res = json.load(open("pact2.json"))
cs = [r for r in res if r["card"] == "Demonic Consultation" and r["dest"] == "Graveyard"]
cache = {}
out = collections.Counter()
for r in cs:
    f = ROOT + r["file"].replace("\\", "/")
    if f not in cache:
        cache[f] = [json.loads(l) for l in open(f, encoding="utf-8")]
    recs = cache[f]
    g = r["game"]; pl = r["player"]
    res_rec = next((q for q in recs if q.get("rec") == "result" and q.get("game") == g), {})
    won = res_rec.get("winner") == pl
    # oracle zone moves for this player after the consultation turn
    orc = [q for q in recs if q.get("rec") == "zone" and q.get("game") == g and q.get("card") == "Thassa's Oracle" and q.get("turn", 0) >= r["turn"] and q.get("to") in ("Stack", "Battlefield")]
    orc_same = [q for q in orc if q.get("turn") == r["turn"]]
    key = ("big" if r["lib_exiled"] >= 20 else "small", "oracle_same_turn" if orc_same else "no_oracle_same_turn", "won" if won else "lost", "final_turn==t" if res_rec.get("turns") == r["turn"] else "")
    out[key] += 1
    print(r["file"][-40:], "t", r["turn"], "exiled", r["lib_exiled"], "hand", r["to_hand"], "oracle same turn", bool(orc_same), "won", won, "final", res_rec.get("turns"), r["agent"])
print(out)
