import json, collections, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "v3.py")).read().split("tab = collections.Counter()")[0])
for r in rows:
    r["o"] = ocat(r["outcome"]); r["s"] = seqclass(r["events"])
    r["cc_oracle"] = any(a[1] == "combo_cast" and a[2].startswith("Thassa's Oracle") for a in r["agentlog"])
    r["cc_exiler"] = [a for a in r["agentlog"] if a[1] == "combo_cast" and not a[2].startswith("Thassa's Oracle")]
W = [r for r in rows if r["o"] == "WON_ORACLE"]
print("WINS", len(W))
c = collections.Counter()
for r in W:
    before = any(e[2].startswith("cast") and ("Consult" in e[2] or "Pact" in e[2]) and e[1] < min(x[1] for x in r["events"] if "cast Thassa" in x[2]) for e in r["events"])
    c[(r["cc_oracle"], bool(r["cc_exiler"]), before)] += 1
    print(r["dir"].split("/")[-1], r["file"][:22], r["game"], r["player"][:22], r["shim"], "ccOracle", r["cc_oracle"], [(e[0], e[2]) for e in r["events"]][:6], [a[2] for a in r["cc_exiler"]])
print("(ccOracle, ccExiler, exilerCastBeforeOracle):", c)
D = [r for r in rows if r["o"] == "DECKED"]
print("DECKED", len(D), "with shim combo_cast of exiler:", sum(1 for r in D if r["cc_exiler"]), "with shim combo_cast of Oracle:", sum(1 for r in D if r["cc_oracle"]))
# Oracle combo_casts: how did each of those 48 seats end?
cc = [r for r in rows if r["cc_oracle"]]
print("seats with Oracle combo_cast:", len(cc), collections.Counter(r["o"] for r in cc), collections.Counter(r["s"] for r in cc))
