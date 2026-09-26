"""Forge's own 'my AI cannot play this card' flags (AI:RemoveDeck:All/Random)
against the decks under test, and what happens to those cards in games.

1. Deck composition: share of nonland cards flagged, per deck set.
2. In games (zone stream): every nonland card that reached a hand, and what
   became of it: cast (Hand->Stack), put/played (Hand->Battlefield),
   discarded (Hand->Graveyard), still in hand at game end / elimination,
   other. Split by flag and pilot.
"""
import sys, re, json, glob, collections, os
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import games_of, REPO, DATASETS

HERE = Path(__file__).parent
FLAGS = json.load(open(HERE / "forge_ai_flags.json"))


def flag(nm):
    f = FLAGS.get(nm)
    if f is None and " // " in nm:
        f = FLAGS.get(nm.split(" // ")[0])
    if f is None:
        return "unknown"
    if "RemoveDeck:All" in f:
        return "All"
    if "RemoveDeck:Random" in f:
        return "Random"
    return "ok"


def read_dck(path):
    out = []
    sec = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("["):
            sec = line.lower()
            continue
        m = re.match(r"^(\d+)\s+(.+?)(?:\|.*)?$", line)
        if m and sec in ("[main]", "[commander]"):
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def deck_report():
    sets = {
        "cEDH pods (human_ceiling)": glob.glob(str(REPO / "studies/human_ceiling/decks/*/dck/*.dck")),
    }
    metas = set()
    for f in glob.glob(str(REPO / "studies/precon_predict/runs_agent_015/*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            m = json.loads(fh.readline())
            metas |= set(m.get("decks", []))
    sets["66 precon cohort"] = sorted(metas)
    for label, files in sets.items():
        tot = collections.Counter()
        per_deck = []
        top = collections.Counter()
        for f in files:
            c = collections.Counter()
            for n, nm in read_dck(f):
                tl = FLAGS.get(nm)
                # lands: skip by name heuristics via card cache
                import cards
                ci = cards.get(nm, fetch=False) or {}
                if "Land" in (ci.get("type_line") or ""):
                    continue
                fl = flag(nm)
                c[fl] += n
                if fl == "All":
                    top[nm] += 1
            tot.update(c)
            s = sum(c.values())
            if s:
                per_deck.append((c["All"] / s, c["Random"] / s, os.path.basename(f)))
        s = sum(tot.values())
        per_deck.sort(reverse=True)
        print(f"== {label}: {len(files)} decks, nonland cards {s}: RemoveDeck:All {tot['All']} ({tot['All'] / s:.1%}), "
              f"Random {tot['Random']} ({tot['Random'] / s:.1%}), unknown {tot['unknown']}")
        print("   worst decks (All share):", [(round(a, 3), round(r, 3), n) for a, r, n in per_deck[:6]])
        print("   median All share:", round(sorted(x[0] for x in per_deck)[len(per_deck) // 2], 3))
        print("   most common All-flagged cards:", top.most_common(25))


def fate_report(dsets):
    for ds in dsets:
        out = collections.Counter()
        names = collections.defaultdict(collections.Counter)
        for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
            for meta, g, ents, lives in games_of(f):
                pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
                fate = {}
                for r in lives:
                    if r.get("rec") != "zone":
                        continue
                    ty = r.get("types") or ""
                    if "Land" in ty or r.get("token"):
                        continue
                    cid = r.get("cardId")
                    fr, to = r.get("from"), r.get("to")
                    if to == "Hand" and r.get("toPlayer"):
                        if cid not in fate:
                            fate[cid] = [r.get("toPlayer"), r.get("card"), "held"]
                        elif fate[cid][2] in ("held",):
                            pass
                    elif fr == "Hand" and cid in fate and fate[cid][2] == "held":
                        if to == "Stack":
                            fate[cid][2] = "cast"
                        elif to == "Battlefield":
                            fate[cid][2] = "put"
                        elif to == "Graveyard":
                            fate[cid][2] = "discard_or_cycle" if (r.get("phase") or "") != "CLEANUP" else "cleanup_discard"
                        elif to == "Library":
                            # mulligan bottom at turn 0: forget it
                            if (r.get("turn") or 0) == 0:
                                del fate[cid]
                            else:
                                fate[cid][2] = "to_library"
                        elif to == "Exile":
                            fate[cid][2] = "exiled"
                for cid, (p, nm, st) in fate.items():
                    fl = flag(nm)
                    pl = pilot.get(p)
                    out[(pl, fl, st)] += 1
                    out[(pl, fl, "ALL")] += 1
                    if fl == "All":
                        names[st][nm] += 1
        print("== fate of nonland cards that reached a hand:", ds)
        for pl in sorted({k[0] for k in out}, key=str):
            for fl in ("ok", "Random", "All", "unknown"):
                n = out[(pl, fl, "ALL")]
                if not n:
                    continue
                row = {st: round(out[(pl, fl, st)] / n, 3) for st in ("cast", "put", "held", "cleanup_discard", "discard_or_cycle", "exiled", "to_library")}
                print(f"   {pl:6s} {fl:8s} n={n:6d} {row}")
        print("   All-flagged never cast (held to end):", names["held"].most_common(15))
        print("   All-flagged discarded at cleanup:", names["cleanup_discard"].most_common(10))
        print("   All-flagged cast:", names["cast"].most_common(10))


if __name__ == "__main__":
    deck_report()
    fate_report(sys.argv[1:])
