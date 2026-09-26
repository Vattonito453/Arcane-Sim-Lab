import json
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
cases=[("agent_viability/runs_winmax/cell_n7WpsqsZtdQ_rot3.jsonl",1,960),
("agent_viability/runs_016_engine/cell_2iA_Jt0d6sM_rot3.jsonl",7,506),
("agent_viability/runs_016_engine/cell_n7WpsqsZtdQ_rot3.jsonl",9,996),
("agent_viability/runs_016_engine/cell_n7WpsqsZtdQ_rot3.jsonl",12,783),
("behavior_rubric/runs_agent/Bq-nFi0f1jA_rot0.jsonl",0,1808)]
for path,g,seq in cases:
    print("=====",path,g,seq)
    ents=[];zones=[]
    for l in open(S+path,encoding="utf-8"):
        try: r=json.loads(l)
        except: continue
        if r.get("game")!=g: continue
        if r.get("rec")=="entry": ents.append(r)
    ents.sort(key=lambda r:r["seq"])
    for e in ents:
        if seq-6<=e["seq"]<=seq+8 and e["type"] not in ("PHASE",):
            print(e["seq"],e["type"],e["message"][:220])
    for e in ents:
        if e["type"]=="GAME_OUTCOME": print("  ",e["message"])
