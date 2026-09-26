"""Independent re-check of tutor_cast reach, fetch outcome, and search offer.
Same five run dirs the finding used (447 tutor_cast / 414 combo_cast)."""
import json, glob, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fidx
idx = fidx.load()
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl"]

rows = []
searches = []
for pat in PATS:
    for f in sorted(glob.glob(S + pat)):
        zones = collections.defaultdict(list)
        agents = collections.defaultdict(list)
        winners = {}
        for l in open(f, encoding="utf-8"):
            if '"rec":"zone"' in l:
                r = json.loads(l); zones[r["game"]].append(r)
            elif '"rec":"agent"' in l:
                r = json.loads(l); agents[r["game"]].append(r)
            elif '"rec":"result"' in l:
                r = json.loads(l); winners[r["game"]] = r.get("winner")
        for g, ags in agents.items():
            zs = zones[g]
            ss = [a for a in ags if a["event"] == "search_seen"]
            steers = [a for a in ags if a["event"] == "tutor_steer"]
            for a in ss:
                d = a["detail"]
                kv = dict(re.findall(r"(\w+)=(\S+)", d.split(" missing=")[0]))
                missing = re.search(r" missing=(.*?) picked=", d).group(1)
                src = d.split(" src=", 1)[1]
                searches.append({"file": f, "game": g, "player": a["player"], "turn": a["turn"],
                                 "sid": kv["sid"], "sighted": kv["sighted"], "comboPick": kv["comboPick"],
                                 "missing": missing, "src": src, "options": int(kv["options"]),
                                 "dest": kv.get("dest")})
            for a in ags:
                if a["event"] != "tutor_cast":
                    continue
                p, t = a["player"], a["turn"]
                tutor, want = a["detail"].split(" seeking ", 1)
                # moment of the tutor's cast: first Hand->Stack of tutor by p in turn t
                cut = None
                for i, z in enumerate(zs):
                    if z.get("turn") == t and z["card"] == tutor and z["from"] == "Hand" and z["to"] == "Stack" \
                            and z.get("fromPlayer") == p:
                        cut = i; break
                cast = cut is not None
                if cut is None:
                    cut = next((i for i, z in enumerate(zs) if (z.get("turn") or 0) >= t), len(zs))
                # location of sought card (own, nontoken) before cut
                loc = None
                for z in zs[:cut]:
                    if z["card"] == want and not z.get("token") and (z.get("fromPlayer") == p or z.get("toPlayer") == p):
                        loc = z["to"]
                if loc is None:
                    first = next((z for z in zs if z["card"] == want and not z.get("token")
                                  and (z.get("fromPlayer") == p or z.get("toPlayer") == p)), None)
                    loc = first["from"] if first else "Library(never moved)"
                # did the piece leave the library for p within [t, t+4]
                fetched = any(z["card"] == want and z["from"] == "Library" and z["to"] != "Library"
                              and z.get("toPlayer") == p and t <= (z.get("turn") or 0) <= t + 4 for z in zs)
                # after cut, direct search move: Library -> Hand/Battlefield/Graveyard/Exile in turn t..t+4
                fetched_any_later = any(z["card"] == want and z["from"] == "Library" and z["to"] != "Library"
                                        and z.get("toPlayer") == p and (z.get("turn") or 0) >= t for z in zs)
                # linked search_seen by src==tutor from p in [t, t+4]
                link = next((s for s in ss if s["player"] == p and s["detail"].endswith(" src=" + tutor)
                             and t <= s["turn"] <= t + 4), None)
                lk = None
                if link:
                    d = link["detail"]
                    lk = {"comboPick": re.search(r"comboPick=(\S+)", d).group(1),
                          "missing": re.search(r" missing=(.*?) picked=", d).group(1),
                          "sid": re.search(r"sid=(\d+)", d).group(1)}
                rows.append({"file": os.path.relpath(f, S).replace("\\", "/"), "game": g, "player": p, "turn": t,
                             "tutor": tutor, "want": want, "cast": cast, "loc": loc,
                             "reach": fidx.reach(idx, tutor, want),
                             "reach_strict": fidx.reach(idx, tutor, want, strict=True),
                             "fetched": fetched, "fetched_later": fetched_any_later, "link": lk,
                             "won": winners.get(g) == p})

json.dump({"rows": rows, "searches": searches}, open(os.path.join(HERE, "tc_rows.json"), "w"), indent=0)
print("tutor_cast events:", len(rows))
uniq = {(r["file"], r["game"], r["player"], r["turn"], r["tutor"], r["want"]) for r in rows}
print("unique (file,game,player,turn,tutor,want):", len(uniq))
C = collections.Counter
print("reach type-only:", C(r["reach"] for r in rows))
print("reach strict (fixed cmc/power/color):", C(r["reach_strict"] for r in rows))
print("tutor actually went Hand->Stack in that turn:", C(r["cast"] for r in rows))
print("sought card location at cast:", C(r["loc"] for r in rows).most_common())
print("fetched within t..t+4:", C(r["fetched"] for r in rows))
print("fetched ever after t:", C(r["fetched_later"] for r in rows))
print("linked search found:", C(r["link"] is not None for r in rows))
print("linked search comboPick:", C((r["link"] or {}).get("comboPick") for r in rows))
print("linked search missing == want:", C(((r["link"] or {}).get("missing") == r["want"]) for r in rows if r["link"]))
print("cannot-reach examples:", C((r["tutor"], r["want"]) for r in rows if r["reach"] is False).most_common(25))
print("unknown reach:", C((r["tutor"], r["want"]) for r in rows if r["reach"] is None).most_common(15))
print("by tutor:", C(r["tutor"] for r in rows).most_common(40))
