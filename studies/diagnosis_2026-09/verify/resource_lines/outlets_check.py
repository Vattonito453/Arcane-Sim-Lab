import json, glob, collections, re, sys
sys.path.insert(0, "C:/Users/Vatto/Magic Rules Engine/engine")
from deck_plan import read_dck
from classify import cls
R = "C:/Users/Vatto/Magic Rules Engine/studies/behavior_rubric/runs_agent_shipping/plans"
D = "C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks"
# my own outlet list, by resource class
OUT = {
 "mill": ["Thassa's Oracle", "Laboratory Maniac", "Jace, Wielder of Mysteries"],
 "draw": ["Thassa's Oracle", "Laboratory Maniac", "Jace, Wielder of Mysteries"],
 "mana": ["Walking Ballista", "Thrasios, Triton Hero", "Kessig Wolf Run", "Helix Pinnacle", "Finale of Devastation",
          "Stroke of Genius", "Blue Sun's Zenith", "Torment of Hailfire", "Exsanguinate", "Villainous Wealth",
          "Hydroid Krasis", "Aetherflux Reservoir", "Banefire", "Crackle with Power", "Fireball", "Rocket Launcher",
          "Mirror Entity", "Staff of Domination", "Vilis, Broker of Blood"],
 "storm": ["Grapeshot", "Brain Freeze", "Tendrils of Agony", "Aetherflux Reservoir", "Empty the Warrens", "Mind's Desire", "Chain of Vapor"],
 "etb": ["Blood Artist", "Zulaport Cutthroat", "Cruel Celebrant", "Impact Tremors", "Purphoros, God of the Forge",
         "Warstorm Surge", "Terror of the Peaks", "Altar of the Brood", "Blind Obedience", "Disciple of the Vault",
         "Marionette Master", "Reckless Fireweaver", "Pestermite", "Nadu, Winged Wisdom", "Goblin Bombardment",
         "Viscera Seer", "Mayhem Devil", "Guttersnipe", "Witherbloom Apprentice", "Thassa's Oracle"],
}
ALL = sorted({c for v in OUT.values() for c in v})
def rclass(prod):
    s = " ".join(prod).lower()
    out = set()
    if "mill" in s or "exile your library" in s: out.add("mill")
    if "draw" in s or "looting" in s: out.add("draw")
    if "mana" in s or "treasure" in s: out.add("mana")
    if "storm" in s or "magecraft" in s: out.add("storm")
    if "etb" in s or "ltb" in s or "death" in s or "sacrifice" in s or "token" in s or "blink" in s or "landfall" in s: out.add("etb")
    return out
tot = any_ = matched = 0
oracle_decks = []
nolinedecks = collections.Counter()
for f in sorted(glob.glob(R + "/plans_*.json")):
    pod = f.split("plans_")[-1][:-5]
    d = json.load(open(f, encoding="utf-8"))
    for name, plan in d["decks"].items():
        dck = f"{D}/{pod}/dck/{name}.dck"
        try:
            _, cmd, main = read_dck(dck)
        except FileNotFoundError:
            print("missing", dck); continue
        deck = set(cmd) | set(main)
        inline = {c for ln in plan["lines"] for c in ln["cards"]}
        unused = {c for c in ALL if c in deck and c not in inline}
        if "Thassa's Oracle" in deck and "Thassa's Oracle" not in inline: oracle_decks.append((pod, name))
        for ln in plan["lines"]:
            if cls(ln.get("produces", []), "lenient") == "win": continue
            tot += 1
            if unused: any_ += 1
            rc = rclass(ln.get("produces", []))
            m = {c for k in rc for c in OUT[k] if c in unused}
            if m: matched += 1
print("resource lines", tot, "with any unused outlet", any_, "with type-matched unused outlet", matched)
print("decks with Thassa's Oracle in list but in no line:", len(oracle_decks), oracle_decks)
