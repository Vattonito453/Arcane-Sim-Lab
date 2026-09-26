import json, collections, sys, os
from pathlib import Path
os.environ["MTG_DATA_DIR"] = str(Path("data").resolve()); os.environ["MTG_OFFLINE"] = "1"
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import cards
rows = json.load(open("plan_audit.json"))
flags = json.load(open("forge_flags.json"))
cache = json.load(open("data/combo_cache.json", encoding="utf-8"))
desc = {}
for v in cache.values():
    for x in v["included"]: desc[frozenset(x["cards"])] = x["description"]
T = collections.Counter(); perdeck = []
flagged_pieces = collections.Counter()
for r in rows:
    if not r["lines"]: continue
    cedh = "/" in r["deck"]
    L = r["lines"]; n = len(L)
    sets = [frozenset(a["cards"]) for a in L]
    exact_dup = n - len(set(sets))
    superset = sum(1 for i, s in enumerate(sets) if any(j != i and sets[j] < s for j in range(n)))
    c = collections.Counter()
    for a in L:
        grp = "cEDH" if cedh else "other"
        c["lines"] += 1
        c["win"] += a["cls"] == "win"
        c["resource_only"] += a["cls"] == "resource"
        c["4plus_pieces"] += a["n"] >= 4
        c["nonB_zone_piece"] += bool(a["nonB"])
        c["graveyard_exile_library_piece"] += any(set(z) & set("GEL") and "H" not in z and "B" not in z for z in a["nonB"].values())
        c["hand_only_permanent_piece"] += any(z == "H" and cards.is_permanent(cn) for cn, z in a["nonB"].items())
        c["template_requires"] += bool(a["requires"])
        c["easy_prereq"] += bool(a["easy"])
        c["notable_prereq"] += bool(a["notable"])
        c["any_prereq_or_template"] += bool(a["requires"] or a["easy"] or a["notable"])
        c["dfc_slash_name"] += any(" // " in x for x in a["cards"])
        d = desc.get(frozenset(a["cards"]), "")
        c["loop_needs_activation"] += ("Activate" in d or "activate" in d or "Tap " in d)
        fl = [x for x in a["cards"] if (flags.get(x) or flags.get(x.split(" // ")[0]) or {}).get("removeDeck")]
        c["forge_ai_flagged_piece"] += bool(fl)
        c["forge_ai_flag_All"] += any("All" in (flags.get(x) or flags.get(x.split(' // ')[0]) or {}).get("removeDeck", []) for x in a["cards"])
        for x in fl: flagged_pieces[(x, tuple((flags.get(x) or flags.get(x.split(' // ')[0]))["removeDeck"]))] += 1
        c["commander_piece"] += any(x in r["commanders"] for x in a["cards"])
    c["exact_duplicate"] = exact_dup; c["superset_of_other_line"] = superset
    for k, v in c.items(): T[("cEDH" if cedh else "other", k)] += v
    perdeck.append((r["deck"], n, c["win"], exact_dup, superset))
for g in ("cEDH", "other"):
    print("==", g)
    for k in ["lines","win","resource_only","4plus_pieces","nonB_zone_piece","graveyard_exile_library_piece","hand_only_permanent_piece","template_requires","easy_prereq","notable_prereq","any_prereq_or_template","dfc_slash_name","loop_needs_activation","forge_ai_flagged_piece","forge_ai_flag_All","commander_piece","exact_duplicate","superset_of_other_line"]:
        print(f"   {k:32s} {T[(g,k)]}")
print("Forge-flagged pieces appearing in lines:", flagged_pieces.most_common(30))
print("decks with zero win lines:", [d for d, n, w, _, _ in perdeck if w == 0])
print("decks total with lines:", len(perdeck))
