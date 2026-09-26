import json, glob, re, os, collections
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl", "human_ceiling/runs/*.jsonl",
        "behavior_rubric/runs_agent/*.jsonl", "behavior_rubric/runs_agent_093/*.jsonl"]
out = collections.Counter()
for pat in PATS:
    for f in glob.glob(S + pat):
        recs = [json.loads(l) for l in open(f, encoding="utf-8")]
        origin = {}
        for r in recs:
            if r.get("rec") == "zone":
                k = (r["game"], r["cardId"])
                if k not in origin and r["from"] in ("Library", "Hand", "Command", "None"):
                    origin[k] = r["card"]
        for r in recs:
            if r.get("rec") == "entry" and r["type"] == "STACK_RESOLVE":
                m = re.match(r"Clock of Omens \((\d+)\) - Untap", r["message"])
                if m:
                    out[origin.get((r["game"], int(m.group(1))), "?")] += 1
print("Clock of Omens untap resolutions by the object's original card:", dict(out))
