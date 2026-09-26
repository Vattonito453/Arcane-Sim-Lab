"""Independent re-count of combo assembly / conversion from raw shim JSONL.

Written from scratch (not derived from combo_execution/funnel.py).
- Battlefield per controller from zone records keyed by cardId.
- Permanence from the zone records' own `types` field (no external index).
- Assembled: every permanent piece of a line on the seat's battlefield at once,
  and every non-permanent piece cast by that seat in the same turn.
- Converted: seat is the winner and at most K own turns began after the
  assembly turn.
- Win method from GAME_OUTCOME entries + result record.
"""
import collections, glob, json, os, re, sys

STUDIES = r"C:/Users/Vatto/Magic Rules Engine/studies"
PERM = {"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"}
TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)$")

TYPES = {}


def scan_types(files):
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                if '"rec":"zone"' not in line:
                    continue
                r = json.loads(line)
                t = r.get("types")
                if t and not r.get("token"):
                    TYPES.setdefault(r["card"], set()).update(t.replace(",", " ").split())


def is_perm(name):
    t = TYPES.get(name)
    if t is None:
        return None
    return bool(t & PERM)


def load_lines(plan_path):
    d = json.load(open(plan_path, encoding="utf-8"))["decks"]
    out = {}
    for deck, p in d.items():
        seen, ls = set(), []
        for ln in p.get("lines", []):
            k = tuple(sorted(ln["cards"]))
            if k not in seen:
                seen.add(k)
                ls.append(list(ln["cards"]))
        out[deck] = ls
    return out


def deck(p):
    return p.split("-", 1)[1]


def games_of(fp):
    meta, games = None, collections.OrderedDict()
    with open(fp, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("rec") == "meta":
                meta = r
                continue
            g = r.get("game")
            if g is None:
                continue
            games.setdefault(g, []).append(r)
    return meta, games


def analyze(fp, lines_by_deck, K=2):
    meta, games = games_of(fp)
    players, agents = meta["players"], dict(zip(meta["players"], meta["agents"]))
    rows = []
    for g, recs in games.items():
        own_turns = collections.defaultdict(list)
        outcomes = []
        for r in recs:
            if r.get("rec") == "entry":
                if r.get("type") == "TURN":
                    m = TURN_RE.match(r["message"])
                    if m:
                        own_turns[m.group(2)].append(int(m.group(1)))
                elif r.get("type") == "GAME_OUTCOME":
                    outcomes.append(r["message"])
        res = next((r for r in recs if r.get("rec") == "result"), None)
        if res is None:
            continue
        bf = {}  # cardId -> (controller, name)
        cast_turn = collections.defaultdict(dict)  # player -> name -> last cast turn
        assembled = {}  # (player, line_idx) -> turn
        cur = 0
        attach_helm_godo_turns = set()
        combats_per_turn = collections.Counter()

        def check(p, t):
            for i, ln in enumerate(lines_by_deck.get(deck(p), [])):
                if (p, i) in assembled:
                    continue
                names_on = collections.Counter(n for (c, n) in bf.values() if c == p)
                ok = True
                for card in ln:
                    pm = is_perm(card)
                    if pm is None:
                        # never observed in any zone record: treat as permanent unless cast seen
                        pm = True
                    if pm:
                        if names_on[card] < 1:
                            ok = False
                            break
                    else:
                        if cast_turn[p].get(card) != t:
                            ok = False
                            break
                if ok:
                    assembled[(p, i)] = t

        for r in recs:
            rt = r.get("rec")
            if rt == "zone":
                t = r.get("turn") or cur
                cur = t
                cid, fr, to = r.get("cardId"), r.get("from"), r.get("to")
                touched = set()
                if fr == "Battlefield" and cid in bf:
                    touched.add(bf.pop(cid)[0])
                if to == "Battlefield":
                    p = r.get("toPlayer") or r.get("fromPlayer")
                    bf[cid] = (p, r["card"])
                    touched.add(p)
                if to == "Stack" and fr in ("Hand", "Command", "Graveyard", "Exile", "Library"):
                    p = r.get("fromPlayer")
                    cast_turn[p][r["card"]] = t
                    touched.add(p)
                for p in touched:
                    if p in players:
                        check(p, t)
            elif rt == "attach":
                if r.get("card") == "Helm of the Host" and str(r.get("to", "")).startswith("Godo"):
                    attach_helm_godo_turns.add(r.get("turn"))
        winner = res.get("winner")
        final = res.get("turns")
        spell = None
        for m in outcomes:
            mm = re.search(r"won due to effect of '([^']+)'", m)
            if mm:
                spell = mm.group(1)
        for p in players:
            ls = lines_by_deck.get(deck(p), [])
            if not ls:
                continue
            asm = [(t, i) for (pp, i), t in assembled.items() if pp == p]
            first = min(asm) if asm else None
            conv = False
            conv_lines = []
            if winner == p:
                for (t, i) in asm:
                    n_after = len([x for x in own_turns[p] if t < x <= final])
                    if n_after <= K:
                        conv = True
                        conv_lines.append(" + ".join(ls[i]))
            rows.append({
                "file": os.path.relpath(fp, STUDIES).replace("\\", "/"), "game": g, "seat": p,
                "agent": agents[p], "won": winner == p, "winner": winner, "final": final,
                "spell_win": spell if winner == p else None,
                "assembled": first[0] if first else None,
                "asm_lines": sorted({" + ".join(ls[i]) for (t, i) in asm}),
                "first_line": " + ".join(ls[first[1]]) if first else None,
                "converted": conv, "conv_lines": conv_lines,
                "helm_on_godo_turns": sorted(x for x in attach_helm_godo_turns if x is not None),
            })
    return rows


def main():
    sets = {
        "av_015_default": ["agent_viability/runs_015_default/cell_*.jsonl"],
        "av_winmax": ["agent_viability/runs_winmax/cell_*.jsonl"],
        "av_016_engine": ["agent_viability/runs_016_engine/cell_*.jsonl"],
    }
    allfiles = []
    for pats in sets.values():
        for pat in pats:
            allfiles += glob.glob(os.path.join(STUDIES, pat))
    scan_types(allfiles)
    rows = []
    for arm, pats in sets.items():
        for pat in pats:
            for fp in sorted(glob.glob(os.path.join(STUDIES, pat))):
                pod = re.search(r"cell_(.+)_rot\d", fp).group(1)
                lp = os.path.join(os.path.dirname(fp), f"plans_{pod}.json")
                for row in analyze(fp, load_lines(lp)):
                    row["arm"] = arm
                    rows.append(row)
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), "vrows.json"), "w"), indent=0)
    for grp in ("plan", "stock"):
        R = [r for r in rows if r["agent"] == grp]
        a = [r for r in R if r["assembled"] is not None]
        c = [r for r in a if r["converted"]]
        print(f"{grp}: n={len(R)} assembled={len(a)} ({len(a)/len(R):.1%}) converted={len(c)} ({len(c)/max(1,len(a)):.1%} of asm) wins={sum(r['won'] for r in R)}")
        for arm in sets:
            RA = [r for r in R if r["arm"] == arm]
            aa = [r for r in RA if r["assembled"] is not None]
            cc = [r for r in aa if r["converted"]]
            print(f"   {arm}: n={len(RA)} asm={len(aa)} conv={len(cc)} wins={sum(r['won'] for r in RA)}")
        sw = collections.Counter(r["spell_win"] for r in R if r["won"])
        print("   win spell:", dict(sw))
        cm = collections.Counter()
        for r in c:
            if r["spell_win"]:
                cm["spell:" + r["spell_win"]] += 1
            elif any("Godo" in x and "Helm" in x for x in r["conv_lines"]):
                cm["godo+helm"] += 1
            else:
                cm["other(nonspell)"] += 1
        print("   converted by method:", dict(cm))
        ts = sorted(r["assembled"] for r in a)
        if ts:
            print("   median assembly turn:", ts[len(ts)//2])


if __name__ == "__main__":
    main()
