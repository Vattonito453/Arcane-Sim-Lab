"""Why did a shim tutor_cast fail to find the missing piece?
For each tutor_cast event, find the resolved search_seen (src = tutor, same or
next turn). If comboPick != yes, look up where the missing piece was at that
moment (zone replay: graveyard/exile/library/hand of an opponent...) and
whether its type matches the tutor's search clause."""
import json, re, glob, collections, sys
from pathlib import Path
ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine")
cache = json.loads((ROOT / "engine/card_cache.json").read_text(encoding="utf-8"))
def fact(n):
    k = (n or "").lower(); return cache.get(k) or cache.get(k.split(" // ")[0]) or {}
CL = re.compile(r"search your library(?: and/or graveyard)? for ([^.;\n]*)", re.I)

def type_ok(tutor, piece):
    t = fact(tutor).get("oracle_text") or ""
    m = CL.search(t)
    if not m:
        return None
    clause = m.group(1).lower()
    pt = (fact(piece).get("type_line") or "").lower()
    pcmc = fact(piece).get("cmc") or 0
    if re.search(r"\ba card\b|\bcards\b(?! with)|up to (one|two|three|four) cards|three cards|a card with", clause) and not re.search(r"creature|artifact|enchantment|instant|sorcery|land|equipment|legendary|permanent", clause):
        ok = True
    else:
        ok = False
        for word, need in (("creature", "creature"), ("artifact", "artifact"), ("enchantment", "enchantment"),
                           ("instant", "instant"), ("sorcery", "sorcery"), ("equipment", "equipment"),
                           ("legendary", "legendary"), ("permanent", None), ("dragon", "dragon")):
            if word in clause:
                if need is None:
                    ok = ok or not re.search(r"instant|sorcery", pt)
                elif need in pt:
                    ok = True
        if "green" in clause and "creature" in clause and ok:
            ok = "G" in (fact(piece).get("colors") or []) or "G" in (fact(piece).get("color_identity") or [])
    mv = re.search(r"mana value (\d+) or less", clause)
    if ok and mv and pcmc > int(mv.group(1)):
        ok = False
    return ok

def main():
    S = ROOT / "studies"
    sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
            "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
    agg = collections.Counter(); ex = collections.defaultdict(list)
    pieces = collections.Counter()
    for arm, d in sets.items():
        for fn in sorted(glob.glob(str(S / d / "*.jsonl"))):
            games = collections.defaultdict(lambda: {"z": [], "a": []})
            for line in open(fn, encoding="utf-8"):
                try: r = json.loads(line)
                except Exception: continue
                if r.get("rec") == "zone": games[r["game"]]["z"].append(r)
                elif r.get("rec") == "agent": games[r["game"]]["a"].append(r)
            for g, G in games.items():
                A = G["a"]
                for i, a in enumerate(A):
                    if a["event"] != "tutor_cast": continue
                    m = re.match(r"(.*) seeking (.*)$", a["detail"]); tutor, want = m.groups()
                    ss = [b for b in A if b["event"] == "search_seen" and b["player"] == a["player"]
                          and b["detail"].endswith("src=" + tutor) and 0 <= b["turn"] - a["turn"] <= 1]
                    if not ss:
                        agg["no search_seen for this tutor (activated/transmute/countered)"] += 1
                        ex["nosearch"].append(tutor); continue
                    det = ss[0]["detail"]
                    if "comboPick=yes" in det:
                        agg["missing piece was a legal option"] += 1; continue
                    # where was the piece?
                    zone = None
                    for z in G["z"]:
                        if (z.get("turn") or 0) > a["turn"]: break
                        if z["card"] == want and (z.get("toPlayer") == a["player"] or z.get("fromPlayer") == a["player"]):
                            zone = z["to"]
                    ok = type_ok(tutor, want)
                    tl = (fact(want).get("type_line") or "")
                    if zone in ("Graveyard", "Exile"):
                        k = f"piece in {zone} (not in library)"
                    elif "Land" in tl and "Creature" not in tl:
                        k = "piece is a land"
                    elif ok is False:
                        k = "tutor's type/MV restriction excludes the piece"
                    elif ok is None:
                        k = "tutor has no library clause (e.g. permanent w/ other search)"
                    else:
                        k = "type allows it; piece not offered (MV/X/other)"
                    agg[k] += 1
                    pieces[(tutor, want)] += 1
                    if len(ex[k]) < 6: ex[k].append((tutor, want, zone))
    tot = sum(agg.values())
    print("shim tutor_cast events:", tot)
    for k, v in agg.most_common():
        print(f"  {v:4d} ({100*v/tot:.0f}%)  {k}")
    for k, v in ex.items():
        print("  ex", k, v[:6] if k != "nosearch" else collections.Counter(v).most_common(8))
    print("top failing (tutor, piece):", pieces.most_common(12))

main()
