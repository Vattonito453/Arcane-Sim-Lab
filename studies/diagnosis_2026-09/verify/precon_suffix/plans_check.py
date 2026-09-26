import json
from pathlib import Path
ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine/studies/precon_predict")
for f in ["plans_agent.json","plans_agent_015.json","plans_synergy.json"]:
    d = json.loads((ROOT/f).read_text(encoding="utf-8"))
    decks = d.get("decks", d)
    withl = [(n, len(p.get("lines") or [])) for n,p in decks.items() if p.get("lines")]
    print(f, "decks", len(decks), "with lines", len(withl), withl[:5])
    # tutors / searchTargets presence
    tut = sum(1 for p in decks.values() if p.get("tutors"))
    print("   decks with tutors", tut)
