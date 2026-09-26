import json, glob, os, collections, re
S = r"C:/Users/Vatto/Magic Rules Engine/studies"
per = collections.defaultdict(collections.Counter)
for f in glob.glob(S + "/**/*.jsonl", recursive=True):
    d = os.path.relpath(os.path.dirname(f), S)
    for line in open(f, encoding="utf-8", errors="replace"):
        if "Portal to Phyrexia" not in line or '"rec":"agent"' not in line: continue
        r = json.loads(line)
        ev, det = r["event"], r["detail"]
        if ev == "search_seen":
            m = re.search(r"picked=(.*?) planPick=(.*)$", det)
            picked, plan = (m.group(1), m.group(2)) if m else ("?", "?")
            agree = "agree=true" in det
            if picked == "Portal to Phyrexia" and not agree: per[d]["seen_stock_portal_plan_other"] += 1
            elif picked == "Portal to Phyrexia" and agree: per[d]["seen_portal_agree"] += 1
            elif plan == "Portal to Phyrexia": per[d]["seen_plan_portal"] += 1
            else: per[d]["seen_other_mention"] += 1
        elif ev == "tutor_steer":
            per[d]["steer:" + ("from_portal" if re.search(r"(stock|from|instead of)[^,]*Portal", det) else "mention")] += 1
            per[d]["steer_example"] = det[:200] if isinstance(per[d].get("steer_example"), int) or "steer_example" not in per[d] else per[d]["steer_example"]
        else:
            per[d][ev] += 1
tot = collections.Counter()
for d, c in sorted(per.items()):
    ex = c.pop("steer_example", None)
    print(d, dict(c)); 
    if ex: print("   ex:", ex)
    tot.update({k: v for k, v in c.items() if isinstance(v, int)})
print("TOTAL", dict(tot))
