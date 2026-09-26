import json
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
cases=[("agent_viability/runs_winmax/cell_n7WpsqsZtdQ_rot3.jsonl",1,"tymna"),
("agent_viability/runs_016_engine/cell_n7WpsqsZtdQ_rot3.jsonl",9,"tymna"),
("agent_viability/runs_016_engine/cell_n7WpsqsZtdQ_rot3.jsonl",12,"tymna")]
for path,g,who in cases:
    rows=[]
    for l in open(S+path,encoding="utf-8"):
        try: r=json.loads(l)
        except: continue
        if r.get("game")==g and r.get("rec")=="zone": rows.append(r)
    # find Consultation Hand->Stack index
    i=[k for k,r in enumerate(rows) if r["card"]=="Demonic Consultation" and r["to"]=="Stack"][0]
    ex=0; tohand=[]; j=i+1
    while j<len(rows) and not (rows[j]["card"]=="Demonic Consultation" and rows[j]["from"]=="Stack"):
        r=rows[j]
        if r["from"]=="Library" and who in r["fromPlayer"]:
            if r["to"]=="Exile": ex+=1
            else: tohand.append((r["card"],r["to"]))
        j+=1
    # library size estimate: count after
    print(path.split('/')[-2],g,"exiled",ex,"to other zones",tohand)
