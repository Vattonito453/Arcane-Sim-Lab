"""Classify every Commander Spellbook line in the 32 human_ceiling cEDH decks by
what executing it requires, against the Forge card scripts and the shim's
combo code. Read-only. Writes line_classes.json + prints a summary."""
import glob, json, os, re, sys, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos  # noqa
from forge_cards import load, facts

HERE = os.path.dirname(os.path.abspath(__file__))
idx = load()

WIN_WORDS = re.compile(r"win the game|infinite damage|damage to each opponent|"
                       r"infinite lifeloss|lose the game|infinite life loss|"
                       r"infinite combat|infinite (colorless |colored )?damage|"
                       r"infinite mill(?! of)|each opponent loses", re.I)


def classify(v):
    cards = v["cards"]
    desc = v.get("description", "")
    pre = v.get("prerequisites", "")
    prod = v.get("produces", [])
    f = {c: facts(idx, c) for c in cards}
    missing = [c for c, x in f.items() if x is None]
    nonperm = [c for c, x in f.items() if x and not x["permanent"]]
    rem_all = [c for c, x in f.items() if x and x["remAll"]]
    steps = [s.strip() for s in desc.split("\n") if s.strip()]
    activates = sum(1 for s in steps if s.lower().startswith("activate"))
    casts = sum(1 for s in steps if s.lower().startswith("cast"))
    repeat = any(s.lower().startswith("repeat") for s in steps)
    equip_step = bool(re.search(r"\bequip|attached to", desc + " " + pre, re.I))
    win = any(WIN_WORDS.search(p) for p in prod)
    if nonperm and activates == 0:
        klass = "spell-completion (instant/sorcery piece, never 'all on battlefield')"
    elif nonperm:
        klass = "spell + activation loop"
    elif activates > 0:
        klass = "activated-ability loop"
    elif equip_step:
        klass = "attach/equip prerequisite then trigger loop"
    else:
        klass = "trigger-only (static/ETB) loop"
    return {
        "cards": cards, "produces": prod[:6], "win_on_its_own": win,
        "class": klass, "nonpermanent_pieces": nonperm,
        "removedeck_all_pieces": rem_all, "activate_steps": activates,
        "cast_steps": casts, "repeat": repeat, "prereq": pre[:200],
        "missing_script": missing,
    }


def main():
    rows = []
    for dck in sorted(glob.glob(r"C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks/*/dck/*.dck")):
        pod = dck.replace("\\", "/").split("/")[-3]
        deck = os.path.basename(dck)[:-4]
        r = combos.combos_for_dck(dck, fetch=False)
        if r is None:
            rows.append({"pod": pod, "deck": deck, "uncached": True})
            continue
        seen = set()
        for v in r["included"]:
            key = tuple(sorted(v["cards"]))
            dup = key in seen
            seen.add(key)
            row = classify(v)
            row.update(pod=pod, deck=deck, duplicate=dup)
            rows.append(row)
    json.dump(rows, open(os.path.join(HERE, "line_classes.json"), "w"), indent=1)
    lines = [r for r in rows if not r.get("uncached")]
    print("decks:", len({(r['pod'], r['deck']) for r in rows}),
          "uncached:", sum(1 for r in rows if r.get("uncached")))
    print("lines:", len(lines), "duplicates (same piece set):", sum(r["duplicate"] for r in lines))
    u = [r for r in lines if not r["duplicate"]]
    print("unique lines:", len(u))
    c = collections.Counter(r["class"] for r in u)
    for k, n in c.most_common():
        print(f"  {n:4d}  {k}")
    print("win on its own (produces names a win/damage/mill outcome):",
          sum(r["win_on_its_own"] for r in u), "/", len(u))
    print("lines with >=1 AI:RemoveDeck:All piece:",
          sum(1 for r in u if r["removedeck_all_pieces"]), "/", len(u))
    print("lines with >=1 instant/sorcery piece:",
          sum(1 for r in u if r["nonpermanent_pieces"]), "/", len(u))
    print("lines needing >=1 activation step:",
          sum(1 for r in u if r["activate_steps"] > 0), "/", len(u))
    print("lines with a prerequisite the plan cannot express:",
          sum(1 for r in u if r["prereq"]), "/", len(u))
    shim_drivable = [r for r in u if r["activate_steps"] == 0 and not r["nonpermanent_pieces"]
                     and not r["prereq"]]
    print("lines whose every step is cast-a-permanent + triggers, no prereq:",
          len(shim_drivable), "/", len(u))
    print("  ...of which win on their own:", sum(r["win_on_its_own"] for r in shim_drivable))
    for r in shim_drivable:
        print("     ", r["pod"], r["deck"], " + ".join(r["cards"]), "->", r["produces"][:3])
    rem = collections.Counter(p for r in u for p in r["removedeck_all_pieces"])
    print("RemoveDeck:All pieces by line count:", rem.most_common(20))


if __name__ == "__main__":
    main()
