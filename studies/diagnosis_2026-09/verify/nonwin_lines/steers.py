import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
def kv(detail):
    # parse key=value where values may contain spaces; keys are \w+=
    out = {}
    parts = re.split(r"\s(?=\w+=)", detail)
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1); out[k] = v
    return out
def plans_for(arm_dir, pod):
    cands = glob.glob(ROOT + arm_dir + f"/plans_{pod}.json") + glob.glob(ROOT + arm_dir + f"/plans/plans_{pod}.json")
    return json.load(open(cands[0], encoding="utf-8"))["decks"], cands[0]
def cat(card, plan):
    L = plan.get("lines", [])
    inwin = any(card in l["cards"] and WIN.search(" ; ".join(l.get("produces", []))) for l in L)
    inany = any(card in l["cards"] for l in L)
    return "win" if inwin else ("nonwin" if inany else "notline")
res = {}
for arm, d in ARMS.items():
    C = collections.defaultdict(collections.Counter); used = set(); nfiles = 0
    tops = collections.Counter()
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        pod = m.group(1)
        plans, pf = plans_for(d, pod); used.add(pf); nfiles += 1
        for line in open(f, encoding="utf-8"):
            if '"tutor_steer"' not in line: continue
            r = json.loads(line)
            if r.get("event") != "tutor_steer": continue
            deck = r["player"].split("-", 1)[1]
            x = kv(r["detail"])
            mode = x.get("mode"); card = x.get("steer")
            c = cat(card, plans.get(deck, {}))
            C[mode][c] += 1
            if c == "nonwin": tops[(mode, deck, card)] += 1
    res[arm] = C
    print(f"== {arm} files={nfiles} plans={[os.path.relpath(p, ROOT) for p in sorted(used)]}")
    for mode, cc in sorted(C.items()):
        n = sum(cc.values())
        print(f"   mode={mode:6s} n={n:4d} " + "  ".join(f"{k}={v} ({100*v/n:.0f}%)" for k, v in cc.most_common()))
    print("   top nonwin steer targets:", tops.most_common(8))
