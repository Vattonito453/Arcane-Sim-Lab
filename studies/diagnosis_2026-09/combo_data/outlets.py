import json, re, collections
from pathlib import Path
rows = json.load(open("plan_audit.json"))
R = r"C:/Users/Vatto/Magic Rules Engine"
OUTLETS = {  # resource feature regex -> cards that turn it into a win (illustrative, well-known)
  r"self-mill|card draw\b|Exile your library": ["Thassa's Oracle", "Laboratory Maniac", "Jace, Wielder of Mysteries"],
  r"colorless mana|colored mana|green mana|red mana|mana creatures|mana lands|mana permanents|mana artifacts": ["Walking Ballista", "Thrasios, Triton Hero", "Kinnan, Bonder Prodigy", "Finale of Devastation", "Stonecoil Serpent", "Hullbreaker Horror", "Staff of Domination", "Aetherflux Reservoir", "Blue Sun's Zenith", "Sanguine Bond"],
  r"storm count|magecraft": ["Grapeshot", "Brain Freeze", "Tendrils of Agony", "Aetherflux Reservoir", "Birgi, God of Storytelling // Harnfel, Horn of Bounty"],
  r"death triggers|sacrifice triggers|LTB": ["Blood Artist", "Zulaport Cutthroat", "Cruel Celebrant", "Bastion of Remembrance", "Pitiless Plunderer", "Mayhem Devil"],
  r"ETB|blinking": ["Impact Tremors", "Purphoros, God of the Forge", "Nadu, Winged Wisdom", "Blind Obedience", "Suture Priest", "Soul Warden", "Terror of the Peaks"],
  r"artifact tokens|Treasure|Food|Clue|artifact ETB": ["Walking Ballista", "Grinding Station", "Reckless Fireweaver", "Marionette Master", "Karn, the Great Creator", "Portal to Phyrexia"],
  r"landfall": ["Scute Swarm", "Rampaging Baloths", "Avenger of Zendikar", "Retreat to Coralhelm"],
}
tot = collections.Counter(); ex = []
for r in rows:
    if "/" not in r["deck"]: continue
    pod, stem = r["deck"].split("/")
    txt = Path(f"{R}/studies/human_ceiling/decks/{pod}/dck/{stem}.dck").read_text(encoding="utf-8")
    deck = {m.group(1).strip() for m in re.finditer(r"^\d+\s+(.+?)\s*$", txt, re.M)}
    for a in r["lines"]:
        if a["cls"] != "resource": continue
        tot["resource lines"] += 1
        feats = " | ".join(a["produces"])
        found = set()
        for pat, outs in OUTLETS.items():
            if re.search(pat, feats, re.I):
                found |= {o for o in outs if o in deck and o not in a["cards"]}
        if found:
            tot["an outlet card is in the deck but not in the line"] += 1
            if len(ex) < 12: ex.append((r["deck"], " + ".join(a["cards"]), sorted(found)[:4]))
        else:
            tot["no outlet from the illustrative list"] += 1
print(dict(tot))
for e in ex: print("  ", e)
