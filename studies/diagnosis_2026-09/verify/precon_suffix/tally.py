import json, glob
recs=[json.load(open(f)) for f in sorted(glob.glob("raw/*.json"))]
print("records", len(recs), "errors", sum(1 for r in recs if "clean_err" in r))
inc=[(r["name"], len(r["clean"]["included"])) for r in recs if r["clean"]["included"]]
print("decks with included:", len(inc), "total included:", sum(x for _,x in inc))
print(inc)
alm=[r for r in recs if r["clean"]["almost_n"]>0]
print("decks with almost:", len(alm), "total almost:", sum(r["clean"]["almost_n"] for r in recs))
print("identity C:", [r["name"] for r in recs if r["clean"]["identity"]=="C"])
WIN = ("Infinite","Win the game","Near-infinite","infinite")
for r in recs:
    for v in r["clean"]["included"]:
        prod = v["produces"]
        flag = any(("nfinite" in p) or ("Win the game" in p) or ("Each opponent loses" in p) or ("damage" in p.lower() and "infinite" in p.lower()) for p in prod)
        print(("*" if flag else " "), r["name"], "|", " + ".join(v["cards"]), "->", "; ".join(prod[:5]))
