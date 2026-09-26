import json, sys
p, n, k = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
r = json.load(open(p, encoding="utf-8"))
g = r["games"][n-1]
print(g["players"], g["result"])
for t in g["turns"][-k:]:
    print("--- turn", t.get("turn"), t.get("active_player"), "round", t.get("round"))
    for e in t["events"]:
        raw = e.get("raw","")
        print("  ", e.get("action"), "|", raw[:220].replace("\n"," / "))
