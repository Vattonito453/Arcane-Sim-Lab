import sys, json, glob, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import games_of, REPO, DATASETS
F = json.load(open(os.path.join(os.path.dirname(__file__), "forge_ai_flags.json")))
KEY = ["Demonic Consultation","Tainted Pact","Thassa's Oracle","Vampiric Tutor","Demonic Tutor","Ad Nauseam","Lion's Eye Diamond",
       "Pact of Negation","Final Fortune","Necrodominance","Culling the Weak","Diabolic Intent","Praetor's Grasp","Mystical Tutor",
       "Imperial Seal","Enlightened Tutor","Worldly Tutor","Gamble","Intuition","Doomsday","Underworld Breach","Dockside Extortionist",
       "Brain Freeze","Mindbreak Trap","Misdirection","Swan Song","Force of Will","Fierce Guardianship","Mana Vault","Lotus Petal",
       "Beseech the Mirror","Wishclaw Talisman","Summoner's Pact","Tymna the Weaver","Rhystic Study","Mystic Remora","Jeska's Will",
       "Deflecting Swat","Dark Ritual","Cabal Ritual","Birthing Pod","Chord of Calling","Green Sun's Zenith","Finale of Devastation"]
out = collections.Counter()
for ds in sys.argv[1:]:
    for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
        for meta, g, ents, lives in games_of(f):
            pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
            fate = {}
            for r in lives:
                if r.get("rec") != "zone": continue
                cid, fr, to = r.get("cardId"), r.get("from"), r.get("to")
                if to == "Hand" and r.get("toPlayer") and cid not in fate:
                    fate[cid] = [r.get("toPlayer"), r.get("card"), "held"]
                elif fr == "Hand" and cid in fate and fate[cid][2] == "held":
                    if to == "Library" and (r.get("turn") or 0) == 0: del fate[cid]; continue
                    fate[cid][2] = {"Stack": "cast", "Battlefield": "put", "Graveyard": "gy"}.get(to, to)
            for cid, (p, nm, st) in fate.items():
                if nm in KEY:
                    out[(nm, pilot.get(p), "n")] += 1
                    out[(nm, pilot.get(p), st)] += 1
print(f"{'card':26s} {'flag':8s} {'stock drawn':>11s} {'cast%':>6s} {'held%':>6s} | {'plan drawn':>10s} {'cast%':>6s} {'held%':>6s}")
for nm in KEY:
    fl = "All" if "RemoveDeck:All" in (F.get(nm) or []) else ("Random" if "RemoveDeck:Random" in (F.get(nm) or []) else "")
    row = []
    for pl in ("stock", "plan"):
        n = out[(nm, pl, "n")]
        row.append((n, out[(nm, pl, "cast")] / n if n else 0, out[(nm, pl, "held")] / n if n else 0))
    if row[0][0] + row[1][0] == 0: continue
    print(f"{nm:26s} {fl:8s} {row[0][0]:11d} {row[0][1]:6.2f} {row[0][2]:6.2f} | {row[1][0]:10d} {row[1][1]:6.2f} {row[1][2]:6.2f}")
