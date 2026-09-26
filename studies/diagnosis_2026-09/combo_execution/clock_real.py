import json, glob, re, os
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl", "human_ceiling/runs/*.jsonl",
        "behavior_rubric/runs_agent/*.jsonl", "behavior_rubric/runs_agent_093/*.jsonl"]
for pat in PATS:
    for f in glob.glob(S + pat):
        recs = [json.loads(l) for l in open(f, encoding="utf-8")]
        origin = {}
        hist = {}
        for r in recs:
            if r.get("rec") == "zone":
                k = (r["game"], r["cardId"])
                hist.setdefault(k, []).append((r["turn"], r["card"], r["from"], r["to"]))
                if k not in origin and r["from"] in ("Library", "Hand", "Command", "None"):
                    origin[k] = r["card"]
        es = [r for r in recs if r.get("rec") == "entry"]
        for i, r in enumerate(es):
            if r["type"] == "STACK_ADD" and "activated Clock of Omens" in r["message"]:
                k = (r["game"], r.get("cardId"))
                if origin.get(k) == "Clock of Omens":
                    print(os.path.relpath(f, S), "game", r["game"], "seq", r["seq"], r["message"][:110])
                    print("     zone history:", hist.get(k)[:6])
                    prev = [q["message"][:90] for q in es[max(0, i-3):i]]
                    print("     before:", prev)
