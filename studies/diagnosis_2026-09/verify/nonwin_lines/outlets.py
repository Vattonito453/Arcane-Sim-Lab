import json, glob
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
OUT = ["Thassa's Oracle","Laboratory Maniac","Jace, Wielder of Mysteries","Walking Ballista","Thrasios, Triton Hero","Grinding Station","Blood Artist","Zulaport Cutthroat","Aetherflux Reservoir","Grapeshot","Brain Freeze","Kiki-Jiki, Mirror Breaker","Finale of Devastation","Duskwatch Recruiter","Hullbreaker Horror","Kinnan, Bonder Prodigy","Staff of Domination","Portal to Phyrexia","Sanguine Bond","Exquisite Blood","Kogla, the Titan Ape","Temur Sabertooth","Pestermite","Displacer Kitten","Tymna the Weaver","Dwarven Bloodboiler","Professional Face-Breaker","Bottle-Cap Blast","Magda, Brazen Outlaw","Yisan, the Wanderer Bard","Selvala, Heart of the Wilds","Umbral Mantle","Ashaya, Soul of the Wild","Emiel the Blessed","Derevi, Empyrial Tactician","Nadu, Winged Wisdom","Cephalid Illusionist","Tainted Pact","Demonic Consultation","Underworld Breach","Isochron Scepter","Dramatic Reversal","Stroke of Genius","Blue Sun's Zenith","Torment of Hailfire","Villainous Wealth","Maddening Cacophony"]
for f in sorted(glob.glob(ROOT+"behavior_rubric/plans_*.json")):
    d = json.load(open(f, encoding="utf-8"))["decks"]
    for name, p in d.items():
        cards = set(p.get("roles", {}).keys())
        print(f[-16:-5], name, len(cards), "|", ", ".join(c for c in OUT if c in cards))
