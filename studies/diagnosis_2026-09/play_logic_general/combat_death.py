"""Died in combat holding a castable instant that would have saved them.

A combat death qualifies when:
  - the loss is logged in a combat damage step (entry stream),
  - removing the single biggest damage source would have left life > 0
    (end life + biggest attacker's damage > 0; lifelink/prevention ignored),
  - at that moment the dead player's hand holds an instant-speed card that
    removes, bounces or fogs a creature (oracle pattern), and the untapped
    lands (exact tap records, shim >= 0.12) can pay for it with colours.
Precision limits: hexproof/protection/indestructible attackers are not
checked; 'deals N damage to target creature' is excluded (toughness unknown);
Forge might have lacked priority in some edge flows (it never does in
declare blockers).
"""
import sys, re, json, glob, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from detect2 import (games_of, parse_entry_phase, CAST_RE, IDREF, TURN_RE, role, REPO, DATASETS,
                     LIVE_PH, lcol, pips, payable, cinfo, has_flash, LOST_RE)

SAVE_RE = re.compile(r"(Destroy target (?:creature|permanent|nonland permanent|artifact or creature|attacking)|"
                     r"Exile target (?:creature|permanent|nonland permanent|attacking|tapped creature)|"
                     r"Return target (?:creature|nonland permanent|permanent)[^.]* to its owner's hand|"
                     r"Put target (?:creature|nonland permanent)[^.]* on (?:top|the bottom)|"
                     r"Prevent all combat damage|target creature gets -[3-9]|Tap target creature|"
                     r"Target creature's owner shuffles)")
DMG_RE = re.compile(r"^(.+?) \((\d+)\) deals (\d+) combat damage to (Ai\(\d\)-.+?)\.?$")

out = collections.Counter()
ex = collections.defaultdict(list)
for ds in sys.argv[1:]:
    for f in sorted(glob.glob(str(REPO / DATASETS[ds]))):
        for meta, g, ents, lives in games_of(f):
            ver = tuple(int(x) for x in (meta.get("shim") or "0.0").split(".")[:2])
            if ver < (0, 13):
                continue
            pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
            live = [r for r in lives if r.get("rec") in ("zone", "tap")]

            def lkey(r):
                return (r.get("turn") or 0, LIVE_PH.get(r.get("phase") or "", 10.5))

            hands = collections.defaultdict(dict)
            bf = collections.defaultdict(dict)
            tapped = {}
            ptr = 0
            turn, rank = 0, -1
            dmg = collections.defaultdict(list)
            life = {}
            for e in ents:
                t, msg = e.get("type"), (e.get("message") or "").strip()
                if t == "TURN":
                    m = TURN_RE.match(msg)
                    turn = int(m.group(1)) if m else turn
                    rank = -1
                    dmg = collections.defaultdict(list)
                    continue
                if t == "PHASE":
                    rk = parse_entry_phase(msg)
                    if rk is not None:
                        if rk < 7 or rk > 8:
                            dmg = collections.defaultdict(list)
                        rank = rk
                    continue
                if t == "LIFE":
                    m = re.match(r"^Life: (.+) (-?\d+) > (-?\d+)$", msg)
                    if m:
                        life[m.group(1)] = int(m.group(3))
                    continue
                if t == "DAMAGE" and rank in (7, 8):
                    m = DMG_RE.match(msg)
                    if m:
                        dmg[m.group(4)].append((m.group(1), int(m.group(2)), int(m.group(3))))
                    continue
                if t == "GAME_OUTCOME":
                    m = LOST_RE.match(msg)
                    if not m:
                        continue
                    p = m.group(1)
                    pl = pilot.get(p)
                    out[(ds, pl, "elims")] += 1
                    if rank not in (7, 8) or not dmg.get(p):
                        continue
                    out[(ds, pl, "combat_elims")] += 1
                    # state as of the start of this damage step
                    while ptr < len(live) and lkey(live[ptr]) < (turn, 7):
                        r = live[ptr]; ptr += 1
                        if r["rec"] == "tap":
                            tapped[r["cardId"]] = bool(r.get("tapped")); continue
                        cid, fr, to = r.get("cardId"), r.get("from"), r.get("to")
                        fp, tp = r.get("fromPlayer") or "", r.get("toPlayer") or ""
                        if fr == "Hand" and fp: hands[fp].pop(cid, None)
                        if to == "Hand" and tp: hands[tp][cid] = (r.get("card") or "", r.get("types") or "")
                        if fr == "Battlefield" and fp: bf[fp].pop(cid, None)
                        if to == "Battlefield" and tp: bf[tp][cid] = (r.get("card") or "", r.get("types") or "")
                    total = sum(x[2] for x in dmg[p])
                    per = collections.Counter()
                    for nm, cid, n in dmg[p]:
                        per[cid] += n
                    biggest = max(per.values())
                    # life at end: from the last LIFE entry is not tracked here; use total vs 40-cap proxy
                    lands = [lcol(nm) for cid, (nm, ty) in bf[p].items() if "Land" in ty and not tapped.get(cid, False)]
                    lands = [x for x in lands if x]
                    savers = []
                    for cid, (nm, ty) in hands[p].items():
                        if "Land" in ty or not has_flash(nm):
                            continue
                        txt = role(nm)[0]
                        if SAVE_RE.search(txt):
                            c = pips(cinfo(nm).get("mana_cost"))
                            if (c and payable(c, lands)) or re.search(r"rather than pay|without paying|Pact of", txt):
                                savers.append(nm)
                    e2 = (os.path.basename(f), g, turn, p, len(per), total, biggest, life.get(p), savers, len(lands))
                    if life.get(p, 0) + biggest > 0:
                        out[(ds, pl, "combat_elim_one_removal_would_save")] += 1
                    if savers:
                        out[(ds, pl, "combat_elim_holding_saver")] += 1
                        if life.get(p, 0) + biggest > 0:
                            out[(ds, pl, "combat_elim_holding_saver_single_or_dominant")] += 1
                            if len(ex[(ds, pl)]) < 40:
                                ex[(ds, pl)].append(e2)
rows = collections.defaultdict(dict)
for (ds, pl, k), v in out.items():
    rows[(ds, pl)][k] = v
for k in sorted(rows, key=str):
    print(k, dict(sorted(rows[k].items())))
json.dump({str(k): v for k, v in ex.items()}, open(os.path.join(os.path.dirname(__file__), "combat_death_examples.json"), "w"), indent=0)
