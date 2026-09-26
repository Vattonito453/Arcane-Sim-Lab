import os, sys, json, glob
from pathlib import Path
S = Path(__file__).resolve().parent
os.environ["MTG_DATA_DIR"] = str(S / "data"); os.environ["MTG_OFFLINE"] = "1"
R = r"C:/Users/Vatto/Magic Rules Engine"
sys.path.insert(0, R + "/engine")
import deck_plan, combos, cards
from collections import Counter

WIN = {"Win the game", "Win the game at the beginning of your next upkeep", "Infinite damage",
       "Near-infinite damage", "Infinite lifeloss", "Infinite mill", "Near-infinite mill",
       "Infinite combat phases", "Infinite creature tokens with haste",
       "Infinitely powerful creatures you control until end of turn",
       "Infinitely large creature until end of turn", "Infinite power for any creature", "Lock",
       "Opponents put all cards in hand on the bottom of their library on each of their draw steps"}
def classify(produces):
    if any(p in WIN for p in produces): return "win"
    return "resource"

idx = json.load(open(S / "raw_index.json"))
full_by_id = {}
full_by_deck = {}
for f in glob.glob(str(S / "raw/*.json")):
    d = json.load(open(f)); res = d.get("results") or {}
    full_by_deck[Path(f).stem] = res
    for v in (res.get("included") or []) + (res.get("almostIncluded") or []):
        full_by_id[v["id"]] = v

decks = [f"{R}/engine/decks/{n}.dck" for n in ("atraxa_counters","drana_vampires","nekusar_punisher","kambal_taxes")]
decks += sorted(glob.glob(f"{R}/studies/human_ceiling/decks/*/dck/*.dck"))
cohort = json.load(open(f"{R}/studies/precon_predict/cohort.json"))
decks += [d["file"] for d in cohort]

rows = []
for p in decks:
    name, plan = deck_plan.build_plan(p, fetch=False)
    main, cmd = combos.parse_dck(Path(p).read_text(encoding="utf-8"))
    cm = [(n.split("|")[0].strip(), q) for n, q in main]; cc = [n.split("|")[0].strip() for n in cmd]
    key_clean = combos._key(cm, cc)
    fresh = full_by_deck.get(key_clean, {})
    cached = combos.combos_for_dck(p, fetch=False)
    lines = plan["lines"]
    tag = (Path(p).parent.parent.name + "/" + Path(p).stem) if "human_ceiling" in p else Path(p).stem
    deckset = {n.split("|")[0].strip() for n, _ in main} | set(cc)
    audit = []
    for ln in lines:
        # match back to a full variant by card set
        v = None
        for fv in (fresh.get("included") or []):
            if set(u["card"]["name"] for u in fv["uses"]) == set(ln["cards"]):
                v = fv; break
        zones = {u["card"]["name"]: "".join(u.get("zoneLocations") or []) for u in (v or {}).get("uses", [])}
        mbc = [u["card"]["name"] for u in (v or {}).get("uses", []) if u.get("mustBeCommander")]
        audit.append({
            "cards": ln["cards"], "n": len(ln["cards"]), "cls": classify(ln["produces"]),
            "produces": ln["produces"],
            "matched_fresh": v is not None,
            "zones": zones,
            "nonB": {c: z for c, z in zones.items() if z != "B"},
            "requires": [(r.get("template") or {}).get("name") for r in (v or {}).get("requires", [])],
            "easy": (v or {}).get("easyPrerequisites", ""), "notable": (v or {}).get("notablePrerequisites", ""),
            "mana": (v or {}).get("manaNeeded", ""), "mustBeCommander": mbc,
            "missing_from_deck": [c for c in ln["cards"] if c not in deckset and c.split(" // ")[0] not in deckset],
            "id": (v or {}).get("id"),
        })
    rows.append({"deck": tag, "name": name, "commanders": cc,
                 "cached_status": "none" if cached is None else ("empty" if not cached["included"] and not cached["almost_included"] else "ok"),
                 "cached_included": len((cached or {}).get("included", [])),
                 "fresh_included": len(fresh.get("included") or []),
                 "fresh_almost": len(fresh.get("almostIncluded") or []),
                 "n_lines": len(lines), "tags": plan["tags"], "tutors": plan["tutors"],
                 "combo_pieces_weight8": sorted(n for n, r in plan["roles"].items() if r == "combo-piece"),
                 "targets8": sorted(n for n, v in plan["search"]["targets"].items() if v >= 8),
                 "lines": audit})
json.dump(rows, open(S / "plan_audit.json", "w"), indent=1)
print("deck | cached | fresh inc/almost | lines | win/resource | nonB-zone lines | req/easy/notable | maxpieces")
for r in rows:
    c = Counter(a["cls"] for a in r["lines"])
    nonb = sum(1 for a in r["lines"] if a["nonB"])
    pre = sum(1 for a in r["lines"] if a["requires"] or a["easy"] or a["notable"])
    mx = max([a["n"] for a in r["lines"]] or [0])
    print(f"{r['deck'][:40]:40s} {r['cached_status']:5s} {r['cached_included']:3d} | {r['fresh_included']:3d}/{r['fresh_almost']:3d} | {r['n_lines']:3d} | {c['win']}/{c['resource']} | {nonb} | {pre} | {mx}")
