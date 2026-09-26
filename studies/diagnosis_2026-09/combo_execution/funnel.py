"""Combo-execution funnel from raw shim JSONL.

For every (game, seat, line) it reconstructs the seat's Hand / Command /
Battlefield from zone records (cardId-keyed, both directions) and classifies:

  S0 never_sighted     line never met the shim's lineOfSight gate
  S1 sighted_no_cast   gate met, but no line piece moved to Stack/Battlefield after
  S2 cast_not_assembled pieces cast, never all together (permanent pieces all on
                        battlefield AND every instant/sorcery piece cast while they were)
  S3 assembled_no_win  assembled, seat did not win within its next 2 own turns
  S4 assembled_won     assembled and won within 2 own turns

Per seat-game the funnel stage is the max across the deck's lines.
Stock seats get the same zone-only classification (sighting is hypothetical:
"the shim's gate would have been open").

Also records: activations ("activated X") of line pieces after assembly,
agent events per stage, win method, and Thassa's Oracle sequencing.
"""
import collections, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from forge_cards import load, facts  # noqa
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos  # noqa

IDX = load()
_perm_cache = {}


def is_perm(name):
    if name not in _perm_cache:
        f = facts(IDX, name)
        _perm_cache[name] = True if f is None else f["permanent"]
    return _perm_cache[name]


TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)$")
CAST_RE = re.compile(r"^(Ai\(\d\)-\S+) (cast|activated) (.+?)(?: targeting .*)?$")


def load_plans(path):
    d = json.load(open(path, encoding="utf-8"))["decks"]
    out = {}
    for name, p in d.items():
        lines = []
        seen = set()
        for ln in p.get("lines", []):
            key = tuple(sorted(ln["cards"]))
            if key in seen:
                continue
            seen.add(key)
            lines.append({"cards": list(ln["cards"]), "produces": ln.get("produces", [])})
        out[name] = {"lines": lines, "tutors": set(p.get("tutors", []))}
    return out


def deck_of(player):
    return player.split("-", 1)[1] if "-" in player else player


def analyze_file(path, plans, arm):
    recs_by_game = collections.defaultdict(list)
    meta = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("rec") == "meta":
                meta = r
                continue
            g = r.get("game")
            if g is None:
                continue
            recs_by_game[g].append(r)
    if meta is None:
        return []
    agents = dict(zip(meta["players"], meta["agents"]))
    commanders = {}
    for p, dpath in zip(meta["players"], meta.get("decks", [])):
        try:
            _, cmd = combos.parse_dck(open(dpath, encoding="utf-8").read())
        except Exception:
            cmd = []
        commanders[p] = cmd
    out = []
    for g, recs in sorted(recs_by_game.items()):
        out.extend(analyze_game(path, arm, g, recs, meta["players"], agents, plans, commanders))
    return out


def analyze_game(path, arm, g, recs, players, agents, plans, commanders=None):
    loc = {}  # cardId -> (player, zone, name)
    zones = {p: collections.defaultdict(collections.Counter) for p in players}
    # the commander's initial placement is not always logged: seed it
    for p in players:
        for c in (commanders or {}).get(p, []):
            zones[p]["Command"][c] = 1
    turn_owner = {}
    own_turns = {p: [] for p in players}
    result = None
    outcomes = []
    agent_ev = collections.defaultdict(list)
    # per seat, per line index state
    st = {}
    for p in players:
        plan = plans.get(deck_of(p))
        if not plan:
            continue
        for i, ln in enumerate(plan["lines"]):
            st[(p, i)] = {"sighted": None, "cast_after_sight": None, "assembled": None,
                          "nonperm_cast": {}, "acts_after": collections.Counter(),
                          "first_all_owned": None}
    cur_turn = 0
    oracle_seq = collections.defaultdict(list)
    acts_all = collections.Counter()

    def names(p, z):
        return zones[p][z]

    def check(p, t, trigger_evt=None):
        plan = plans.get(deck_of(p))
        if not plan:
            return
        bf, hand, cmd = names(p, "Battlefield"), names(p, "Hand"), names(p, "Command")
        # mirror the shim: command-zone cards join "hand" BEFORE the tutor check
        tutor_in_hand = any(hand[x] > 0 or cmd[x] > 0 for x in plan["tutors"])
        for i, ln in enumerate(plan["lines"]):
            s = st[(p, i)]
            cards = ln["cards"]
            perm = [c for c in cards if is_perm(c)]
            nonperm = [c for c in cards if not is_perm(c)]
            onb = [c for c in cards if bf[c] > 0]
            owned = [c for c in cards if bf[c] == 0 and (hand[c] > 0 or cmd[c] > 0)]
            outside = [c for c in cards if c not in onb and c not in owned]
            if len(onb) < len(cards):
                clear = (not outside) or (len(outside) == 1 and tutor_in_hand)
                if clear and s["sighted"] is None:
                    s["sighted"] = t
                if not outside and s["first_all_owned"] is None:
                    s["first_all_owned"] = t
            # assembled: every permanent piece on bf and every nonpermanent piece
            # cast this turn while those were on bf
            if s["assembled"] is None and all(bf[c] > 0 for c in perm):
                if all(s["nonperm_cast"].get(c) == t for c in nonperm):
                    s["assembled"] = t

    # Entries are dumped as one block per game BEFORE the chronological
    # zone/agent records, and carry no turn: derive each entry's turn from the
    # TURN lines inside the block, and drive state from zone records only.
    entry_turn = 0
    acts_list = []   # (turn, player, card)
    for r in recs:
        if r.get("rec") != "entry":
            continue
        m = r.get("message", "")
        if r.get("type") == "TURN":
            mt = TURN_RE.match(m)
            if mt:
                entry_turn = int(mt.group(1))
                turn_owner[entry_turn] = mt.group(2)
                if mt.group(2) in own_turns:
                    own_turns[mt.group(2)].append(entry_turn)
        elif r.get("type") == "STACK_ADD":
            mc = CAST_RE.match(m)
            if mc:
                p, verb, card = mc.group(1), mc.group(2), r.get("card") or mc.group(3)
                if verb == "activated":
                    acts_all[(p, card)] += 1
                    acts_list.append((entry_turn, p, card))
                if card in ("Thassa's Oracle", "Demonic Consultation", "Tainted Pact"):
                    oracle_seq[p].append((entry_turn, verb, card, r.get("seq")))
        elif r.get("type") == "GAME_OUTCOME":
            outcomes.append(m)
    cur_turn = 0
    for r in recs:
        rt = r.get("rec")
        if rt == "zone":
            cid = r.get("cardId")
            to, frm = r.get("to"), r.get("from")
            name = r.get("card")
            t = r.get("turn") or cur_turn
            cur_turn = t
            old = loc.get(cid)
            if old is not None:
                op, oz, on = old
                if op in zones and zones[op][oz][on] > 0:
                    zones[op][oz][on] -= 1
            elif frm == "Command" and r.get("fromPlayer") in zones:
                fp = r.get("fromPlayer")
                if zones[fp]["Command"][name] > 0:
                    zones[fp]["Command"][name] -= 1
            tp = r.get("toPlayer")
            if tp in zones and to:
                zones[tp][to][name] += 1
                loc[cid] = (tp, to, name)
            else:
                loc.pop(cid, None)
            if name == "Thassa's Oracle" and to == "Battlefield":
                oracle_seq[tp].append((t, "ETB", name, None))
            is_cast = (to == "Stack" and frm in ("Hand", "Command", "Exile", "Graveyard", "Library"))
            # Stack moves carry toPlayer "" -- the caster is the fromPlayer
            actor = tp if tp in zones else r.get("fromPlayer")
            if actor in zones and (to == "Battlefield" or is_cast):
                for (pp, i), s in st.items():
                    if pp != actor:
                        continue
                    ln = plans[deck_of(actor)]["lines"][i]
                    if name not in ln["cards"]:
                        continue
                    if s["sighted"] is not None and s["cast_after_sight"] is None:
                        s["cast_after_sight"] = t
                    if is_cast and not is_perm(name):
                        s["nonperm_cast"][name] = t
            for p in {tp, actor, old[0] if old else None}:
                if p in zones:
                    check(p, t)
        elif rt == "agent":
            agent_ev[r.get("player")].append((r.get("turn"), r.get("event"), r.get("detail", "")))
        elif rt == "result":
            result = r
    # activations of a line's pieces on or after the assembly turn
    for (p, i), s in st.items():
        if s["assembled"] is None:
            continue
        ln = plans[deck_of(p)]["lines"][i]
        for (t, pp, card) in acts_list:
            if pp == p and card in ln["cards"] and t >= s["assembled"]:
                s["acts_after"][card] += 1
    if result is None:
        return []
    winner = result.get("winner")
    final_turn = result.get("turns") or cur_turn
    method = "none"
    for m in outcomes:
        if "won due to effect of" in m or "won by spell" in m:
            method = "spell:" + m.split("'")[1] if "'" in m else "spell"
            break
    if method == "none" and winner:
        losses = [m for m in outcomes if "has lost" in m]
        if losses and all("life total" in m for m in losses):
            method = "life"
        elif losses:
            method = "mixed:" + ";".join(sorted({re.sub(r"Ai\(\d\)-\S+ ", "", x)[:40] for x in losses}))
    rows = []
    for p in players:
        plan = plans.get(deck_of(p))
        if not plan:
            continue
        won = (winner == p)
        best = None
        per_line = []
        for i, ln in enumerate(plan["lines"]):
            s = st[(p, i)]
            if s["assembled"] is not None:
                later_own = [t for t in own_turns[p] if t > s["assembled"]]
                if won:
                    # own turns begun after assembly up to game end
                    n_after = len([t for t in later_own if t <= final_turn])
                    stage = 4 if n_after <= 2 else 3
                else:
                    stage = 3
            elif s["cast_after_sight"] is not None:
                stage = 2
            elif s["sighted"] is not None:
                stage = 1
            else:
                stage = 0
            per_line.append({"line": " + ".join(ln["cards"]), "stage": stage,
                             "sighted": s["sighted"], "cast": s["cast_after_sight"],
                             "assembled": s["assembled"], "acts_after": dict(s["acts_after"]),
                             "produces": ln["produces"][:3]})
            if best is None or stage > best["stage"] or (
                    stage == best["stage"] and (s["assembled"] or 999) < (best["assembled"] or 999)):
                best = per_line[-1]
        acts = {c: n for (pp, c), n in acts_all.items() if pp == p}
        rows.append({
            "file": os.path.relpath(path, r"C:/Users/Vatto/Magic Rules Engine/studies").replace("\\", "/"),
            "arm": arm, "game": g, "seat": p, "agent": agents.get(p),
            "won": won, "winner": winner, "method": method, "final_turn": final_turn,
            "timedOut": result.get("timedOut"), "turnCapped": result.get("turnCapped"),
            "n_lines": len(plan["lines"]), "stage": best["stage"] if best else -1,
            "best": best, "lines": per_line,
            "own_turns": own_turns[p], "acts": acts,
            "agent_events": collections.Counter(e[1] for e in agent_ev.get(p, [])),
            "combo_events": [e for e in agent_ev.get(p, []) if e[1] in
                             ("combo_cast", "combo_hold", "tutor_cast", "tutor_steer")],
            "oracle_seq": oracle_seq.get(p, []),
        })
    return rows


RUNSETS = {
    # arm: (glob of jsonl, plans resolver)
    "av_015_default": ("agent_viability/runs_015_default/cell_*.jsonl", "pod_plans_in_dir"),
    "av_winmax": ("agent_viability/runs_winmax/cell_*.jsonl", "pod_plans_in_dir"),
    "av_016_engine": ("agent_viability/runs_016_engine/cell_*.jsonl", "pod_plans_in_dir"),
    "br_agent_shipping": ("behavior_rubric/runs_agent_shipping/*.jsonl", "br_plans"),
    "tt_stage2": ("tutor_targeting/runs_stage2/*.jsonl", "tt_plans"),
    "hc_stock": ("human_ceiling/runs/*.jsonl", "br_plans"),
}
STUDIES = r"C:/Users/Vatto/Magic Rules Engine/studies"


def plans_for(path, mode):
    pod = None
    base = os.path.basename(path)
    for pd in ["2iA_Jt0d6sM", "5A6o18Bra0Y", "B421mac67IE", "Bq-nFi0f1jA", "CxKMqO36DdM",
               "OuY6mdiXbHU", "n7WpsqsZtdQ", "sZA0KqXCGrY"]:
        if pd in base:
            pod = pd
    if mode == "pod_plans_in_dir":
        return os.path.join(os.path.dirname(path), f"plans_{pod}.json")
    if mode == "br_plans":
        return os.path.join(STUDIES, "behavior_rubric/runs_agent_shipping/plans", f"plans_{pod}.json")
    if mode == "tt_plans":
        return os.path.join(STUDIES, "tutor_targeting/runs_stage2/plans_20260825_175454_pid81260.json")


def main():
    arms = sys.argv[1:] or list(RUNSETS)
    allrows = []
    for arm in arms:
        pat, mode = RUNSETS[arm]
        files = sorted(glob.glob(os.path.join(STUDIES, pat)))
        n = 0
        for fp in files:
            pp = plans_for(fp, mode)
            if not pp or not os.path.exists(pp):
                print("no plans for", fp, pp, file=sys.stderr)
                continue
            plans = load_plans(pp)
            rows = analyze_file(fp, plans, arm)
            allrows.extend(rows)
            n += len(rows)
        print(arm, "files", len(files), "seat-games", n, file=sys.stderr)
    out = os.path.join(HERE, "funnel_rows.json")
    json.dump(allrows, open(out, "w", encoding="utf-8"), default=list)
    print("wrote", out, len(allrows), file=sys.stderr)


if __name__ == "__main__":
    main()
