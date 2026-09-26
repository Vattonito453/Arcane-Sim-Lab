import json, sys, re, collections
for f in sys.argv[1:]:
    picks = []; errs = []; res = None; agent = collections.Counter(); casts = collections.Counter()
    for l in open(f, encoding="utf-8", errors="replace"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("rec") == "agent":
            agent[r["event"]] += 1
            if r["event"] == "sim_pick": picks.append(r)
            if r["event"] == "sim_error": errs.append(r)
        elif r.get("rec") == "result": res = r
        elif r.get("rec") == "entry" and r.get("type") == "STACK_ADD" and "Kilo Omega" in r.get("message", "") and (" cast " in r["message"] or " activated " in r["message"]):
            casts[" cast " in r["message"] and "cast" or "activated"] += 1
    print("===", f.split("/")[-1])
    print("result:", {k: res.get(k) for k in ("winner", "turns", "timedOut", "turnCapped", "ms", "error", "errorClass")} if res else None)
    print("agent events:", dict(agent))
    print("plan-seat casts/activations:", dict(casts))
    ms = [int(re.search(r"ms=(\d+)", p["detail"]).group(1)) for p in picks]
    if ms:
        tot = sum(ms); ms_sorted = sorted(ms)
        print("sim_pick n=%d total=%.1fs mean=%.0fms p50=%d p90=%d max=%d" % (len(ms), tot / 1000, tot / len(ms), ms_sorted[len(ms) // 2], ms_sorted[int(len(ms) * .9)], ms_sorted[-1]))
        byturn = collections.defaultdict(int)
        for p, m in zip(picks, ms): byturn[p["turn"]] += m
        print("sim ms by turn:", dict(sorted(byturn.items())))
    diff = [p for p in picks if " | stock=" in p["detail"] and p["detail"].split(" pick=")[1].split(" | stock=")[0] != p["detail"].split(" | stock=")[1].split(" cfms=")[0]]
    print("decisions where sim pick != stock pick: %d of %d" % (len(diff), len(picks)))
    for p in diff[:40]:
        d = p["detail"]; print("  t%d %s | sim=%s | stock=%s" % (p["turn"], re.search(r"phase=(\S+)", d).group(1), d.split(" pick=")[1].split(" | stock=")[0], d.split(" | stock=")[1].split(" cfms=")[0]))
    for e in errs[:10]: print("  ERR t%d %s" % (e["turn"], e["detail"][:200]))
