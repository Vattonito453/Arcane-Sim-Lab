import json
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
cases=[("agent_viability/runs_015_default/cell_2iA_Jt0d6sM_rot3.jsonl",11),
("agent_viability/runs_015_default/cell_n7WpsqsZtdQ_rot3.jsonl",4),
("agent_viability/runs_015_default/cell_2iA_Jt0d6sM_rot3.jsonl",2)]
TUT={"Demonic Tutor","Vampiric Tutor","Imperial Seal","Grim Tutor","Gamble","Mystical Tutor","Diabolic Intent","Tainted Pact","Wishclaw Talisman","Intuition","Personal Tutor","Merchant Scroll","Scheming Symmetry","Beseech the Mirror","Enlightened Tutor","Worldly Tutor","Summoner's Pact","Crop Rotation","Lim-D\u00fbl's Vault","Solve the Equation","Muddle the Mixture","Final Parting","Night's Whisper"}
for path,g in cases:
    print("=====",path.split('/')[-2],path.split('/')[-1],g)
    for l in open(S+path,encoding="utf-8"):
        try: r=json.loads(l)
        except: continue
        if r.get("game")!=g or r.get("rec")!="zone": continue
        if r["card"] in ("Demonic Consultation","Thassa's Oracle","Tainted Pact") or (r["card"] in TUT and r["to"] in ("Hand","Stack")):
            print("  t%s %s %s: %s -> %s (%s)"%(r["turn"],r["phase"],r["card"],r["from"],r["to"],r.get("fromPlayer") or r.get("toPlayer")))
