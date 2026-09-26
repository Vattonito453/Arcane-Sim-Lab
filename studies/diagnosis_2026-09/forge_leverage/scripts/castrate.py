"""Cast rate of drawn nonland cards and activation rate of permanents, split by
Forge's own AI:RemoveDeck flag, per seat agent type. Read-only over study JSONL."""
import zipfile, re, json, glob, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
Z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
info = {}
for n in Z.namelist():
    if not n.endswith(".txt"): continue
    t = Z.read(n).decode("utf-8", "replace")
    names = re.findall(r"^Name:(.+)$", t, re.M)
    if not names: continue
    rem = "All" if re.search(r"^AI:RemoveDeck:All", t, re.M) else ("Random" if re.search(r"^AI:RemoveDeck:Random", t, re.M) else "none")
    abil = [l for l in t.splitlines() if l.startswith("A:AB$")]
    nonmana = [l for l in abil if not re.match(r"A:AB\$ ?Mana\b", l)]
    d = {"rem": rem, "ab": len(nonmana) > 0}
    for nm in names:
        info.setdefault(nm.strip(), d)
R = "C:/Users/Vatto/Magic Rules Engine/studies/"
folders = sys.argv[1:]
out = {}
for fold in folders:
    files = sorted(glob.glob(R + fold + "/*.jsonl"))
    drawn = collections.Counter(); cast = collections.Counter()
    bf = collections.Counter(); act = collections.Counter()
    percard = collections.defaultdict(lambda: [0, 0])  # drawn, cast for RemAll cards
    abcard = collections.defaultdict(lambda: [0, 0])
    games = 0
    for f in files:
        agent_of = {}
        hand = {}   # (game, id) -> (player, name)
        casted = set(); onbf = {}; activated = set()
        for l in open(f, encoding="utf-8", errors="replace"):
            try: r = json.loads(l)
            except Exception: continue
            rec = r.get("rec")
            if rec == "meta":
                for p, a in zip(r.get("players", []), r.get("agents", [])):
                    agent_of[p] = "plan" if a not in ("stock",) else "stock"
            elif rec == "result":
                games += 1
            elif rec == "zone":
                g = r.get("game"); cid = r.get("cardId"); nm = r.get("card")
                if r.get("to") == "Hand" and r.get("from") == "Library" and "Land" not in (r.get("types") or ""):
                    hand.setdefault((g, cid), (r.get("toPlayer"), nm))
                if r.get("to") == "Battlefield" and not r.get("token"):
                    onbf.setdefault((g, cid), (r.get("toPlayer"), nm))
            elif rec == "entry" and r.get("type") == "STACK_ADD":
                m = r.get("message", ""); g = r.get("game"); cid = r.get("cardId")
                if cid is None: continue
                if " cast " in m: casted.add((g, cid))
                elif " activated " in m: activated.add((g, cid))
        for k, (p, nm) in hand.items():
            a = agent_of.get(p, "?"); fl = info.get(nm, {}).get("rem", "unk")
            drawn[(a, fl)] += 1
            if k in casted: cast[(a, fl)] += 1
            if fl == "All":
                percard[nm][0] += 1; percard[nm][1] += (k in casted)
        for k, (p, nm) in onbf.items():
            ci = info.get(nm, {})
            if not ci.get("ab"): continue
            a = agent_of.get(p, "?"); fl = ci.get("rem", "unk")
            bf[(a, fl)] += 1
            if k in activated: act[(a, fl)] += 1
            abcard[(fl, nm)][0] += 1; abcard[(fl, nm)][1] += (k in activated)
    print("=== %s: %d files, %d games" % (fold, len(files), games))
    for key in sorted(drawn):
        print("  drawn nonland  agent=%-5s flag=%-6s drawn=%6d cast=%6d rate=%.3f" % (key[0], key[1], drawn[key], cast[key], cast[key] / max(1, drawn[key])))
    for key in sorted(bf):
        print("  perm w/ non-mana AB agent=%-5s flag=%-6s onBF=%6d activated=%6d rate=%.3f" % (key[0], key[1], bf[key], act[key], act[key] / max(1, bf[key])))
    top = sorted(percard.items(), key=lambda kv: -kv[1][0])[:25]
    print("  RemoveDeck:All cards drawn->cast:", [(k, v[0], v[1]) for k, v in top])
    topab = sorted(((k, v) for k, v in abcard.items() if k[0] == "All"), key=lambda kv: -kv[1][0])[:20]
    print("  RemoveDeck:All permanents onBF->activated:", [(k[1], v[0], v[1]) for k, v in topab])
