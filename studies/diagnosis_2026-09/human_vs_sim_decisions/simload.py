"""Loader for raw shim JSONL: per-game entries + real-time stream (zone/agent/rubric)."""
import json, re, glob, os, collections
ROOT = "C:/Users/Vatto/Magic Rules Engine"
AI = re.compile(r"^Ai\(\d+\)-")
TURN = re.compile(r"^Turn (\d+) \((.+)\)$")
def bare(p): return AI.sub("", p or "")

PODS = ["2iA_Jt0d6sM","5A6o18Bra0Y","B421mac67IE","Bq-nFi0f1jA","CxKMqO36DdM","OuY6mdiXbHU","n7WpsqsZtdQ","sZA0KqXCGrY"]
def pod_of(path):
    b = os.path.basename(path).replace("hcpilot","").replace("hc_pilot_","hc_")
    for p in PODS:
        if p in b or p.replace("_","") in b: return p
    return None

_plans = {}
def plans(pod):
    if pod not in _plans:
        f = f"{ROOT}/studies/behavior_rubric/plans_{pod}.json"
        _plans[pod] = json.load(open(f, encoding="utf-8"))["decks"] if os.path.exists(f) else {}
    return _plans[pod]

_cmdr = {}
def commanders(pod, deck):
    k=(pod,deck)
    if k not in _cmdr:
        f = f"{ROOT}/studies/human_ceiling/decks/{pod}/dck/{deck}.dck"
        out=[]; sec=None
        if os.path.exists(f):
            for line in open(f, encoding="utf-8"):
                line=line.strip()
                if line.startswith("["): sec=line.lower(); continue
                if sec=="[commander]" and line:
                    m=re.match(r"(\d+)\s+(.+?)(\|.*)?$", line)
                    if m: out.append(m.group(2).strip())
        _cmdr[k]=out
    return _cmdr[k]

def load(path):
    """Yield game dicts from one JSONL file."""
    meta=None; games=collections.OrderedDict()
    for line in open(path, encoding="utf-8"):
        try: r=json.loads(line)
        except Exception: continue
        rec=r.get("rec")
        if rec=="meta": meta=r; continue
        g=r.get("game")
        if g is None: continue
        G=games.setdefault(g, {"entries":[], "stream":[], "result":None})
        if rec=="entry": G["entries"].append(r)
        elif rec=="result": G["result"]=r
        else: G["stream"].append(r)
    pod=pod_of(path)
    for g,G in games.items():
        if G["result"] is None: continue
        G["file"]=path; G["pod"]=pod; G["idx"]=g; G["meta"]=meta
        G["players"]=list(meta.get("players",[])) if meta else []
        G["agents"]=dict(zip(G["players"], meta.get("agents",[]))) if meta else {}
        # turn map
        tp={}; own=collections.Counter(); ownround={}
        for e in G["entries"]:
            if e.get("type")=="TURN":
                m=TURN.match(e["message"])
                if m:
                    t=int(m.group(1)); p=m.group(2); own[p]+=1; tp[t]=p; ownround[t]=own[p]
        G["turn_player"]=tp; G["turn_round"]=ownround; G["own_turns"]=dict(own)
        # entry -> global turn
        cur=0
        for e in G["entries"]:
            if e.get("type")=="TURN":
                m=TURN.match(e["message"]); cur=int(m.group(1)) if m else cur
            e["_turn"]=cur
        G["last_turn"]=cur
        yield G

def round_of(G, turn):
    """Table round at a global turn = own-turn count of the active player."""
    return G["turn_round"].get(turn, 0)

def player_round(G, player, turn):
    """How many turns `player` has started up to and including global turn."""
    n=0
    for t,p in G["turn_player"].items():
        if p==player and t<=turn: n+=1
    return n

def win_info(G):
    res=G["result"]; w=res.get("winner")
    info={"winner":w, "timedOut":res.get("timedOut"), "turnCapped":res.get("turnCapped"), "draw":res.get("draw")}
    info["win_round"]= G["own_turns"].get(w) if w else None
    # method: for each loser, find the LIFE entry that took them <=0 and the DAMAGE just before
    ents=G["entries"]; method=collections.Counter(); spell=None
    for e in ents:
        if e.get("type")=="GAME_OUTCOME":
            m=re.search(r"won by spell '([^']+)'|effect of '([^']+)'|effect of spell '([^']+)'", e["message"])
            if m: spell=[x for x in m.groups() if x][0]
    life_re=re.compile(r"Life: (.+) (-?\d+) > (-?\d+)")
    for i,e in enumerate(ents):
        if e.get("type")!="LIFE": continue
        m=life_re.match(e["message"])
        if not m: continue
        who,a,b=m.group(1),int(m.group(2)),int(m.group(3))
        if b<=0 and a>0:
            kind="lifeloss"
            for j in range(i-1,max(0,i-40),-1):
                if ents[j].get("type")=="DAMAGE" and ents[j]["message"].rstrip(".").endswith(who):
                    kind="combat" if " combat damage" in ents[j]["message"] else "noncombat"
                    break
                if ents[j].get("type")=="LIFE": break
            method[kind]+=1
    if spell: info["method"]="spell:"+spell
    elif not w: info["method"]="none"
    elif method: info["method"]=max(method, key=method.get)
    else: info["method"]="other"
    info["kill_kinds"]=dict(method)
    return info
