import sys, os, re, glob, collections
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import games_of, CAST_RE, IDREF, REPO, DATASETS, is_counterspell, cinfo, TURN_RE
def manaish(nm):
    ci = cinfo(nm); txt = ci.get("oracle_text") or ""; tl = ci.get("type_line") or ""
    return ("Add {" in txt or "Add one mana" in txt or "Add X" in txt or "mana of any" in txt) and "Land" not in tl
out = collections.Counter(); names = collections.defaultdict(collections.Counter)
for ds in sys.argv[1:]:
    for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
        for meta, g, ents, lives in games_of(f):
            pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
            for e in ents:
                if e.get("type") != "STACK_ADD": continue
                m = CAST_RE.match((e.get("message") or "").strip())
                if not m or m.group(2) != "cast" or not m.group(4): continue
                card = IDREF.sub("", m.group(3)).strip()
                if not is_counterspell(card): continue
                tgt = re.sub(r" - Creature.*$", "", IDREF.sub("", m.group(4)).strip())
                pl = pilot.get(m.group(1))
                out[(ds, pl, "counters")] += 1
                if manaish(tgt):
                    out[(ds, pl, "on_mana")] += 1; names[(ds, pl)][(card, tgt)] += 1
                    if re.search(r"Force of Will|Force of Negation|Fierce Guardianship|Pact of Negation|Mindbreak|Deflecting Swat|Misdirection|Daze|Mental Misstep", card):
                        out[(ds, pl, "free_counter_on_mana")] += 1
for k in sorted({(a, b) for a, b, c in out}, key=str):
    n = out[(*k, "counters")]; m = out[(*k, "on_mana")]; fm = out[(*k, "free_counter_on_mana")]
    print(k, f"counters {n}  on mana sources {m} ({m / n:.2f})  free/pitch counters on mana {fm}")
