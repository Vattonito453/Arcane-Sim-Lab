import json, glob, os, collections, re
S = r"C:/Users/Vatto/Magic Rules Engine/studies"
LINES = {
 "winota_kiki": ("OuY6mdiXbHU", "winota", ["Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"], "Kiki-Jiki"),
 "cabbage_mill": (None, "cabbage_merchant", ["Nuka-Cola Vending Machine", "Academy Manufactor", "Grinding Station"], "Grinding Station"),
 "cabbage_font": (None, "cabbage_merchant", ["Transmutation Font", "Academy Manufactor", "Clock of Omens"], "Clock of Omens"),
 "magda_torque": (None, "magda", ["Magda, Brazen Outlaw", "Clock of Omens", "Liquimetal Torque"], "Magda, Brazen Outlaw"),
 "derevi_emiel": (None, "derevi", ["Derevi, Empyrial Tactician", "Emiel the Blessed", "Gaea's Cradle"], "Emiel the Blessed"),
 "oboro": (None, "rog_thrasios", ["Oboro Breezecaller", "Talon Gates of Madara", "Gaea's Cradle"], "Oboro Breezecaller"),
}
res = collections.defaultdict(collections.Counter)
for f in glob.glob(S + "/**/*.jsonl", recursive=True):
    d = os.path.relpath(os.path.dirname(f), S)
    txt = None
    bf = collections.defaultdict(set)  # (game, player) -> names
    assembled_games = {}
    acts = collections.Counter()
    winners = {}
    agents = None; players=None
    for line in open(f, encoding="utf-8", errors="replace"):
        if line.startswith('{"rec":"meta"'):
            m = json.loads(line); agents = m.get("agents"); players = m.get("players"); continue
        if line.startswith('{"rec":"zone"'):
            r = json.loads(line)
            c = r["card"]; g = r["game"]
            if r.get("to") == "Battlefield": bf[(g, r.get("toPlayer"))].add(c)
            if r.get("from") == "Battlefield": bf[(g, r.get("fromPlayer"))].discard(c)
            for key, (pod, deck, pieces, actor) in LINES.items():
                p = r.get("toPlayer") or ""
                if deck in p and all(x in bf[(g, p)] for x in pieces):
                    assembled_games.setdefault((key, g, p), r.get("turn"))
        elif line.startswith('{"rec":"entry"') and ("activated" in line or "STACK_ADD" in line):
            r = json.loads(line)
            if r.get("type") != "STACK_ADD": continue
            msg = r.get("message", "")
            for key, (pod, deck, pieces, actor) in LINES.items():
                if msg.startswith("Ai(") and deck in msg.split(" ")[0] and actor in (r.get("card") or "") and "activated" in msg:
                    acts[(key, r["game"])] += 1
        elif line.startswith('{"rec":"result"'):
            r = json.loads(line); winners[r["game"]] = r.get("winner")
    for (key, g, p), t in assembled_games.items():
        seat = players.index(p) if players and p in players else None
        ag = agents[seat] if agents and seat is not None and seat < len(agents) else "?"
        res[key]["assembled_games|" + ag] += 1
        res[key]["assembled_and_won|" + ag] += (winners.get(g) == p)
        res[key]["actor_activations_in_those_games|" + ag] += acts[(key, g)]
        if acts[(key, g)] >= 20: res[key]["games_with_>=20_activations|" + ag] += 1
for k, c in res.items():
    print(k, dict(sorted(c.items())))
