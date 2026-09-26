"""Assembly per combo: analysis.py as shipped (text inference) vs the same maths on
the shim zone stream (board.build). Read-only; monkeypatches in-process only."""
import json, sys, os, copy, collections
from pathlib import Path
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import analysis, board
def run(result, deck_dirs, use_zones):
    orig = board.reconstruct
    if use_zones:
        board.reconstruct = board.build
    try:
        return analysis.analyse(copy.deepcopy(result), deck_dirs=deck_dirs, fetch=False)
    finally:
        board.reconstruct = orig
tot = collections.Counter()
for p in sys.argv[1:]:
    r = json.load(open(p, encoding="utf-8"))
    r.setdefault("file", os.path.basename(p))
    dd = None
    if "_result.json" in p:
        pod = p.split("_result.json")[0].split("_")[-2] + "_" + p.split("_result.json")[0].split("_")[-1] if False else None
        for pod in ("n7WpsqsZtdQ","2iA_Jt0d6sM","5A6o18Bra0Y","B421mac67IE","Bq-nFi0f1jA","CxKMqO36DdM","OuY6mdiXbHU","sZA0KqXCGrY"):
            if pod in p: dd = [Path(r"C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks")/pod/"dck"]
    a = run(r, dd, False); b = run(r, dd, True)
    print("==", os.path.basename(p), "zones present:", sum(1 for g in r["games"] if g.get("zones")), "/", len(r["games"]))
    for name in a["decks"]:
        seen=set()
        for ca, cb in zip(a["decks"][name]["combos"], b["decks"][name]["combos"]):
            k = tuple(sorted(ca["cards"]))
            if k in seen: continue
            seen.add(k)
            tot["rows"] += 1
            tot["asm_text"] += ca["assembled_games"]; tot["asm_zones"] += cb["assembled_games"]
            tot["conv_text"] += ca["converted_games"]; tot["conv_zones"] += cb["converted_games"]
            if ca["reading"] != cb["reading"]: tot["reading_differs"] += 1
            if ca["assembled_games"] != cb["assembled_games"] or ca["reading"] != cb["reading"]:
                print(f"   {name}: {' + '.join(ca['cards'])}: text asm {ca['assembled_games']} conv {ca['converted_games']} [{ca['reading']}] vs zones asm {cb['assembled_games']} conv {cb['converted_games']} [{cb['reading']}]")
print(dict(tot))
