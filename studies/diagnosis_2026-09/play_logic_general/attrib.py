"""Attribute attackers that die for nothing to the shim's re-aim passes.

For each plan-seat attack declaration (a turn), note whether the shim moved
attackers that turn (kingmaker_reaim / split / open_reaim / see_attack with
added>0). Then compare the died-for-nothing rate per attacker in turns with
and without a move, and for the moved defender specifically.
"""
import sys, re, json, glob, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import games_of, parse_entry_phase, IDREF, TURN_RE, REPO, DATASETS, LIVE_PH, pt_split, ATK_RE, BLK_RE

MOVE_EVENTS = ("kingmaker_reaim", "split", "open_reaim")
out = collections.Counter()
for ds in sys.argv[1:]:
    for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
        for meta, g, ents, lives in games_of(f):
            ver = tuple(int(x) for x in (meta.get("shim") or "0.0").split(".")[:2])
            if ver < (0, 13):
                continue
            pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
            moves = collections.defaultdict(list)    # (turn, player) -> [(event, onto)]
            for r in lives:
                if r.get("rec") == "agent" and r.get("event") in MOVE_EVENTS:
                    m = re.search(r"onto=(Ai\(\d\)-.+?)(?: leaderThreat=|$)", r.get("detail") or "")
                    moves[(r.get("turn"), r.get("player"))].append((r["event"], m.group(1) if m else None))
                if r.get("rec") == "agent" and r.get("event") == "see_attack":
                    m = re.search(r"added=(\d+)", r.get("detail") or "")
                    if m and int(m.group(1)) > 0:
                        moves[(r.get("turn"), r.get("player"))].append(("see_added", None))
            deaths = collections.defaultdict(set)
            ptmap = {}
            for r in lives:
                if r.get("rec") != "zone":
                    continue
                if r.get("from") == "Battlefield" and LIVE_PH.get(r.get("phase") or "", -9) in (7, 8):
                    deaths[r.get("turn")].add(r["cardId"])
                if r.get("to") == "Battlefield":
                    ptmap[r["cardId"]] = r.get("pt") or ""
            turn = 0
            atk = {}
            blk = collections.defaultdict(list)

            def close():
                for aid, (ap, dfd) in atk.items():
                    pl = pilot.get(ap)
                    mv = moves.get((turn, ap), [])
                    evs = {e for e, o in mv}
                    onto = {o for e, o in mv if o}
                    cls = "moved_turn" if mv else "no_move"
                    tgt_cls = "to_moved_target" if dfd in onto else "other"
                    bl = blk.get(aid, [])
                    died = bool(bl) and aid in deaths[turn] and not any(b in deaths[turn] for b in bl)
                    a = pt_split(ptmap.get(aid, ""))
                    bs = [pt_split(ptmap.get(b, "")) for b in bl]
                    pred = died and a and all(bs) and a[0] < min(x[1] for x in bs) and sum(x[0] for x in bs) >= a[1]
                    for key in (cls, cls + "|" + tgt_cls) if mv else (cls,):
                        out[(ds, pl, key, "attackers")] += 1
                        out[(ds, pl, key, "blocked")] += bool(bl)
                        out[(ds, pl, key, "died_nothing")] += bool(died)
                        out[(ds, pl, key, "pred")] += bool(pred)
                    for ev in evs:
                        if dfd in onto or ev == "see_added":
                            out[(ds, pl, "ev:" + ev, "attackers")] += 1
                            out[(ds, pl, "ev:" + ev, "died_nothing")] += bool(died)
                            out[(ds, pl, "ev:" + ev, "pred")] += bool(pred)
                atk.clear(); blk.clear()

            for e in ents:
                t, msg = e.get("type"), (e.get("message") or "").strip()
                if t == "TURN":
                    close()
                    m = TURN_RE.match(msg)
                    turn = int(m.group(1)) if m else turn
                    continue
                if t == "COMBAT":
                    for one in msg.split("\n"):
                        one = one.strip()
                        mb = BLK_RE.match(one)
                        if mb:
                            for aid in [int(x) for x in IDREF.findall(mb.group(3))]:
                                blk[aid] += [int(x) for x in IDREF.findall(mb.group(2))]
                            continue
                        ma = ATK_RE.match(one)
                        if ma:
                            for aid in [int(x) for x in IDREF.findall(ma.group(2))]:
                                atk[aid] = (ma.group(1), ma.group(3).strip().rstrip("."))
            close()
rows = collections.defaultdict(dict)
for (ds, pl, key, what), v in out.items():
    rows[(ds, pl, key)][what] = v
for k in sorted(rows, key=str):
    r = rows[k]
    a = r.get("attackers", 0)
    print(f"{str(k):70s} attackers {a:6d}  blocked {r.get('blocked', 0):5d}  died_nothing {r.get('died_nothing', 0):5d} ({r.get('died_nothing', 0) / a if a else 0:.3f})  predictable {r.get('pred', 0):5d} ({r.get('pred', 0) / a if a else 0:.3f})")
