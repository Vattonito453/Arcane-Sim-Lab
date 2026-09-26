#!/usr/bin/env python3
"""Glaring-error detectors over raw shim JSONL (read-only diagnosis).

The shim writes TWO streams per game and does not interleave them:
  - `entry` records: Forge's game log, dumped as one block, ordered by seq,
    carrying TURN / PHASE / STACK_ADD / LAND / MANA / COMBAT / DISCARD ...
  - live records (`zone`, `tap`, `rubric`, `agent`): streamed from the event
    bus, carrying `turn` and (shim >= 0.13) `phase`.
So state is rebuilt by merging on (turn, phase-rank). Phase-less logs
(shim < 0.13) are merged at turn granularity: their records are placed after
MAIN2 of their turn (start-of-turn state for casts, end-of-turn for the end
step check). `--phaseless` forces that rule on phased logs for an
apples-to-apples comparison with old stock data.
"""
from __future__ import annotations
import bisect, collections, glob, json, os, re, sys
from pathlib import Path

REPO = Path("C:/Users/Vatto/Magic Rules Engine")
sys.path.insert(0, str(REPO / "engine"))
import cards  # noqa: E402

CACHE = cards._load()
MISSING = collections.Counter()


def cinfo(name):
    if not name:
        return {}
    d = CACHE.get(cards.key(name)) or CACHE.get(name.lower())
    if d is None:
        MISSING[name] += 1
        return {}
    return d


ENTRY_PH = [("Untap step", 0), ("Upkeep step", 1), ("Draw step", 2), ("Main phase, precombat", 3),
            ("Beginning of Combat Step", 4), ("Declare Attackers Step", 5), ("Declare Blockers Step", 6),
            ("First Strike Damage Step", 7), ("Combat Damage Step", 8), ("End of Combat Step", 9),
            ("Main phase, postcombat", 10), ("End step", 11), ("Cleanup step", 12)]
LIVE_PH = {"": -1, "UNTAP": 0, "UPKEEP": 1, "DRAW": 2, "MAIN1": 3, "COMBAT_BEGIN": 4,
           "COMBAT_DECLARE_ATTACKERS": 5, "COMBAT_DECLARE_BLOCKERS": 6, "COMBAT_FIRST_STRIKE_DAMAGE": 7,
           "COMBAT_DAMAGE": 8, "COMBAT_END": 9, "MAIN2": 10, "END_OF_TURN": 11, "CLEANUP": 12}
PHASELESS_RANK = 10.5

TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)\s*$")
CAST_RE = re.compile(r"^(Ai\(\d\)-.+?) (cast|activated|triggered) (.+?)(?: targeting \[(.*)\])?\s*$")
IDREF = re.compile(r"\((\d+)\)")
ATK_RE = re.compile(r"^(Ai\(\d\)-.+?) assigned (.+) to attack (.+?)\.?$")
BLK_RE = re.compile(r"^(Ai\(\d\)-.+?) assigned (.+) to block (.+?)\.?$")
MANA_RE = re.compile(r"\((\d+)\) - ")
LOST_RE = re.compile(r"^(Ai\(\d\)-.+?) has lost")
DISC_RE = re.compile(r"^(Ai\(\d\)-.+?) discards (.+?)\.?$")

COLORS = "WUBRG"
BASIC = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
_LC = {}


def lcol(name):
    if name in _LC:
        return _LC[name]
    ci = cinfo(name)
    tl = ci.get("type_line", "") or ""
    txt = ci.get("oracle_text", "") or ""
    out = set()
    for b, c in BASIC.items():
        if b in tl:
            out.add(c)
    if re.search(r"any color|any type|of any one color|mana of any", txt):
        out |= set(COLORS)
    for sent in re.findall(r"Add ([^.]*)", txt):
        for sym in re.findall(r"\{([WUBRGC])\}", sent):
            out.add(sym)
    if not out and "Search your library" in txt:
        out = set()          # fetchland: counted as no mana (conservative)
    elif not out and ci:
        out = {"C"}
    elif not ci:
        out = {"C"}
    _LC[name] = out
    return out


def pips(mana_cost):
    if mana_cost is None:
        return None
    mana_cost = mana_cost.split("//")[0]
    gen, req = 0, []
    for sym in re.findall(r"\{([^}]*)\}", mana_cost):
        if sym.isdigit():
            gen += int(sym)
        elif sym in ("X", "Y", "Z"):
            return None
        elif sym in COLORS or sym == "C":
            req.append({sym})
        elif "/" in sym:
            parts = sym.split("/")
            if "P" in parts:
                continue
            cols = {p for p in parts if p in COLORS}
            if any(p.isdigit() for p in parts):
                cols = cols | {"*"}
            req.append(cols)
        elif sym == "S":
            req.append(set(COLORS) | {"C"})
    return gen, req


def payable(cost, lands):
    if cost is None:
        return False
    gen, req = cost
    if len(req) + gen > len(lands):
        return False
    match = [-1] * len(lands)

    def aug(i, seen):
        want = req[i]
        for j, cs in enumerate(lands):
            if j in seen:
                continue
            if "*" in want or (want & cs):
                seen.add(j)
                if match[j] == -1 or aug(match[j], seen):
                    match[j] = i
                    return True
        return False

    for i in range(len(req)):
        if not aug(i, set()):
            return False
    return sum(1 for m in match if m == -1) >= gen


def role(name):
    ci = cinfo(name)
    return ci.get("oracle_text") or "", ci.get("type_line") or ""


def is_perm_types(types):
    return any(t in types for t in ("Creature", "Artifact", "Enchantment", "Planeswalker", "Battle")) and "Land" not in types


def has_flash(name):
    txt, tl = role(name)
    return "Instant" in tl or bool(re.search(r"(^|\n)Flash", txt))


def is_ritual(name):
    txt, tl = role(name)
    return ("Instant" in tl or "Sorcery" in tl) and bool(re.search(r"(^|\n|• )Add \{", txt)) and "Search" not in txt


def is_counterspell(name):
    txt, tl = role(name)
    return ("Instant" in tl or "Sorcery" in tl) and "Counter target" in txt


REMOVAL_RE = re.compile(r"(Destroy target|Exile target (?!card)|deals? \d+ damage to (?:any )?target|"
                        r"deals damage equal to [^.]* to (?:any )?target|target creature gets -\d|"
                        r"Return target (?:nonland )?(?:creature|permanent|artifact|enchantment)[^.]* to its owner's hand)")
WRATH_RE = re.compile(r"(Destroy all|Exile all|All creatures get -|deals? \d+ damage to each creature|"
                      r"Return all (?:nonland|creature)|Destroy each|Each player sacrifices all)", re.I)
SELF_OK_RE = re.compile(r"(you control|Return (?:it|that card|the exiled card)|then return|return it|return that|"
                        r"its controller creates|its controller may search|you own)", re.I)


def is_removal(name):
    txt, tl = role(name)
    return ("Instant" in tl or "Sorcery" in tl) and bool(REMOVAL_RE.search(txt))


def is_wrath(name):
    txt, tl = role(name)
    return ("Instant" in tl or "Sorcery" in tl) and bool(WRATH_RE.search(txt)) and "creature" in txt.lower()


def rockish(name):
    txt, tl = role(name)
    return ("Artifact" in tl or "Creature" in tl) and "{T}: Add" in txt and "Land" not in tl


def ramp_spell(name):
    txt, tl = role(name)
    return bool(re.search(r"Search your library for (?:a|up to \w+) basic land", txt))


def pt_split(pt):
    try:
        a, b = pt.split("/")
        return int(a), int(b)
    except Exception:
        return None


class Acc:
    def __init__(self):
        self.n = collections.Counter()
        self.ex = collections.defaultdict(list)
        self.dist = collections.defaultdict(list)

    def add(self, pilot, key, k=1, ex=None):
        self.n[(pilot, key)] += k
        if ex is not None and len(self.ex[(pilot, key)]) < 300:
            self.ex[(pilot, key)].append(ex)


def parse_entry_phase(msg):
    for suf, rk in ENTRY_PH:
        if msg.endswith(suf):
            return rk
    return None


def games_of(path):
    """Yield (meta, game_no, entries, lives) per game."""
    meta = None
    cur = None
    ents, lives = [], []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") == "meta":
                meta = r
                continue
            g = r.get("game")
            if g is None:
                continue
            if cur is not None and g != cur:
                # streams of one game are contiguous per stream; a new number closes the old
                pass
            if r.get("rec") == "entry":
                ents.append(r)
            else:
                lives.append(r)
            cur = g
    if meta is None:
        return
    byg_e = collections.defaultdict(list)
    byg_l = collections.defaultdict(list)
    for r in ents:
        byg_e[r["game"]].append(r)
    for r in lives:
        byg_l[r["game"]].append(r)
    for g in sorted(set(byg_e) | set(byg_l)):
        e = sorted(byg_e[g], key=lambda x: x.get("seq", 0))
        yield meta, g, e, byg_l[g]


def analyse_game(meta, gno, ents, lives, acc, tag, plan_pieces, force_phaseless=False, fname=""):
    players = meta.get("players", [])
    pilot = dict(zip(players, meta.get("agents", [])))
    v = meta.get("shim") or "0"
    try:
        ver = tuple(int(x) for x in v.split(".")[:2])
    except ValueError:
        ver = (0, 0)
    has_tap = ver >= (0, 12) and not force_phaseless
    phased = ver >= (0, 13) and not force_phaseless

    def P(p):
        return pilot.get(p, "?")

    for p in players:
        acc.add(P(p), "seat_games", 1)
    acc.add("all", "games", 1)
    res = [r for r in lives if r.get("rec") == "result"]
    decided = bool(res and res[-1].get("winner"))
    timed_out = bool(res and res[-1].get("timedOut"))

    # ---------- live stream keyed by (turn, rank)
    def lkey(r):
        t = r.get("turn") or 0
        if phased:
            return (t, LIVE_PH.get(r.get("phase") or "", 10.5))
        return (t, -1 if t == 0 else PHASELESS_RANK)

    live = [r for r in lives if r.get("rec") in ("zone", "tap")]
    if force_phaseless:
        live = [r for r in live if r.get("rec") == "zone"]
    # battlefield controller history for target ownership
    ctl_hist = collections.defaultdict(list)
    for r in live:
        if r.get("rec") == "zone" and r.get("to") == "Battlefield" and r.get("toPlayer"):
            ctl_hist[r["cardId"]].append((lkey(r), r["toPlayer"], r.get("card"), r.get("types") or "", r.get("pt") or ""))

    def controller_at(cid, key):
        best = None
        for k, p, nm, ty, pt in ctl_hist.get(cid, []):
            if k <= key:
                best = (p, nm, ty, pt)
        return best

    deaths_by_turn = collections.defaultdict(set)
    for r in live:
        if r.get("rec") == "zone" and r.get("from") == "Battlefield":
            if (not phased) or LIVE_PH.get(r.get("phase") or "", -9) in (7, 8):
                deaths_by_turn[r.get("turn") or 0].add(r["cardId"])

    S = {"hands": collections.defaultdict(dict), "bf": collections.defaultdict(dict), "tapped": {}}
    ptr = [0]

    def advance(key):
        while ptr[0] < len(live) and lkey(live[ptr[0]]) < key:
            r = live[ptr[0]]
            ptr[0] += 1
            if r["rec"] == "tap":
                S["tapped"][r["cardId"]] = bool(r.get("tapped"))
                continue
            cid, fr, to = r.get("cardId"), r.get("from"), r.get("to")
            fp, tp = r.get("fromPlayer") or "", r.get("toPlayer") or ""
            nm, ty = r.get("card") or "", r.get("types") or ""
            if fr == "Hand" and fp:
                S["hands"][fp].pop(cid, None)
            if to == "Hand" and tp:
                S["hands"][tp][cid] = (nm, ty, lkey(r))
            if fr == "Battlefield" and fp:
                S["bf"][fp].pop(cid, None)
            if to == "Battlefield" and tp:
                S["bf"][tp][cid] = (nm, ty, r.get("pt") or "")
                if not has_tap:
                    S["tapped"].setdefault(cid, False)

    def untapped_lands(p):
        out = []
        for cid, (nm, ty, pt) in S["bf"][p].items():
            if "Land" in ty and not S["tapped"].get(cid, False):
                cs = lcol(nm)
                if cs:
                    out.append(cs)
        return out

    def land_count(p):
        return sum(1 for (nm, ty, pt) in S["bf"][p].values() if "Land" in ty)

    def castable_perms(p, lands, before_key):
        outl = []
        for cid, (nm, ty, k) in S["hands"][p].items():
            if k > before_key:
                continue
            if not is_perm_types(ty):
                continue
            ci = cinfo(nm)
            if not ci or "Aura" in (ci.get("type_line") or "") or has_flash(nm):
                continue
            c = pips(ci.get("mana_cost"))
            if c and payable(c, lands):
                outl.append((nm, ci.get("cmc")))
        return outl

    # ---------- walk the entry stream
    turn, tp_, rank = 0, None, -1
    lands_played = collections.Counter()
    alive = set(players)
    pending_ritual = None
    attackers, blocks, dead_in_combat = {}, collections.defaultdict(list), set()
    mana_tapped_turn = set()
    end_done = set()
    discards_turn = []

    def finish_ritual():
        nonlocal pending_ritual
        if pending_ritual is None:
            return
        caster, name, t, rk, followed = pending_ritual
        acc.add(P(caster), "ritual_cast", 1)
        if not followed:
            acc.add(P(caster), "ritual_wasted", 1, (tag, fname, gno, t, rk, caster, name))
        pending_ritual = None

    def close_combat():
        nonlocal attackers, blocks
        if attackers:
            # deaths this combat: zone records Battlefield->Graveyard in this turn at damage ranks
            deaths = deaths_by_turn.get(turn, set())
            for aid, (ap, an, apt) in attackers.items():
                acc.add(P(ap), "attackers", 1)
                bl = blocks.get(aid, [])
                if not bl:
                    continue
                acc.add(P(ap), "attackers_blocked", 1)
                if aid in deaths and not any(b in deaths for b, bn, bpt in bl):
                    a = pt_split(apt)
                    bs = [pt_split(bpt) for b, bn, bpt in bl]
                    pred = bool(a and all(bs) and a[0] < min(x[1] for x in bs) and sum(x[0] for x in bs) >= a[1])
                    acc.add(P(ap), "attacker_died_for_nothing", 1, (tag, fname, gno, turn, ap, an, apt, [(bn, bpt) for b, bn, bpt in bl]))
                    if pred:
                        acc.add(P(ap), "attacker_died_for_nothing_predictable", 1,
                                (tag, fname, gno, turn, ap, an, apt, [(bn, bpt) for b, bn, bpt in bl]))
        attackers, blocks = {}, collections.defaultdict(list)

    def end_check(t, p):
        if (t, p) in end_done or p not in alive:
            return
        end_done.add((t, p))
        pl = P(p)
        advance((t, 10.99))
        acc.add(pl, "player_turns", 1)
        early = (t, 3.5) if phased else (t - 1, 99)   # in hand by main 1 (phased) / before the turn (phaseless)
        lands_in = [nm for cid, (nm, ty, k) in S["hands"][p].items() if "Land" in ty and k <= early]
        if lands_played[p] == 0:
            if lands_in:
                acc.add(pl, "missed_land_drop", 1, (tag, fname, gno, t, p, lands_in[:3], land_count(p)))
                if land_count(p) < 6:
                    acc.add(pl, "missed_land_drop_under6", 1)
            acc.add(pl, "turns_no_land_played", 1)
        if True:
            if not has_tap:
                pl = pl + "~est"
            lands = untapped_lands(p)
            acc.add(pl, "tap_turns", 1)
            acc.add(pl, "untapped_at_end_sum", len(lands))
            cp = castable_perms(p, lands, (t, 10.0) if phased else (t, 99))
            hand_inst = [nm for cid, (nm, ty, k) in S["hands"][p].items() if "Land" not in ty and has_flash(nm)]
            if cp:
                key = "unspent_castable_perm" + ("_hold_instant" if hand_inst else "_no_instant")
                acc.add(pl, key, 1, (tag, fname, gno, t, p, len(lands), cp[:3], hand_inst[:2]))
                if len(lands) >= 4 and not hand_inst and any((c or 0) >= 2 for n, c in cp):
                    acc.add(pl, "unspent4_castable_perm_no_instant", 1, (tag, fname, gno, t, p, len(lands), cp[:3]))

    for e in ents:
        typ = e.get("type")
        msg = (e.get("message") or "").strip()
        if typ == "TURN":
            m = TURN_RE.match(msg)
            if m:
                finish_ritual()
                turn, tp_ = int(m.group(1)), m.group(2)
                lands_played = collections.Counter()
                rank = -1
            continue
        if typ == "PHASE":
            rk = parse_entry_phase(msg)
            if rk is None:
                continue
            if rk != rank:
                finish_ritual()
            if rank in (7, 8, 9) and rk not in (7, 8, 9):
                close_combat()
            if rk == 0 and not has_tap and tp_:
                advance((turn, 0))
                for cid in S["bf"][tp_]:
                    S["tapped"][cid] = False
            if rk == 11 and tp_:
                end_check(turn, tp_)
            rank = rk
            continue
        if typ == "LAND":
            m = re.match(r"^(Ai\(\d\)-.+?) played ", msg)
            if m:
                lands_played[m.group(1)] += 1
            continue
        if typ == "MANA":
            if not has_tap:
                m = MANA_RE.search(msg)
                if m:
                    S["tapped"][int(m.group(1))] = True
            continue
        if typ == "DISCARD" and rank == 12:
            m = DISC_RE.match(msg)
            if m and m.group(1) == tp_:
                p = m.group(1)
                nm = IDREF.sub("", m.group(2)).strip()
                pl = P(p)
                advance((turn, 10.99))
                ci = cinfo(nm)
                ty = ci.get("type_line") or ""
                acc.add(pl, "cleanup_discard", 1)
                if "Land" in ty and "//" not in ty:
                    acc.add(pl, "cleanup_discard_land", 1)
                else:
                    if has_tap:
                        lands = untapped_lands(p)
                        c = pips(ci.get("mana_cost"))
                        if is_perm_types(ty) and "Aura" not in ty and c and payable(c, lands):
                            acc.add(pl, "cleanup_discard_castable_perm", 1, (tag, fname, gno, turn, p, nm, len(lands)))
                    land_in_hand = [n for cid, (n, t_, k) in S["hands"][p].items() if "Land" in t_]
                    if land_in_hand and land_count(p) >= 6:
                        acc.add(pl, "cleanup_discard_spell_while_holding_land_6plus", 1, (tag, fname, gno, turn, p, nm, land_in_hand[:2], land_count(p)))
                    deck = p.split("-", 1)[1] if "-" in p else p
                    if plan_pieces and nm in plan_pieces.get(deck, set()):
                        acc.add(pl, "cleanup_discard_line_or_tutor", 1, (tag, fname, gno, turn, p, nm))
            continue
        if typ == "GAME_OUTCOME":
            m = LOST_RE.match(msg)
            if m:
                p = m.group(1)
                advance((turn, rank + 0.5))
                acc.add(P(p), "eliminations", 1)
                acc.add(P(p), "hand_at_elim_sum", len(S["hands"][p]))
                if has_tap:
                    lands = untapped_lands(p)
                    held = []
                    for cid, (nm, ty, k) in S["hands"][p].items():
                        if "Land" in ty or not has_flash(nm):
                            continue
                        txt = role(nm)[0]
                        if is_removal(nm) or is_counterspell(nm) or re.search(r"Prevent all combat damage", txt):
                            c = pips(cinfo(nm).get("mana_cost"))
                            if c and payable(c, lands):
                                held.append(nm)
                    acc.add(P(p), "elim_tap", 1)
                    if held:
                        acc.add(P(p), "died_holding_castable_answer", 1, (tag, fname, gno, turn, rank, p, held[:3], len(lands)))
                alive.discard(p)
            continue
        if typ == "COMBAT":
            for one in msg.split("\n"):
                one = one.strip()
                mb = BLK_RE.match(one)
                if mb:
                    bids = [int(x) for x in IDREF.findall(mb.group(2))]
                    aids = [int(x) for x in IDREF.findall(mb.group(3))]
                    for aid in aids:
                        for bid in bids:
                            info = controller_at(bid, (turn, 6))
                            blocks[aid].append((bid, info[1] if info else "?", info[3] if info else ""))
                    continue
                ma = ATK_RE.match(one)
                if ma:
                    ap = ma.group(1)
                    for aid in [int(x) for x in IDREF.findall(ma.group(2))]:
                        info = controller_at(aid, (turn, 5))
                        attackers[aid] = (ap, info[1] if info else "?", info[3] if info else "")
            continue
        if typ == "STACK_ADD":
            m = CAST_RE.match(msg)
            if not m:
                continue
            caster, verb, card, tgt = m.group(1), m.group(2), m.group(3), m.group(4)
            card = IDREF.sub("", card).strip()
            pl = P(caster)
            if pending_ritual is not None and pending_ritual[0] == caster and verb in ("cast", "activated"):
                pending_ritual = (*pending_ritual[:4], True)
            if verb != "cast":
                continue
            acc.add(pl, "casts", 1)
            if is_ritual(card):
                finish_ritual()
                pending_ritual = (caster, card, turn, rank, False)
            key = (turn, rank + 0.5 if phased else PHASELESS_RANK - 0.01)
            skey = (turn, rank if phased else PHASELESS_RANK - 0.01)   # start of this step: excludes the spell's own effects
            if tgt is not None:
                tids = [int(x) for x in IDREF.findall(tgt)]
                owners = {cid: controller_at(cid, key) for cid in tids}
                if is_removal(card):
                    acc.add(pl, "removal_targeted", 1)
                    txt = role(card)[0]
                    own = [cid for cid, o in owners.items() if o and o[0] == caster]
                    if tids and len(own) == len(tids) and not SELF_OK_RE.search(txt):
                        acc.add(pl, "removal_on_own_permanent", 1, (tag, fname, gno, turn, caster, card, [owners[c][1] for c in own]))
                    advance(skey)
                    opp_t = [o for cid, o in owners.items() if o and o[0] != caster]
                    tpow = [pt_split(o[3])[0] for o in opp_t if "Creature" in o[2] and pt_split(o[3])]
                    big = 0
                    for p2 in alive:
                        if p2 == caster:
                            continue
                        for cid, (nm, ty, pt) in S["bf"][p2].items():
                            ps = pt_split(pt)
                            if "Creature" in ty and ps:
                                big = max(big, ps[0])
                    if tpow and max(tpow) <= 2 and big >= 7:
                        acc.add(pl, "removal_small_target_while_7power_stands", 1, (tag, fname, gno, turn, caster, card, tgt, big))
                if is_counterspell(card):
                    acc.add(pl, "counters_cast", 1)
                    tname = IDREF.sub("", tgt).strip()
                    if rockish(tname) or ramp_spell(tname):
                        acc.add(pl, "counter_on_ramp_or_rock", 1, (tag, fname, gno, turn, caster, card, tname))
            if is_wrath(card):
                advance(skey)
                mine = [(pt_split(pt) or (0, 0))[0] for (nm, ty, pt) in S["bf"][caster].values() if "Creature" in ty]
                opp = {}
                for p2 in alive:
                    if p2 == caster:
                        continue
                    opp[p2] = [(pt_split(pt) or (0, 0))[0] for (nm, ty, pt) in S["bf"][p2].values() if "Creature" in ty]
                acc.add(pl, "wraths", 1)
                mx = max((sum(v) for v in opp.values()), default=0)
                nopp = sum(len(v) for v in opp.values())
                if len(mine) >= 2 and sum(mine) > mx:
                    acc.add(pl, "wrath_while_ahead", 1, (tag, fname, gno, turn, caster, card, len(mine), sum(mine), sorted(((len(v), sum(v)) for v in opp.values()), reverse=True)))
                if nopp <= 1:
                    acc.add(pl, "wrath_into_empty", 1, (tag, fname, gno, turn, caster, card, len(mine), nopp))
            continue
    finish_ritual()
    close_combat()

    # rubric: unnecessary chumps (neutral observer, every seat)
    for r in lives:
        if r.get("rec") == "rubric" and r.get("kind") == "block":
            pl = P(r.get("player"))
            acc.add(pl, "rubric_block_recs", 1)
            v0 = r.get("v0") or 0
            acc.add(pl, "rubric_blocks", r.get("blocked") or 0)
            acc.add(pl, "rubric_chumps", v0)
            life_before = (r.get("life") or 0) + (r.get("lifeTaken") or 0)
            inc = r.get("incomingPower") or 0
            if v0 and life_before >= 20 and inc * 2 <= life_before:
                acc.add(pl, "chump_not_needed", v0, (tag, fname, gno, r.get("turn"), r.get("player"), inc, life_before, v0))
    acc.add("all", "decided", 1 if decided else 0)
    acc.add("all", "timed_out", 1 if timed_out else 0)


def load_plan_pieces(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    decks = d.get("decks") or {}
    out = {}
    for deck, pl in decks.items():
        s = set()
        for line in pl.get("lines") or []:
            s |= set(line.get("cards") or [])
        s |= set(pl.get("tutors") or [])
        out[deck] = s
    return out


DATASETS = {
    "cedh015": "studies/agent_viability/runs_015_default/cell_*.jsonl",
    "cedh016": "studies/agent_viability/runs_016_engine/cell_*.jsonl",
    "precon_agent015": "studies/precon_predict/runs_agent_015/*.jsonl",
    "precon_stock": "studies/precon_predict/runs_stock/*.jsonl",
    "precon_mixed_base": "studies/behavior_rubric/runs_overnight/base/*.jsonl",
    "hc_stock": "studies/human_ceiling/runs/*.jsonl",
    "engine_ab": "studies/engine_ab/runs/*.jsonl",
    "cedh_shipping": "studies/behavior_rubric/runs_agent_shipping/*.jsonl",
}

if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--phaseless" in args
    args = [a for a in args if a != "--phaseless"]
    out = {}
    for ds in args:
        acc = Acc()
        files = sorted(glob.glob(str(REPO / DATASETS[ds])))
        for f in files:
            pp = None
            m = re.search(r"cell_(.+?)_rot", f)
            if m:
                pp = load_plan_pieces(str(Path(f).parent / f"plans_{m.group(1)}.json"))
            for meta, gno, e, l in games_of(f):
                analyse_game(meta, gno, e, l, acc, ds, pp, force, os.path.basename(f))
        tag = ds + ("_phaseless" if force else "")
        out[tag] = {"n": {f"{k[0]}|{k[1]}": v for k, v in acc.n.items()},
                    "ex": {f"{k[0]}|{k[1]}": v for k, v in acc.ex.items()}}
        print(tag, len(files), "files", file=sys.stderr)
    od = Path(__file__).parent
    name = "out2_" + "_".join(args) + ("_phaseless" if force else "") + ".json"
    json.dump(out, open(od / name, "w"), indent=0, default=str)
    print("missing card facts:", len(MISSING), MISSING.most_common(8), file=sys.stderr)
