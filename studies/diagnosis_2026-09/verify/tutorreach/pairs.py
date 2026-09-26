import json, glob, collections, re
from pathlib import Path
S = Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
tut = collections.Counter(); pairs = collections.Counter(); n=0
for arm, d in sets.items():
    for fn in sorted(glob.glob(str(S / d / "*.jsonl"))):
        for line in open(fn, encoding="utf-8"):
            if '"tutor_cast"' not in line: continue
            r = json.loads(line)
            t, p = re.match(r"(.*) seeking (.*)$", r["detail"]).groups()
            tut[t]+=1; pairs[(t,p)]+=1; n+=1
print(n)
for t,c in tut.most_common(): print(c, t)
print()
for k,c in pairs.most_common(): print(c, k)
