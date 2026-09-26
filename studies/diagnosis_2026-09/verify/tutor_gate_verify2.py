"""Independent re-check of tutoring/one-short-gate-closer.

For every plan-seat own turn, snapshot the zones at the END of that turn and
mirror PlanPlayerController.lineOfSight(): hand = hand + command zone;
tutorInHand = any plan.tutors name in hand; for each non-assembled line count
pieces outside (not on my battlefield, not in hand/command).  Classify the
min-outside over lines.

Also: shim tutor_cast events by table round, and ALL plan-seat casts of plan
tutors (Hand/Command -> Stack) by table round, split shim-forced vs stock.
"""
import json, glob, os, sys, collections

ROOT = "C:/Users/Vatto/Magic Rules Engine/studies"
ARMS = {
    "av015": (f"{ROOT}/agent_viability/runs_015_default", "cell_*.jsonl", "plans_{pod}.json"),
    "winmax": (f"{ROOT}/agent_viability/runs_winmax", "cell_*.jsonl", "plans_{pod}.json"),
    "av016": (f"{ROOT}/agent_viability/runs_016_engine", "cell_*.jsonl", "plans_{pod}.json"),
    "rubric_ship": (f"{ROOT}/behavior_rubric/runs_agent_shipping", "*.jsonl", "plans/plans_{pod}.json"),
}


def commanders(dck):
    out, sec = [], None
    try:
        for ln in open(dck, encoding="utf-8"):
            ln = ln.strip()
            if ln.startswith("["):
                sec = ln.lower(); continue
            if sec == "[commander]" and ln:
                parts = ln.split(" ", 1)
                name = parts[1] if len(parts) > 1 and parts[0].isdigit() else ln
                out.append(name.split("|")[0].strip())
    except OSError:
        pass
    return out


def pod_of(fname):
    b = os.path.basename(fname)
    b = b[5:] if b.startswith("cell_") else b
    return b.rsplit("_rot", 1)[0]


def rnd_for(turn_owner, t):
    cnt = collections.Counter()
    for tt in sorted(turn_owner):
        if tt > t: break
        cnt[turn_owner[tt]] += 1
    return max(cnt.values()) if cnt else 0


def analyze(arm, cmd_init=True, tutor_from_cmd=True):
    d, pat, ppat = ARMS[arm]
    held = collections.Counter(); held_early = collections.Counter()
    held_by_round = collections.defaultdict(collections.Counter)
    tc_round = collections.Counter(); allcast_round = collections.Counter()
    shimcast_round = collections.Counter()
    alltc = 0; n_games = 0; n_ownturns = 0
    tcast_detail = collections.Counter()
    for f in sorted(glob.glob(os.path.join(d, pat))):
        pod = pod_of(f)
        plans = json.load(open(os.path.join(d, ppat.format(pod=pod)), encoding="utf-8"))["decks"]
        games = collections.defaultdict(list)
        meta = None
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("rec") == "meta":
                meta = r; continue
            if "game" in r:
                games[r["game"]].append(r)
        players = meta["players"]; agents = meta["agents"]
        planseats = [p for p, a in zip(players, agents) if a == "plan"]
        deckkey = {p: p.split("-", 1)[1] for p in players}
        cmdr = {p: commanders(dk) for p, dk in zip(players, meta["decks"])}
        for g, recs in games.items():
            if not any(r.get("rec") == "result" for r in recs):
                continue  # unfinished game
            n_games += 1
            turn_owner = {}
            for r in recs:
                if r.get("rec") == "entry" and r["type"] == "TURN":
                    m = r["message"]  # Turn 12 (Ai(1)-derevi)
                    t = int(m.split()[1]); who = m[m.index("(") + 1:-1]
                    turn_owner[t] = who
            # table round per turn
            cnt = collections.Counter(); round_of = {}
            for t in sorted(turn_owner):
                cnt[turn_owner[t]] += 1
                round_of[t] = max(cnt.values())
            own_idx = {}
            c2 = collections.Counter()
            for t in sorted(turn_owner):
                c2[turn_owner[t]] += 1
                own_idx[t] = c2[turn_owner[t]]
            state = {p: {"hand": {}, "bf": {}, "cmd": collections.Counter(cmdr[p] if cmd_init else [])} for p in planseats}
            pending = sorted(t for t, w in turn_owner.items() if w in planseats)
            pi = 0

            def snap(T):
                nonlocal n_ownturns
                p = turn_owner[T]; pl = plans[deckkey[p]]
                st = state[p]
                board = set(st["bf"].values())
                hand = set(st["hand"].values()) | {n for n, c in st["cmd"].items() if c > 0}
                tutors = set(pl["tutors"])
                n_ownturns += 1
                handonly = set(st["hand"].values())
                if not ((hand if tutor_from_cmd else handonly) & tutors):
                    return
                lines = [set(l["cards"]) for l in pl["lines"] if l.get("cards")]
                best = None
                for line in lines:
                    onb = line & board
                    if len(onb) == len(line):
                        continue
                    outside = [x for x in line if x not in board and x not in hand]
                    if best is None or len(outside) < best:
                        best = len(outside)
                if not lines:
                    cat = "nolines"
                elif best is None:
                    cat = "all_assembled"
                else:
                    cat = {0: "0_owned", 1: "1_short", 2: "2_short"}.get(best, "3plus_short")
                held[cat] += 1
                rd = own_idx[T]
                held_by_round[min(rd, 12)][cat] += 1
                if rd <= 4:
                    held_early[cat] += 1

            for r in recs:
                t = r.get("turn")
                if t is None:
                    continue
                while pi < len(pending) and pending[pi] < t:
                    snap(pending[pi]); pi += 1
                if r.get("rec") == "zone":
                    cid = r["cardId"]; name = r["card"]
                    fp, tp = r.get("fromPlayer"), r.get("toPlayer")
                    for p in planseats:
                        st = state[p]
                        if r["from"] == "Hand":
                            st["hand"].pop(cid, None)
                        if r["from"] == "Battlefield":
                            st["bf"].pop(cid, None)
                        if r["from"] == "Command" and fp == p and st["cmd"][name] > 0 and name in cmdr[p]:
                            st["cmd"][name] -= 1
                    if r["to"] == "Hand" and tp in state:
                        state[tp]["hand"][cid] = name
                    if r["to"] == "Battlefield" and tp in state:
                        state[tp]["bf"][cid] = name
                    if r["to"] == "Command" and tp in state and name in cmdr[tp]:
                        state[tp]["cmd"][name] += 1
                    # all plan-tutor casts by plan seats
                    if r["to"] == "Stack" and r["from"] in ("Hand", "Command") and fp in state:
                        if name in set(plans[deckkey[fp]]["tutors"]):
                            allcast_round[min(round_of.get(t, 0), 12)] += 1
                            alltc += 1
                elif r.get("rec") == "agent" and r.get("event") == "tutor_cast" and r.get("player") in state:
                    tc_round[min(round_of.get(t, 0), 12)] += 1
                    tcast_detail[r["detail"].split(" seeking ")[0]] += 1
            while pi < len(pending):
                snap(pending[pi]); pi += 1
    return dict(held=held, held_early=held_early, held_by_round=held_by_round, tc_round=tc_round,
                allcast_round=allcast_round, alltc=alltc, n_games=n_games, n_ownturns=n_ownturns,
                tcast_detail=tcast_detail)


def pct(a, b):
    return f"{a}/{b} ({100*a/b:.0f}%)" if b else f"{a}/0"


if __name__ == "__main__":
    import itertools
    variants={"A_shim_mirror":(True,True),"B_their_def":(False,False),"C_hand_tutor_cmdr_owned":(True,False)}
    for (vn,(ci,tc)),arm in itertools.product(variants.items(), ARMS):
        res = analyze(arm, ci, tc); arm=vn+":"+arm
        H = res["held"]; tot = sum(H.values()); E = res["held_early"]; te = sum(E.values())
        print(f"== {arm}: games={res['n_games']} plan own turns={res['n_ownturns']} held-tutor turns={tot}")
        for k in sorted(H):
            print(f"   {k:14s} all {pct(H[k], tot):18s} rounds1-4 {pct(E.get(k, 0), te)}")
        tc = res["tc_round"]; nt = sum(tc.values())
        late = sum(v for k, v in tc.items() if k >= 8)
        early = sum(v for k, v in tc.items() if 1 <= k <= 4)
        print(f"   shim tutor_cast n={nt}  rounds1-4 {pct(early, nt)}  round8+ {pct(late, nt)}  hist={dict(sorted(tc.items()))}")
        ac = res["allcast_round"]; na = sum(ac.values())
        late = sum(v for k, v in ac.items() if k >= 8)
        early = sum(v for k, v in ac.items() if 1 <= k <= 4)
        print(f"   ALL plan-tutor casts (hand/cmd->stack) n={na} rounds1-4 {pct(early, na)} round8+ {pct(late, na)} hist={dict(sorted(ac.items()))}")
        print("   held by own-turn round:")
        for rd in sorted(res["held_by_round"]):
            c = res["held_by_round"][rd]; s = sum(c.values())
            print(f"     r{rd:2d} n={s:3d} " + " ".join(f"{k}={c[k]}" for k in sorted(c)))
