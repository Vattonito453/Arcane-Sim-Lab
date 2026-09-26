import json, glob, re
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
for f in sorted(glob.glob(ROOT+"behavior_rubric/plans_*.json")):
    d = json.load(open(f, encoding="utf-8"))["decks"]
    for name, p in d.items():
        L = p.get("lines", [])
        print(f"## {f.split('plans_')[1][:11]} {name} lines={len(L)} win={sum(1 for l in L if WIN.search(' ; '.join(l['produces'])))}")
        for l in L:
            s = ' ; '.join(l['produces'])
            print("   ", "W" if WIN.search(s) else "-", " + ".join(l['cards']), " => ", s[:140])
