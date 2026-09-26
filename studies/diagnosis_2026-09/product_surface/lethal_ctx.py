import json, sys, re
RE_LIFE = re.compile(r"^Life:\s*(.+?)\s+(-?\d+)\s*>\s*(-?\d+)")
RE_LOST = re.compile(r"^(.+?) has lost because life total reached 0")
r = json.load(open(sys.argv[1], encoding="utf-8"))
maxn = int(sys.argv[2])
k = 0
for gi, g in enumerate(r["games"], 1):
    flat = [(t.get("turn"), e) for t in g["turns"] for e in t["events"]]
    for i, (turn, e) in enumerate(flat):
        if e.get("action") == "life_change":
            m = RE_LIFE.match(e.get("raw",""))
            if m and int(m.group(3)) <= 0 and int(m.group(2)) > 0:
                print(f"--- game {gi} turn {turn}: {e['raw']}")
                for j in range(max(0, i-5), i+1):
                    print("     ", flat[j][1].get("action"), "|", flat[j][1].get("raw","")[:150])
                k += 1
                if k >= maxn: sys.exit()
