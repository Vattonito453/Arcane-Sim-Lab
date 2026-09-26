"""Independent re-check of 'tutor_cast cannot reach piece'.
Per tutor_cast event:
  actual  - did the tutor card move Hand/Command -> Stack for that player that turn (zone stream)?
  search  - the first unclaimed search_seen by that player with src=tutor after the event (turn t..t+1)
  outcome - comboPick yes/-, and whether search_seen.missing == sought piece
  loc     - where the sought piece was just before the tutor left hand (zone replay)
  legal   - hand-coded tutor predicate vs piece type/MV/colour (independent of the investigator's regex)
"""
import json, glob, collections, re, sys
from pathlib import Path
ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine")
S = ROOT / "studies"
cache = json.loads((ROOT / "engine/card_cache.json").read_text(encoding="utf-8"))
def fact(n):
    k = (n or "").lower(); return cache.get(k) or cache.get(k.split(" // ")[0]) or {}
def tl(n): return (fact(n).get("type_line") or "")
def mv(n): return fact(n).get("cmc") or 0
def green(n): return "G" in (fact(n).get("colors") or [])
def power(n):
    try: return int(fact(n).get("power"))
    except Exception: return None
C = lambda n: "Creature" in tl(n)
A = lambda n: "Artifact" in tl(n)
E = lambda n: "Enchantment" in tl(n)
IS = lambda n: ("Instant" in tl(n) or "Sorcery" in tl(n))
LAND = lambda n: "Land" in tl(n) and not C(n)
ANY = lambda n: True
# kind: resolve = search when the spell/ETB resolves; activated = permanent whose search is an
# activated ability; transmute = search only via transmute (castableSpell casts the spell half)
R = {
 "Worldly Tutor": ("resolve", C), "Enlightened Tutor": ("resolve", lambda n: A(n) or E(n)),
 "Mystical Tutor": ("resolve", IS), "Eldritch Evolution": ("resolve", C),
 "Summoner's Pact": ("resolve", lambda n: C(n) and green(n)), "Vampiric Tutor": ("resolve", ANY),
 "Shared Summons": ("resolve", C), "Tezzeret, Cruel Captain": ("activated", lambda n: A(n) and mv(n) <= 1),
 "Spellseeker": ("resolve", lambda n: IS(n) and mv(n) <= 2), "Neoform": ("resolve", C),
 "Ranger-Captain of Eos": ("resolve", lambda n: C(n) and mv(n) <= 1), "Gamble": ("resolve", ANY),
 "Reckless Handling": ("resolve", A), "Beseech the Mirror": ("resolve", ANY),
 "Muddle the Mixture": ("transmute", lambda n: mv(n) == 2), "Chord of Calling": ("resolve", C),
 "Trinket Mage": ("resolve", lambda n: A(n) and mv(n) <= 1), "Dizzy Spell": ("transmute", lambda n: mv(n) == 1),
 "Natural Order": ("resolve", lambda n: C(n) and green(n)),
 "Imperial Recruiter": ("resolve", lambda n: C(n) and (power(n) is not None and power(n) <= 2)),
 "Fierce Empath": ("resolve", lambda n: C(n) and mv(n) >= 6), "Birthing Pod": ("activated", C),
 "Goblin Engineer": ("resolve", A), "Demonic Tutor": ("resolve", ANY), "Imperial Seal": ("resolve", ANY),
 "Intuition": ("resolve", ANY), "Green Sun's Zenith": ("resolve", lambda n: C(n) and green(n)),
 "Wishclaw Talisman": ("activated", ANY), "Tezzeret the Seeker": ("activated", A),
 "Captain Sisay": ("activated", lambda n: "Legendary" in tl(n)), "Kuldotha Forgemaster": ("activated", A),
 "Diabolic Intent": ("resolve", ANY), "Drift of Phantasms": ("transmute", lambda n: mv(n) == 3),
 "Wargate": ("resolve", lambda n: not IS(n)), "Grim Tutor": ("resolve", ANY), "Idyllic Tutor": ("resolve", E),
 "Gifts Ungiven": ("resolve", ANY),
 "Sisay, Weatherlight Captain": ("activated", lambda n: "Legendary" in tl(n) and not IS(n)),
 "Woodland Bellower": ("resolve", lambda n: C(n) and green(n) and "Legendary" not in tl(n) and mv(n) <= 3),
 "Transmute Artifact": ("resolve", A), "Nature's Rhythm": ("resolve", C),
 "Goblin Matron": ("resolve", lambda n: "Goblin" in tl(n)), "Tooth and Nail": ("resolve", C),
 "Trophy Mage": ("resolve", lambda n: A(n) and mv(n) == 3), "Solve the Equation": ("resolve", IS),
 "Demonic Counsel": ("resolve", ANY),
 "Moggcatcher": ("activated", lambda n: "Goblin" in tl(n)),
}
sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
if len(sys.argv) > 1:
    sets = dict(a.split("=", 1) for a in sys.argv[1:])
out = []
for arm, d in sets.items():
    for fn in sorted(glob.glob(str(S / d / "*.jsonl"))):
        games = collections.defaultdict(lambda: {"z": [], "a": []})
        for line in open(fn, encoding="utf-8"):
            if '"rec":"zone"' in line or '"rec":"agent"' in line:
                r = json.loads(line)
                games[r["game"]]["z" if r["rec"] == "zone" else "a"].append(r)
        for g, G in games.items():
            A_, Z = G["a"], G["z"]
            claimed_ss = set(); claimed_z = set()
            for i, a in enumerate(A_):
                if a["event"] != "tutor_cast": continue
                tutor, want = re.match(r"(.*) seeking (.*)$", a["detail"]).groups()
                p, t = a["player"], a["turn"]
                zi = None
                for k, z in enumerate(Z):
                    if k in claimed_z: continue
                    if z["card"] == tutor and z["from"] in ("Hand", "Command") and z["to"] == "Stack" \
                       and z.get("fromPlayer") == p and z.get("turn") == t:
                        zi = k; break
                if zi is not None: claimed_z.add(zi)
                loc = "Library"
                lim = zi if zi is not None else next((k for k, z in enumerate(Z) if (z.get("turn") or 0) > t), len(Z))
                for k in range(lim):
                    z = Z[k]
                    if z["card"] == want and (z.get("toPlayer") == p or z.get("fromPlayer") == p):
                        loc = z["to"]
                ss = None
                for j in range(i + 1, len(A_)):
                    b = A_[j]
                    if b["turn"] > t + 1: break
                    if j in claimed_ss: continue
                    if b["event"] == "search_seen" and b["player"] == p and b["detail"].endswith("src=" + tutor):
                        ss = j; break
                rec = {"arm": arm, "file": Path(fn).name, "game": g, "turn": t, "player": p, "tutor": tutor,
                       "want": want, "actual": zi is not None, "loc": loc}
                kind, pred = R.get(tutor, ("?", None))
                rec["kind"] = kind
                rec["legal_type"] = None if pred is None else bool(pred(want))
                if ss is not None:
                    claimed_ss.add(ss)
                    det = A_[ss]["detail"]
                    rec["combo"] = "comboPick=yes" in det
                    m = re.search(r" missing=(.*?) picked=", det); rec["ss_missing"] = m.group(1) if m else None
                    m = re.search(r" picked=(.*?) planPick=", det); rec["picked"] = m.group(1) if m else None
                    m = re.search(r" options=(\d+)", det); rec["options"] = int(m.group(1))
                    m = re.search(r" dest=(\S+)", det); rec["dest"] = m.group(1)
                else:
                    rec["combo"] = None
                out.append(rec)
json.dump(out, open("reach_rows.json", "w"), indent=0)
N = len(out); print("tutor_cast events:", N)
act = [r for r in out if r["actual"]]; print("with an actual Hand/Command->Stack move same turn:", len(act))
dup = collections.Counter((r["file"], r["game"], r["player"], r["tutor"], r["turn"]) for r in out)
print("events sharing (game,player,tutor,turn) with another event:", sum(c for c in dup.values() if c > 1))
def cls(r):
    if r["combo"] is True:
        return "A reachable: comboPick=yes" + ("" if r["ss_missing"] == r["want"] else " (missing differs from sought)")
    if r["combo"] is False:
        if r["loc"] != "Library": return "B searched; piece in " + r["loc"]
        if LAND(r["want"]): return "C searched; piece is a land"
        if r["legal_type"] is False: return "D searched; tutor restriction excludes piece"
        return "E searched; type allows; piece not offered"
    if not r["actual"]: return "F no search: tutor never left hand that turn"
    return "G no search: cast, no search (" + r["kind"] + ")"
agg = collections.Counter(cls(r) for r in out)
for k, v in sorted(agg.items()): print(f"  {v:4d} ({100*v/N:4.1f}%)  {k}")
print()
print("per arm reachable/total (and per actual cast):")
for arm in sets:
    rr = [r for r in out if r["arm"] == arm]
    ra = [r for r in rr if r["actual"]]
    print(" ", arm, sum(1 for r in rr if r["combo"]), "/", len(rr), " actual:", sum(1 for r in ra if r["combo"]), "/", len(ra))
tot_act = [r for r in out if r["actual"]]
print("reachable among ACTUAL casts:", sum(1 for r in tot_act if r["combo"]), "/", len(tot_act))
agg2 = collections.Counter(cls(r) for r in tot_act)
for k, v in sorted(agg2.items()): print(f"  {v:4d} ({100*v/len(tot_act):4.1f}%)  {k}")
stat = collections.Counter()
for r in out:
    if r["legal_type"] is None: stat["unknown tutor"] += 1
    if r["legal_type"] is False: stat["static type/MV restriction excludes piece"] += 1
    if LAND(r["want"]): stat["sought piece is a land"] += 1
    if r["kind"] == "transmute": stat["transmute tutor"] += 1
    if r["kind"] == "activated": stat["activated-ability tutor"] += 1
    if r["loc"] in ("Graveyard", "Exile"): stat["piece in gy/exile at cast"] += 1
print("static:", dict(stat))
