"""Scope: how big a share of the plan seat's tutor casts are shim tutor_cast decisions,
and what the unreachable searches took instead."""
import json, collections, re, glob
from pathlib import Path
S = Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
exec(open("reach.py", encoding="utf-8").read().split("sets = {")[0])  # reuse R, predicates
TUT = set(R)
tot = collections.Counter()
for arm, d in sets.items():
    for fn in sorted(glob.glob(str(S / d / "*.jsonl"))):
        meta = None; tc = collections.Counter(); casts = []
        for line in open(fn, encoding="utf-8"):
            if meta is None and line.startswith("{") and "meta" in line[:40]:
                meta = json.loads(line)
            elif '"rec":"zone"' in line and '"to":"Stack"' in line:
                z = json.loads(line)
                if z["card"] in TUT and z["from"] in ("Hand", "Command"):
                    casts.append((z["game"], z["fromPlayer"], z.get("turn"), z["card"]))
            elif '"tutor_cast"' in line:
                a = json.loads(line); tc[(a["game"], a["player"], a["turn"], a["detail"].split(" seeking ")[0])] += 1
        if meta is None: print("NO META", fn); continue
        plan_seats = {p for p, ag in zip(meta["players"], meta["agents"]) if ag == "plan"}
        for c in casts:
            if c[1] not in plan_seats: continue
            if tc.get(c, 0) > 0:
                tc[c] -= 1; tot[(arm, "shim")] += 1
            else:
                tot[(arm, "stock")] += 1
for arm in sets:
    s, k = tot[(arm, "shim")], tot[(arm, "stock")]
    print(f"{arm}: plan-seat tutor casts {s+k}, shim tutor_cast {s} ({100*s/max(1,s+k):.0f}%)")
S_ = sum(v for (a, w), v in tot.items() if w == "shim"); K = sum(v for (a, w), v in tot.items() if w == "stock")
print(f"ALL: {S_+K} plan-seat tutor casts, {S_} shim-decided ({100*S_/(S_+K):.0f}%)")
rows = json.load(open("reach_rows.json"))
un = [r for r in rows if r["combo"] is False]
print("unreachable-but-searched:", len(un), "picked examples:", collections.Counter((r["tutor"], r["want"], r["picked"]) for r in un).most_common(8))
