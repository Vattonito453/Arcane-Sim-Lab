"""Wasted rituals, precise version. Entry stream only (ordered by seq).
A ritual is wasted when its caster casts/activates nothing after it before the
mana empties: end of the step, or end of turn for 'don't lose this mana' cards.
Land plays after the ritual are also counted as use for Jeska's Will (exile mode)."""
import sys, re, json, glob, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import games_of, parse_entry_phase, CAST_RE, IDREF, TURN_RE, role, is_ritual, REPO, DATASETS

out = collections.Counter()
ex = collections.defaultdict(list)
for ds in sys.argv[1:]:
    for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
        for meta, g, ents, lives in games_of(f):
            pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
            pend = []   # [caster, card, turn, rank, followed, persist]
            turn, rank = 0, -1

            def close(all_=False, turn_end=False):
                keep = []
                for p in pend:
                    if p[5] and not turn_end:
                        keep.append(p)
                        continue
                    kind = "jeska" if p[1] == "Jeska's Will" else ("persist" if p[5] else "classic")
                    out[(ds, pilot.get(p[0]), kind, "cast")] += 1
                    if not p[4]:
                        out[(ds, pilot.get(p[0]), kind, "wasted")] += 1
                        if len(ex[(ds, kind)]) < 50:
                            ex[(ds, kind)].append((os.path.basename(f), g, p[2], p[3], p[0], p[1]))
                pend[:] = keep

            for e in ents:
                t, msg = e.get("type"), (e.get("message") or "").strip()
                if t == "TURN":
                    close(turn_end=True)
                    m = TURN_RE.match(msg)
                    turn = int(m.group(1)) if m else turn
                    rank = -1
                    continue
                if t == "PHASE":
                    rk = parse_entry_phase(msg)
                    if rk is not None and rk != rank:
                        close()
                        rank = rk
                    continue
                if t == "LAND":
                    for p in pend:
                        if p[1] == "Jeska's Will" and msg.startswith(p[0]):
                            p[4] = True
                    continue
                if t == "STACK_ADD":
                    m = CAST_RE.match(msg)
                    if not m:
                        continue
                    caster, verb, card = m.group(1), m.group(2), IDREF.sub("", m.group(3)).strip()
                    if verb in ("cast", "activated"):
                        for p in pend:
                            if p[0] == caster:
                                p[4] = True
                    if verb == "cast" and is_ritual(card):
                        persist = "don't lose this mana" in role(card)[0]
                        pend.append([caster, card, turn, rank, False, persist])
            close(turn_end=True)

rows = collections.defaultdict(dict)
for (ds, pl, kind, what), v in out.items():
    rows[(ds, pl, kind)][what] = v
for k in sorted(rows, key=str):
    c = rows[k].get("cast", 0); w = rows[k].get("wasted", 0)
    print(f"{str(k):60s} wasted {w:4d} / cast {c:4d} = {w / c if c else 0:.2f}")
json.dump({str(k): v for k, v in ex.items()}, open(os.path.join(os.path.dirname(__file__), "ritual_examples.json"), "w"), indent=0)
