#!/usr/bin/env python3
"""Glaring-error detectors over raw shim JSONL. Read-only diagnosis.

Reconstructs per game: whose turn / which step, every player's hand and
battlefield (zone records carry cardId, from/to, owner, core types, pt),
tapped state (tap records on shim >= 0.12, else MANA entries since the
controller's untap step), land plays, casts with targets, combat.

Each detector counts events and an eligible denominator, keyed by pilot
(plan/stock) from the meta record. Examples are sampled for audit.
"""
from __future__ import annotations
import collections, glob, json, os, random, re, sys
from pathlib import Path

REPO = Path("C:/Users/Vatto/Magic Rules Engine")
sys.path.insert(0, str(REPO / "engine"))
import cards  # noqa: E402

CACHE = cards._load()


def cinfo(name):
    if not name:
        return {}
    return CACHE.get(cards.key(name)) or CACHE.get(name.lower()) or {}


PHASES = [("Untap step", "untap"), ("Upkeep step", "upkeep"), ("Draw step", "draw"),
          ("Main phase, precombat", "main1"), ("Beginning of Combat Step", "bcombat"),
          ("Declare Attackers Step", "attackers"), ("Declare Blockers Step", "blockers"),
          ("First Strike Damage Step", "fsdamage"), ("Combat Damage Step", "damage"),
          ("End of Combat Step", "ecombat"), ("Main phase, postcombat", "main2"),
          ("End step", "end"), ("Cleanup step", "cleanup")]
TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)\s*$")
CAST_RE = re.compile(r"^(Ai\(\d\)-.+?) (cast|activated|triggered) (.+?)(?: targeting \[(.*)\])?\s*$")
IDREF = re.compile(r"\((\d+)\)")
LIFE_RE = re.compile(r"^Life: (.+) (-?\d+) > (-?\d+)$")
ATK_RE = re.compile(r"^(Ai\(\d\)-.+?) assigned (.+) to attack (.+?)\.?$")
BLK_RE = re.compile(r"^(Ai\(\d\)-.+?) assigned (.+) to block (.+?)\.?$")
MANA_RE = re.compile(r"\((\d+)\) - ")
LOST_RE = re.compile(r"^(Ai\(\d\)-.+?) has lost")

COLORS = "WUBRG"
BASIC = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


def land_colors(name):
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
    if "Search your library" in txt and not out:
        return set()   # fetchland: no mana of its own (conservative)
    if not out and "Land" in tl:
        out.add("C")  # unknown: count as colorless
    return out


_LC = {}


def lcol(name):
    if name not in _LC:
        _LC[name] = land_colors(name)
    return _LC[name]


def pips(mana_cost):
    """-> (generic, [set_of_colors per colored pip]) ; None when X or unparseable."""
    if mana_cost is None:
        return None
    if "//" in mana_cost:
        mana_cost = mana_cost.split("//")[0]
    gen = 0
    req = []
    for sym in re.findall(r"\{([^}]*)\}", mana_cost):
        if sym.isdigit():
            gen += int(sym)
        elif sym in ("X", "Y", "Z"):
            return None
        elif sym in COLORS:
            req.append({sym})
        elif sym == "C":
            req.append({"C"})
        elif "/" in sym:
            parts = sym.split("/")
            if "P" in parts:
                continue  # phyrexian: payable with life
            cols = {p for p in parts if p in COLORS}
            nums = [int(p) for p in parts if p.isdigit()]
            if nums:
                gen += 0  # {2/W}: treat as one colored or 2 generic -> take colored path
                req.append(cols | {"*"})
            else:
                req.append(cols)
        elif sym == "S":
            req.append({"C", "W", "U", "B", "R", "G"})
    return gen, req


def payable(cost, lands):
    """lands: list of color sets (untapped). Bipartite match colored pips then generic."""
    if cost is None:
        return False
    gen, req = cost
    if len(req) + gen > len(lands):
        return False
    match = [-1] * len(lands)

    def try_pip(i, seen):
        want = req[i]
        for j, cs in enumerate(lands):
            if j in seen:
                continue
            if "*" in want or (want & cs):
                seen.add(j)
                if match[j] == -1 or try_pip(match[j], seen):
                    match[j] = i
                    return True
        return False

    for i in range(len(req)):
        if not try_pip(i, set()):
            return False
    free = sum(1 for m in match if m == -1)
    return free >= gen


def is_permanent_spell(types):
    return any(t in types for t in ("Creature", "Artifact", "Enchantment", "Planeswalker", "Battle")) \
        and "Land" not in types


def card_role(name):
    ci = cinfo(name)
    txt = (ci.get("oracle_text") or "")
    tl = ci.get("type_line") or ""
    return txt, tl


def is_ritual(name):
    txt, tl = card_role(name)
    if not ("Instant" in tl or "Sorcery" in tl):
        return False
    return bool(re.search(r"(^|\n|• )Add \{", txt)) and "Search" not in txt


def is_counterspell(name):
    txt, tl = card_role(name)
    return ("Instant" in tl or "Sorcery" in tl) and bool(re.search(r"Counter target", txt))


REMOVAL_RE = re.compile(r"(Destroy target|Exile target (?!card)|deals? \d+ damage to (?:any )?target|"
                        r"deals damage equal to .* to (?:any )?target|target creature gets -\d|"
                        r"Return target (?:nonland )?(?:creature|permanent|artifact|enchantment)[^.]* to its owner's hand)")
WRATH_RE = re.compile(r"(Destroy all|Exile all|All creatures get -|each creature|Return all (?:nonland|creature)|"
                      r"Destroy each|Each player sacrifices all)", re.I)
SELF_OK_RE = re.compile(r"(you control|Return (?:it|that card|the exiled card)|then return|return it|"
                        r"return that|its controller creates|its controller may search)", re.I)


def is_removal(name):
    txt, tl = card_role(name)
    if not ("Instant" in tl or "Sorcery" in tl):
        return False
    return bool(REMOVAL_RE.search(txt))


def is_wrath(name):
    txt, tl = card_role(name)
    if not ("Instant" in tl or "Sorcery" in tl):
        return False
    return bool(WRATH_RE.search(txt)) and "creature" in txt.lower()


def is_generic_tutor(name):
    txt, tl = card_role(name)
    return bool(re.search(r"Search your library for an? (?:card|instant|sorcery|artifact|creature|enchantment|"
                          r"instant or sorcery)[^.]*(?:into your hand|on top|put (?:it|that card) into your hand)", txt))


def cmc_of(name):
    ci = cinfo(name)
    v = ci.get("cmc")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mana_rockish(name):
    txt, tl = card_role(name)
    return ("Artifact" in tl or "Creature" in tl) and "{T}: Add" in txt and "Land" not in tl


def has_flash(name):
    txt, tl = card_role(name)
    return bool(re.search(r"(^|\n)Flash", txt)) or "Instant" in tl


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

    def add(self, pilot, key, k=1, ex=None):
        self.n[(pilot, key)] += k
        if ex is not None and len(self.ex[(pilot, key)]) < 400:
            self.ex[(pilot, key)].append(ex)


def analyse_file(path, acc: Acc, dataset: str, plans_lines=None):
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    meta = None
    pilot = {}
    has_tap = False
    G = None  # game state
    game_idx = None

    def new_game(g):
        return {
            "g": g, "turn_player": None, "turn": 0, "phase": None, "hands": collections.defaultdict(dict),
            "bf": collections.defaultdict(dict), "tapped": {}, "owner_bf": {}, "lands_played": collections.Counter(),
            "life": {}, "alive": set(pilot), "main2_hand": {}, "main_hand": {}, "end_done": set(),
            "attackers": {}, "blocks": collections.defaultdict(list), "combat_dead": set(),
            "pending_ritual": None, "casts_this_step": collections.Counter(), "tutor_pending": {},
            "ended": False, "turn_casts": collections.Counter(), "cmd_casts": collections.Counter(),
            "combat_dmg_player": set(), "phase_seen": set(),
        }

    def P(name):
        return pilot.get(name, "?")

    def untapped_lands(g, p):
        out = []
        for cid, (nm, ty, pt, tok) in g["bf"][p].items():
            if "Land" in ty and not g["tapped"].get(cid, False):
                cs = lcol(nm)
                if cs:
                    out.append(cs)
        return out

    def land_count(g, p):
        return sum(1 for (nm, ty, pt, tok) in g["bf"][p].values() if "Land" in ty)

    def castable_perms(g, p, hand_snapshot):
        lands = untapped_lands(g, p)
        res = []
        for cid, (nm, ty) in g["hands"][p].items():
            if hand_snapshot is not None and cid not in hand_snapshot:
                continue
            if not is_permanent_spell(ty):
                continue
            ci = cinfo(nm)
            tl = ci.get("type_line", "")
            if "Aura" in tl:
                continue
            if has_flash(nm):
                continue
            cost = pips(ci.get("mana_cost"))
            if cost is None or not ci:
                continue
            if payable(cost, lands):
                res.append((nm, ci.get("cmc")))
        return res, len(lands)

    def finish_ritual(g):
        pr = g["pending_ritual"]
        if pr is None:
            return
        caster, name, turn, ph, followed = pr
        acc.add(P(caster), "ritual_cast", 1)
        if not followed:
            acc.add(P(caster), "ritual_wasted", 1, (dataset, os.path.basename(path), g["g"], turn, ph, caster, name))
        g["pending_ritual"] = None

    def end_step_checks(g, p):
        """Called when p's End step begins (first time this turn)."""
        key = (g["turn"], p)
        if key in g["end_done"]:
            return
        g["end_done"].add(key)
        if p not in g["alive"]:
            return
        pl = P(p)
        acc.add(pl, "player_turns", 1)
        hand = g["hands"][p]
        m2 = g["main2_hand"].get(key)
        # missed land drop: a land in hand since main2 began (or since main1), no land played
        lands_in_hand = [nm for cid, (nm, ty) in hand.items() if "Land" in ty and (m2 is None or cid in m2)]
        if g["lands_played"][p] == 0:
            if lands_in_hand:
                acc.add(pl, "missed_land_drop", 1, (dataset, os.path.basename(path), g["g"], g["turn"], p,
                                                   lands_in_hand[:3], land_count(g, p)))
            else:
                acc.add(pl, "no_land_no_drop", 1)
        # unspent mana with castable permanent
        if has_tap:
            res, nl = castable_perms(g, p, m2)
            acc.add(pl, "unspent_lands_sum", nl)
            acc.add(pl, "turns_tapcheck", 1)
            if res:
                inst = [nm for cid, (nm, ty) in hand.items() if has_flash(nm) and "Land" not in ty]
                k = "unspent_castable_perm" + ("_w_instant" if inst else "")
                acc.add(pl, k, 1, (dataset, os.path.basename(path), g["g"], g["turn"], p, nl, res[:3], inst[:2]))
                big = [r for r in res if (r[1] or 0) >= 3]
                if nl >= 3 and big and not inst:
                    acc.add(pl, "unspent3_castable_perm_noinst", 1)

    def cleanup_discard(g, p, cid, nm, ty):
        pl = P(p)
        acc.add(pl, "cleanup_discard", 1)
        if "Land" in ty:
            acc.add(pl, "cleanup_discard_land", 1)
            return
        # castable at end of turn with untapped lands?
        lands = untapped_lands(g, p)
        ci = cinfo(nm)
        cost = pips(ci.get("mana_cost")) if ci else None
        if is_permanent_spell(ty) and "Aura" not in (ci.get("type_line") or "") and cost and payable(cost, lands):
            acc.add(pl, "cleanup_discard_castable_perm", 1, (dataset, os.path.basename(path), g["g"], g["turn"], p, nm, len(lands)))
        land_in_hand = [n for c, (n, t) in g["hands"][p].items() if "Land" in t and c != cid]
        if land_in_hand and land_count(g, p) >= 6:
            acc.add(pl, "cleanup_discard_spell_keep_land", 1, (dataset, os.path.basename(path), g["g"], g["turn"], p, nm, land_in_hand[:2], land_count(g, p)))
        if plans_lines is not None:
            pieces = plans_lines.get(p.split("-", 1)[1] if "-" in p else p, set())
            if nm in pieces:
                acc.add(pl, "cleanup_discard_plan_piece", 1, (dataset, os.path.basename(path), g["g"], g["turn"], p, nm))

    def close_combat(g):
        # attacker died, every blocker survived, attacker was blocked -> died for nothing
        for aid, (ap, an, apt) in g["attackers"].items():
            acc.add(P(ap), "attackers", 1)
            bl = g["blocks"].get(aid, [])
            if not bl:
                continue
            acc.add(P(ap), "attackers_blocked", 1)
            if aid in g["combat_dead"]:
                killed = any(b in g["combat_dead"] for b, bn, bpt in bl)
                if not killed:
                    # predictable? attacker power < every blocker toughness and some blocker power >= attacker toughness
                    a = pt_split(apt)
                    pred = False
                    if a:
                        bs = [pt_split(bpt) for b, bn, bpt in bl]
                        if all(bs):
                            tot_pow = sum(x[0] for x in bs)
                            pred = a[0] < min(x[1] for x in bs) and tot_pow >= a[1]
                    acc.add(P(ap), "attacker_died_for_nothing", 1, (dataset, os.path.basename(path), g["g"], g["turn"], ap, an, apt, [(bn, bpt) for b, bn, bpt in bl]))
                    if pred:
                        acc.add(P(ap), "attacker_died_for_nothing_predictable", 1)
        g["attackers"] = {}
        g["blocks"] = collections.defaultdict(list)
        g["combat_dead"] = set()

    with fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rec = r.get("rec")
            if rec == "meta":
                meta = r
                pilot = dict(zip(meta.get("players", []), meta.get("agents", [])))
                v = meta.get("shim") or "0"
                try:
                    has_tap = tuple(int(x) for x in v.split(".")[:2]) >= (0, 12)
                except ValueError:
                    has_tap = False
                continue
            if meta is None:
                return
            gnum = r.get("game")
            if gnum is not None and (G is None or gnum != G["g"]):
                if G is not None:
                    finish_ritual(G)
                G = new_game(gnum)
                acc.add("all", "games_" + dataset, 1)
                for p in pilot:
                    acc.add(P(p), "seat_games", 1)
            g = G
            if rec == "result":
                continue
            if rec == "tap":
                g["tapped"][r["cardId"]] = bool(r.get("tapped"))
                continue
            if rec == "zone":
                cid = r.get("cardId")
                fr, to = r.get("from"), r.get("to")
                fp, tp = r.get("fromPlayer") or "", r.get("toPlayer") or ""
                nm, ty = r.get("card") or "", r.get("types") or ""
                if fr == "Hand" and fp:
                    g["hands"][fp].pop(cid, None)
                    if to == "Graveyard" and (r.get("phase") == "CLEANUP" or g["phase"] == "cleanup") and fp == g["turn_player"]:
                        cleanup_discard(g, fp, cid, nm, ty)
                if to == "Hand" and tp:
                    g["hands"][tp][cid] = (nm, ty)
                if fr == "Battlefield" and fp:
                    info = g["bf"][fp].pop(cid, None)
                    if g["phase"] in ("fsdamage", "damage"):
                        g["combat_dead"].add(cid)
                if to == "Battlefield" and tp:
                    g["bf"][tp][cid] = (nm, ty, r.get("pt") or "", bool(r.get("token")))
                    if not has_tap:
                        g["tapped"][cid] = False
                if fr == "Command" and to == "Stack" and fp:
                    g["cmd_casts"][fp] += 1
                    acc.add(P(fp), "commander_casts", 1)
                    if g["cmd_casts"][fp] >= 3:
                        acc.add(P(fp), "commander_cast_3plus", 1)
                continue
            if rec != "entry":
                continue
            t = r.get("type")
            msg = (r.get("message") or "").strip()
            if t == "TURN":
                m = TURN_RE.match(msg)
                if m:
                    g["turn"] = int(m.group(1))
                    g["turn_player"] = m.group(2)
                    g["lands_played"] = collections.Counter()
                continue
            if t == "PHASE":
                ph = None
                who = None
                for suf, key in PHASES:
                    if msg.endswith(suf):
                        ph = key
                        who = msg[: -len(suf)].rstrip()
                        if who.endswith("'s"):
                            who = who[:-2]
                        elif who.endswith("'"):
                            who = who[:-1]
                        break
                if ph is None:
                    continue
                if ph != g["phase"]:
                    finish_ritual(g)
                if g["phase"] in ("damage", "fsdamage", "ecombat") and ph not in ("damage", "fsdamage", "ecombat"):
                    close_combat(g)
                elif ph == "ecombat":
                    pass
                g["phase"] = ph
                tp = g["turn_player"]
                if ph == "untap" and not has_tap and tp:
                    for cid in g["bf"][tp]:
                        g["tapped"][cid] = False
                if ph == "main2" and tp:
                    g["main2_hand"][(g["turn"], tp)] = set(g["hands"][tp].keys())
                if ph == "end" and tp:
                    end_step_checks(g, tp)
                continue
            if t == "LAND":
                m = re.match(r"^(Ai\(\d\)-.+?) played ", msg)
                if m:
                    g["lands_played"][m.group(1)] += 1
                continue
            if t == "MANA":
                if not has_tap:
                    m = MANA_RE.search(msg)
                    if m:
                        g["tapped"][int(m.group(1))] = True
                continue
            if t == "LIFE":
                m = LIFE_RE.match(msg)
                if m:
                    g["life"][m.group(1)] = int(m.group(3))
                continue
            if t == "GAME_OUTCOME":
                m = LOST_RE.match(msg)
                if m:
                    p = m.group(1)
                    g["alive"].discard(p)
                    # died holding an instant-speed answer with the mana to cast it
                    lands = untapped_lands(g, p)
                    held = []
                    for cid, (nm, ty) in g["hands"][p].items():
                        if "Land" in ty or not has_flash(nm):
                            continue
                        ci = cinfo(nm)
                        if is_removal(nm) or is_counterspell(nm) or re.search(r"Prevent all combat damage|Fog", ci.get("oracle_text", "")):
                            c = pips(ci.get("mana_cost"))
                            if c and payable(c, lands):
                                held.append(nm)
                    acc.add(P(p), "eliminations", 1)
                    acc.add(P(p), "hand_at_death_sum", len(g["hands"][p]))
                    if held and has_tap:
                        acc.add(P(p), "died_holding_castable_answer", 1, (dataset, os.path.basename(path), g["g"], g["turn"], p, held[:3], len(lands)))
                    if has_tap:
                        acc.add(P(p), "eliminations_tap", 1)
                continue
            if t == "COMBAT":
                for one in msg.split("\n"):
                    one = one.strip()
                    mb = BLK_RE.match(one)
                    if mb:
                        # "D assigned B (id) to block A (id)"
                        bids = [int(x) for x in IDREF.findall(mb.group(2))]
                        aids = [int(x) for x in IDREF.findall(mb.group(3))]
                        for aid in aids:
                            for bid in bids:
                                info = None
                                for pl_ in g["bf"]:
                                    if bid in g["bf"][pl_]:
                                        info = g["bf"][pl_][bid]
                                        break
                                g["blocks"][aid].append((bid, info[0] if info else "?", info[2] if info else ""))
                        continue
                    ma = ATK_RE.match(one)
                    if ma:
                        ap = ma.group(1)
                        for aid in [int(x) for x in IDREF.findall(ma.group(2))]:
                            info = g["bf"][ap].get(aid)
                            g["attackers"][aid] = (ap, info[0] if info else "?", info[2] if info else "")
                continue
            if t == "STACK_ADD":
                m = CAST_RE.match(msg)
                if not m:
                    continue
                caster, verb, card, tgt = m.group(1), m.group(2), m.group(3), m.group(4)
                card = IDREF.sub("", card).strip()
                pl = P(caster)
                pr = g["pending_ritual"]
                if pr is not None and pr[0] == caster and verb in ("cast", "activated"):
                    g["pending_ritual"] = (pr[0], pr[1], pr[2], pr[3], True)
                if verb != "cast":
                    continue
                acc.add(pl, "casts", 1)
                if is_ritual(card):
                    finish_ritual(g)
                    g["pending_ritual"] = (caster, card, g["turn"], g["phase"], False)
                if tgt is not None:
                    tids = [int(x) for x in IDREF.findall(tgt)]
                    own = [cid for cid in tids if cid in g["bf"][caster]]
                    if is_removal(card):
                        acc.add(pl, "removal_targeted", 1)
                        txt = card_role(card)[0]
                        if own and tids and len(own) == len(tids) and not SELF_OK_RE.search(txt):
                            acc.add(pl, "removal_on_own_permanent", 1, (dataset, os.path.basename(path), g["g"], g["turn"], caster, card, [g["bf"][caster][c][0] for c in own]))
                        # minor target while a big threat stands
                        opp_ids = [cid for cid in tids if cid not in g["bf"][caster]]
                        if opp_ids:
                            tgt_pow = []
                            for cid in opp_ids:
                                for pl_ in g["bf"]:
                                    if cid in g["bf"][pl_]:
                                        nm_, ty_, pt_, tok_ = g["bf"][pl_][cid]
                                        ps = pt_split(pt_)
                                        if "Creature" in ty_ and ps:
                                            tgt_pow.append(ps[0])
                            big = 0
                            for pl_ in g["bf"]:
                                if pl_ == caster or pl_ not in g["alive"]:
                                    continue
                                for cid, (nm_, ty_, pt_, tok_) in g["bf"][pl_].items():
                                    ps = pt_split(pt_)
                                    if "Creature" in ty_ and ps:
                                        big = max(big, ps[0])
                            if tgt_pow and max(tgt_pow) <= 2 and big >= 7:
                                acc.add(pl, "removal_small_target_big_threat_standing", 1, (dataset, os.path.basename(path), g["g"], g["turn"], caster, card, tgt, big))
                    if is_counterspell(card):
                        acc.add(pl, "counters_cast", 1)
                        tname = IDREF.sub("", tgt).strip()
                        tci = cinfo(tname)
                        tcmc = tci.get("cmc")
                        chaff = mana_rockish(tname) or ("Land" in (tci.get("type_line") or "")) or \
                            bool(re.search(r"Search your library for (?:a|up to \w+) basic land", tci.get("oracle_text") or ""))
                        if chaff:
                            acc.add(pl, "counter_on_ramp", 1, (dataset, os.path.basename(path), g["g"], g["turn"], caster, card, tname))
                        try:
                            if tcmc is not None and float(tcmc) <= 2:
                                acc.add(pl, "counter_on_cmc_le2", 1)
                        except ValueError:
                            pass
                if is_wrath(card):
                    mine_c = [(pt_split(pt) or (0, 0))[0] for (nm, ty, pt, tok) in g["bf"][caster].values() if "Creature" in ty]
                    opp = {}
                    for pl_ in g["bf"]:
                        if pl_ == caster or pl_ not in g["alive"]:
                            continue
                        opp[pl_] = [(pt_split(pt) or (0, 0))[0] for (nm, ty, pt, tok) in g["bf"][pl_].values() if "Creature" in ty]
                    acc.add(pl, "wraths", 1)
                    max_opp_pow = max((sum(v) for v in opp.values()), default=0)
                    tot_opp_n = sum(len(v) for v in opp.values())
                    if len(mine_c) >= 2 and sum(mine_c) > max_opp_pow:
                        acc.add(pl, "wrath_while_ahead", 1, (dataset, os.path.basename(path), g["g"], g["turn"], caster, card, len(mine_c), sum(mine_c), {k[-18:]: (len(v), sum(v)) for k, v in opp.items()}))
                    if tot_opp_n <= 1:
                        acc.add(pl, "wrath_into_empty", 1, (dataset, os.path.basename(path), g["g"], g["turn"], caster, card, len(mine_c), tot_opp_n))
                continue
    if G is not None:
        finish_ritual(G)


def load_plan_lines(plan_path):
    try:
        d = json.load(open(plan_path, encoding="utf-8"))
    except Exception:
        return None
    out = {}
    plans = d.get("decks") or d.get("plans") or d if isinstance(d, dict) else {}
    for deck, pl in plans.items():
        if not isinstance(pl, dict):
            continue
        s = set()
        for line in pl.get("lines", []) or []:
            if isinstance(line, dict):
                s |= set(line.get("pieces") or line.get("cards") or [])
            elif isinstance(line, list):
                s |= set(line)
        s |= set(pl.get("tutors", []) or [])
        out[deck] = s
    return out


DATASETS = {
    "cedh015": ("studies/agent_viability/runs_015_default/cell_*.jsonl", "studies/agent_viability/runs_015_default/plans_{pod}.json"),
    "cedh016": ("studies/agent_viability/runs_016_engine/cell_*.jsonl", "studies/agent_viability/runs_016_engine/plans_{pod}.json"),
    "precon_agent015": ("studies/precon_predict/runs_agent_015/*.jsonl", None),
    "precon_stock": ("studies/precon_predict/runs_stock/*.jsonl", None),
    "precon_mixed_base": ("studies/behavior_rubric/runs_overnight/base/*.jsonl", None),
    "hc_stock": ("studies/human_ceiling/runs/*.jsonl", None),
    "engine_ab": ("studies/engine_ab/runs/*.jsonl", None),
}

if __name__ == "__main__":
    which = sys.argv[1:] or list(DATASETS)
    out = {}
    for ds in which:
        pat, plan_pat = DATASETS[ds]
        acc = Acc()
        files = sorted(glob.glob(str(REPO / pat)))
        for f in files:
            pl = None
            if plan_pat:
                m = re.search(r"cell_(.+?)_rot", f)
                if m:
                    pl = load_plan_lines(str(REPO / plan_pat.format(pod=m.group(1))))
            analyse_file(f, acc, ds, pl)
        out[ds] = {"n": {f"{k[0]}|{k[1]}": v for k, v in acc.n.items()},
                   "ex": {f"{k[0]}|{k[1]}": v for k, v in acc.ex.items()}}
        print(ds, len(files), "files", file=sys.stderr)
    od = Path(__file__).parent
    json.dump(out, open(od / ("out_" + "_".join(which) + ".json"), "w"), indent=0, default=str)
