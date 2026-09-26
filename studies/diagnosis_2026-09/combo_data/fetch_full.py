"""Re-query Commander Spellbook find-my-combos with FULL records (zoneLocations,
requires, easyPrerequisites, mustBeCommander) for every deck under study, with
Forge's |SET|art suffix stripped. Writes only to this scratch folder."""
import json, sys, time, glob, hashlib, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
OUT = Path("raw"); OUT.mkdir(exist_ok=True)
R = r"C:/Users/Vatto/Magic Rules Engine"
decks = [f"{R}/engine/decks/{n}.dck" for n in ("atraxa_counters","drana_vampires","nekusar_punisher","kambal_taxes")]
decks += sorted(glob.glob(f"{R}/studies/human_ceiling/decks/*/dck/*.dck"))
decks += [d["file"] for d in json.load(open(f"{R}/studies/precon_predict/cohort.json"))]
seen = {}
for p in decks:
    main, cmd = combos.parse_dck(Path(p).read_text(encoding="utf-8"))
    main = [(n.split("|")[0].strip(), q) for n, q in main]
    cmd = [n.split("|")[0].strip() for n in cmd]
    key = combos._key(main, cmd)
    tag = Path(p).parent.parent.name + "__" + Path(p).stem if "human_ceiling" in p else Path(p).stem
    out = OUT / (key + ".json")
    seen.setdefault(key, []).append(tag)
    if out.exists():
        continue
    body = json.dumps({"main": [{"card": n, "quantity": q} for n, q in main],
                       "commanders": [{"card": n, "quantity": 1} for n in cmd]}).encode()
    req = urllib.request.Request(combos.API_URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": combos.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.loads(r.read().decode())
        out.write_text(json.dumps(data), encoding="utf-8")
        res = data.get("results") or {}
        print(tag, res.get("identity"), len(res.get("included") or []), len(res.get("almostIncluded") or []), flush=True)
    except Exception as e:
        print("ERR", tag, e, flush=True)
    time.sleep(1.2)
json.dump({"index": seen, "files": {Path(p).stem: p for p in decks}}, open("raw_index.json", "w"), indent=1)
