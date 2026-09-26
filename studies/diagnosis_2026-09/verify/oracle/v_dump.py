import json, re, sys
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
def dump(path, game, player_sub):
    print("=====", path, "g", game)
    turn = 0
    rows=[]
    for l in open(S+path, encoding="utf-8"):
        try: r=json.loads(l)
        except: continue
        if r.get("game")!=game: continue
        rows.append(r)
    ents=sorted([r for r in rows if r.get("rec")=="entry"], key=lambda r:r["seq"])
    for e in ents:
        m=e["message"]
        if e["type"]=="TURN":
            turn=int(re.match(r"Turn (\d+)",m).group(1)); continue
        if re.search(r"Thassa|Consultation|Tainted Pact|GAME_OUTCOME|Tutor|Gamble|Imperial Seal|Vampiric|Mystical|Worldly|Enlightened|Intuition|Demonic", m) or e["type"]=="GAME_OUTCOME":
            if player_sub in m or e["type"] in ("GAME_OUTCOME","STACK_RESOLVE"):
                print(f"t{turn:3d} seq{e['seq']:5d} {e['type']:14s} {m[:170]}")
    for a in rows:
        if a.get("rec")=="agent" and a["event"] in ("combo_cast","tutor_cast","tutor_steer","combo_hold","line_completion_seen"):
            print("   agent t%s %s %s" % (a["turn"], a["event"], a["detail"][:150]))
    # zone records for Oracle
    for z in rows:
        if z.get("rec")=="zone" and "Thassa" in json.dumps(z):
            print("   zone", json.dumps(z)[:220])
dump("agent_viability/runs_015_default/cell_2iA_Jt0d6sM_rot3.jsonl", 11, "rograkh")
dump("agent_viability/runs_015_default/cell_n7WpsqsZtdQ_rot3.jsonl", 4, "tymna")
dump("agent_viability/runs_015_default/cell_2iA_Jt0d6sM_rot3.jsonl", 2, "rograkh")
dump("agent_viability/runs_016_engine/cell_n7WpsqsZtdQ_rot3.jsonl", 4, "tymna")
