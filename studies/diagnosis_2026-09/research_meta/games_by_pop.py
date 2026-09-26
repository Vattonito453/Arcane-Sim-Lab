# Games per study run, classified by deck population, plus re-ask-loop signature
import os, json, collections, re
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
CEDH = set("alan_tnt ashton_bluefarm cabbage_merchant dallas_bluefarm derevi dexter_kinnan godo godo_archetype isaac_yisan joseph_ral kinnan lily_malcolm_vial magda malcolm_kediss matt_sisay nadu natalie_magda rog_ishai rog_thrasios rograkh_silas selvala_archetype sterling_bluefarm tyler_bluefarm tymna_thrasios winota_ian winota_lua winota_mike winota_rachel yidris".split())
def strip(n): return re.sub(r"^Ai\(\d\)-", "", n)
def key_for(path):
    rel = os.path.relpath(path, ROOT).replace("\\","/")
    parts = rel.split("/")
    if len(parts) >= 4: return "/".join(parts[:3])
    return "/".join(parts[:2])
res = collections.OrderedDict()
for dp, dn, fn in os.walk(ROOT):
    for f in sorted(fn):
        if not f.endswith(".jsonl"): continue
        p = os.path.join(dp, f); k = key_for(p)
        a = res.setdefault(k, dict(games=0, decided=0, timeout=0, pop=collections.Counter(), plan_seats=0,
                                   loop_turns=0, reaim_total=0, to_with_loop=0, to_games=0, games_with_loop=0,
                                   loop_game_timeouts=0))
        pop = None
        reaim = collections.Counter()   # (game,turn,player) -> count
        results = {}
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    m = json.loads(line)
                    names = [strip(x) for x in m.get("players", [])]
                    if any("[20" in n for n in names): pop = "precon"
                    elif any(n in CEDH for n in names): pop = "cEDH"
                    else: pop = "bundled/other"
                    ag = m.get("agents") or []
                    a["plan_seats"] += sum(1 for x in ag if x == "plan")
                elif line.startswith('{"rec":"result"'):
                    r = json.loads(line); results[r["game"]] = r
                elif line.startswith('{"rec":"agent"') and '"kingmaker_reaim"' in line:
                    r = json.loads(line); reaim[(r["game"], r["turn"], r["player"])] += 1
        if pop is None: continue
        a["pop"][pop] += len(results)
        a["games"] += len(results)
        loop_games = set()
        for (g,t,pl), c in reaim.items():
            a["reaim_total"] += c
            if c > 1:
                a["loop_turns"] += 1; loop_games.add(g)
        a["games_with_loop"] += len(loop_games)
        for g, r in results.items():
            if r.get("timedOut"):
                a["to_games"] += 1
                if g in loop_games: a["to_with_loop"] += 1
            if not r.get("draw") and r.get("winner"): a["decided"] += 1
tot = collections.Counter()
for k, a in res.items():
    if a["games"] == 0: continue
    pop = max(a["pop"], key=a["pop"].get)
    tot[pop] += a["games"]
    print(f"{k:42s} pop={dict(a['pop'])} games={a['games']:4d} dec={a['decided']:4d} TO={a['to_games']:4d} "
          f"reaim={a['reaim_total']:6d} loopTurns(>1/turn)={a['loop_turns']:5d} gamesWithLoop={a['games_with_loop']:4d} TOwithLoop={a['to_with_loop']:4d}")
print("TOTAL games by population:", dict(tot), "sum", sum(tot.values()))
