import sys, os, re, glob, collections
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import games_of, parse_entry_phase, TURN_RE, LOST_RE, REPO, DATASETS
out = collections.Counter(); ex = collections.defaultdict(list)
for ds in sys.argv[1:]:
    for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
        for meta, g, ents, lives in games_of(f):
            pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
            turn, tp, rank = 0, None, -1
            recent = []
            for e in ents:
                t, msg = e.get("type"), (e.get("message") or "").strip()
                recent.append((t, msg)); recent = recent[-8:]
                if t == "TURN":
                    m = TURN_RE.match(msg); turn, tp = (int(m.group(1)), m.group(2)) if m else (turn, tp); rank = -1
                elif t == "PHASE":
                    rk = parse_entry_phase(msg); rank = rk if rk is not None else rank
                elif t == "GAME_OUTCOME":
                    m = LOST_RE.match(msg)
                    if not m or "life total" not in msg: continue
                    p = m.group(1); pl = pilot.get(p)
                    out[(ds, pl, "life_losses")] += 1
                    if p == tp and rank not in (7, 8):
                        # last damage/life-loss source
                        src = [x for x in recent if x[0] in ("DAMAGE", "STACK_RESOLVE", "LIFE")]
                        out[(ds, pl, "own_turn_noncombat")] += 1
                        if len(ex[(ds, pl)]) < 12: ex[(ds, pl)].append((os.path.basename(f), g, turn, rank, [s[1][:110] for s in src[-3:]]))
for k in sorted(out, key=str): print(k, out[k])
for k, v in ex.items():
    print("==", k)
    for x in v: print("  ", x)
