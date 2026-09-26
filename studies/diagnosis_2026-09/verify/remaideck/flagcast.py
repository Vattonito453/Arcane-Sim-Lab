"""Independent re-count: cast rate of drawn nonland cards split by Forge's
AI:RemoveDeck flag, per seat agent. Casting detected from ZONE records
(Hand->Stack by cardId), not entry messages, to cross-check the other script.
Also splits flagged stock casts by primary API (Counter vs other) and by
whether the stack was empty at cast time (from the preceding zone stream)."""
import zipfile, re, json, glob, os, sys, collections, pickle

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cardinfo.pkl")
if os.path.exists(CACHE):
    info = pickle.load(open(CACHE, "rb"))
else:
    Z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
    info = {}
    for n in Z.namelist():
        if not n.endswith(".txt"):
            continue
        t = Z.read(n).decode("utf-8", "replace")
        names = [x.strip() for x in re.findall(r"^Name:(.+)$", t, re.M)]
        if not names:
            continue
        flags = set(re.findall(r"^AI:RemoveDeck:(\w+)", t, re.M))
        if "All" in flags:
            fl = "All"
        elif "Random" in flags:
            fl = "Random"
        else:
            fl = "none"
        m = re.search(r"^A:SP\$ ?(\w+)", t, re.M)
        api = m.group(1) if m else ""
        pbl = bool(re.search(r"^SVar:PlayBeforeLandDrop", t, re.M))
        d = {"fl": fl, "api": api, "pbl": pbl, "flags": sorted(flags)}
        for nm in names:
            info.setdefault(nm, d)
        # full DFC/split name too
        if len(names) > 1:
            info.setdefault(" // ".join(names), d)
    pickle.dump(info, open(CACHE, "wb"))

R = "C:/Users/Vatto/Magic Rules Engine/studies/"
for fold in sys.argv[1:]:
    files = sorted(glob.glob(R + fold + "/*.jsonl"))
    drawn = collections.Counter(); cast = collections.Counter()
    games = 0
    stock_flag_casts = collections.Counter()   # (name, api, stackEmpty)
    percard = collections.defaultdict(lambda: collections.Counter())
    for f in files:
        agent_of = {}
        hand = {}      # (g,cid) -> (player,name)
        casted = {}    # (g,cid) -> stackEmptyAtCast
        stackdepth = collections.Counter()
        for l in open(f, encoding="utf-8", errors="replace"):
            if '"rec":"zone"' not in l and '"rec":"meta"' not in l and '"rec":"result"' not in l:
                continue
            try:
                r = json.loads(l)
            except Exception:
                continue
            rec = r.get("rec")
            if rec == "meta":
                for p, a in zip(r.get("players", []), r.get("agents", [])):
                    agent_of[p] = "stock" if a == "stock" else "plan"
                continue
            if rec == "result":
                games += 1
                continue
            g = r.get("game"); cid = r.get("cardId"); nm = r.get("card")
            fr = r.get("from"); to = r.get("to")
            if fr == "Library" and to == "Hand" and "Land" not in (r.get("types") or ""):
                hand.setdefault((g, cid), (r.get("toPlayer"), nm))
            if fr == "Hand" and to == "Stack":
                casted.setdefault((g, cid), stackdepth[g] == 0)
            if to == "Stack":
                stackdepth[g] += 1
            if fr == "Stack":
                stackdepth[g] = max(0, stackdepth[g] - 1)
        for k, (p, nm) in hand.items():
            a = agent_of.get(p, "?")
            ci = info.get(nm)
            fl = ci["fl"] if ci else "unk"
            drawn[(a, fl)] += 1
            hit = k in casted
            if hit:
                cast[(a, fl)] += 1
            if fl == "All":
                percard[(a, nm)]["drawn"] += 1
                percard[(a, nm)]["cast"] += hit
                if hit and a == "stock":
                    stock_flag_casts[(nm, ci["api"], "emptyStack" if casted[k] else "response")] += 1
    print("=== %s: %d files, %d games" % (fold, len(files), games))
    for key in sorted(drawn):
        print("  agent=%-5s flag=%-6s drawn=%6d cast=%6d rate=%.3f" % (key[0], key[1], drawn[key], cast[key], cast[key] / max(1, drawn[key])))
    tot_nl = sum(v for (a, fl), v in drawn.items() if a == "stock")
    tot_all = drawn[("stock", "All")]
    if tot_nl:
        print("  stock flagged share of drawn nonland: %d/%d = %.3f" % (tot_all, tot_nl, tot_all / tot_nl))
    # stock flagged casts by api / stack state
    by_api = collections.Counter(); by_stack = collections.Counter()
    for (nm, api, st), v in stock_flag_casts.items():
        by_api["Counter" if api == "Counter" else "other"] += v
        by_stack[st] += v
    print("  stock flagged casts by API:", dict(by_api), "by stack:", dict(by_stack))
    print("  stock flagged casts detail:", sorted(stock_flag_casts.items(), key=lambda kv: -kv[1])[:25])
    top = sorted(((k, v) for k, v in percard.items() if k[0] == "stock"), key=lambda kv: -kv[1]["drawn"])[:20]
    print("  stock All cards drawn/cast:", [(k[1], v["drawn"], v["cast"]) for k, v in top])
