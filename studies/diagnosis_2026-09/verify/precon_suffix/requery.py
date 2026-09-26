import json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine")
sys.path.insert(0, str(ROOT/"engine"))
import combos
OUT = Path("raw")
cohort = json.loads((ROOT/"studies/precon_predict/cohort.json").read_text(encoding="utf-8"))
def q(main, cmd):
    body = json.dumps({"main":[{"card":n,"quantity":qq} for n,qq in main],
                       "commanders":[{"card":n,"quantity":1} for n in cmd]}).encode()
    req = urllib.request.Request(combos.API_URL, data=body, method="POST", headers={
        "Content-Type":"application/json","Accept":"application/json","User-Agent":combos.USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())
controls = {"Planeswalker Party","Counter Blitz","Family Matters"}
for i,c in enumerate(cohort):
    fn = OUT/(f"{i:02d}.json")
    if fn.exists(): continue
    main, cmd = combos.parse_dck(Path(c["file"]).read_text(encoding="utf-8"))
    cm = [(n.split("|")[0].strip(), qq) for n,qq in main]; cc=[n.split("|")[0].strip() for n in cmd]
    rec = {"name": c["name"], "file": c["file"]}
    try:
        res = q(cm, cc)["results"]
        rec["clean"] = {"identity": res.get("identity"),
            "included":[combos._slim(v) for v in res.get("included") or []],
            "almost_n": len(res.get("almostIncluded") or [])}
    except Exception as e:
        rec["clean_err"] = str(e)
    time.sleep(0.7)
    if c["name"] in controls:
        try:
            res = q(main, cmd)["results"]
            rec["suffixed"] = {"identity": res.get("identity"), "included_n": len(res.get("included") or []),
                               "almost_n": len(res.get("almostIncluded") or [])}
        except Exception as e:
            rec["suffixed_err"] = str(e)
        time.sleep(0.7)
    fn.write_text(json.dumps(rec), encoding="utf-8")
    print(i, c["name"], rec.get("clean",{}).get("identity"), len(rec.get("clean",{}).get("included",[])), rec.get("clean",{}).get("almost_n"), rec.get("suffixed"), rec.get("clean_err"), flush=True)
