"""Does a commander in the command zone open the one-piece-short gate?
Replays zone records to rebuild the plan seat's hand/board/command at each
combo_cast / tutor_cast, then re-evaluates lineOfSight with and without the
command zone counting toward tutorInHand."""
import json, glob, os, collections, re
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
DIRS = ["agent_viability/runs_015_default", "agent_viability/runs_winmax", "agent_viability/runs_016_engine"]


def sight(plan, board, hand, command, cmd_tutor=True):
    h = set(hand) | set(command)
    tset = set(hand) | (set(command) if cmd_tutor else set())
    tutor_in = any(t in tset for t in plan["tutors"])
    best = None
    bo, bt = 99, 99
    for ln in plan["lines"]:
        cards = ln["cards"]
        on = [c for c in cards if c in board]
        own = [c for c in cards if c not in board and c in h]
        out = [c for c in cards if c not in board and c not in h]
        if len(on) == len(cards):
            continue
        if not (len(out) == 0 or (len(out) == 1 and tutor_in)):
            continue
        tc = len(cards) - len(on)
        if len(out) < bo or (len(out) == bo and tc < bt):
            best = (tuple(cards), tuple(out))
            bo, bt = len(out), tc
    return best


res = collections.Counter()
early = collections.defaultdict(dict)  # (dir,deck) -> game -> earliest turn of combo/tutor event
early_ss = collections.defaultdict(dict)
examples = []
for d in DIRS:
    for deck, cell in (("godo_archetype", "cell_2iA_Jt0d6sM_rot1.jsonl"), ("magda", "cell_n7WpsqsZtdQ_rot0.jsonl")):
        pod = "2iA_Jt0d6sM" if "2iA" in cell else "n7WpsqsZtdQ"
        plan = json.load(open(S + d + "/plans_" + pod + ".json", encoding="utf-8"))["decks"][deck]
        commander = "Godo, Bandit Warlord" if deck.startswith("godo") else "Magda, Brazen Outlaw"
        assert commander in plan["tutors"], (d, deck)
        zones = collections.defaultdict(list)
        agents = collections.defaultdict(list)
        me = None
        for l in open(S + d + "/" + cell, encoding="utf-8"):
            r = json.loads(l)
            if r.get("rec") == "meta":
                me = [p for p, a in zip(r["players"], r["agents"]) if a == "plan"][0]
            elif r.get("rec") == "zone":
                zones[r["game"]].append(r)
            elif r.get("rec") == "agent":
                agents[r["game"]].append(r)
        for g in sorted(set(zones) | set(agents)):
            zs = zones[g]
            ev = [a for a in agents[g] if a["player"] == me and a["event"] in ("combo_cast", "tutor_cast", "combo_hold")]
            if ev:
                early[(d, deck)][g] = min(a["turn"] for a in ev)
            ssv = [a for a in agents[g] if a["player"] == me and a["event"] == "search_seen" and "sighted=true" in a["detail"]]
            if ssv:
                early_ss[(d, deck)][g] = min(a["turn"] for a in ssv)
            for a in ev:
                if a["event"] != "combo_cast":
                    continue
                t = a["turn"]
                piece = re.sub(r" \(\d+/\d+ online\)$", "", a["detail"])
                cut = next((i for i, z in enumerate(zs) if z.get("turn") == t and z["card"] == piece
                            and z["from"] == "Hand" and z.get("fromPlayer") == me), None)
                if cut is None:
                    cut = next((i for i, z in enumerate(zs) if (z.get("turn") or 0) > t), len(zs))
                state = {}
                for z in zs[:cut]:
                    if z.get("token"):
                        continue
                    state[z["cardId"]] = (z["to"], z.get("toPlayer"), z["card"])
                board = {n for (zn, p, n) in state.values() if zn == "Battlefield" and p == me}
                hand = {n for (zn, p, n) in state.values() if zn == "Hand" and p == me}
                seen_ids = {z["cardId"] for z in zs[:cut]}
                command = {n for (zn, p, n) in state.values() if zn == "Command" and p == me}
                # a commander that never moved yet is still in the command zone
                if not any(z["card"] == commander and z.get("fromPlayer") == me for z in zs[:cut]):
                    command.add(commander)
                with_c = sight(plan, board, hand, command, True)
                without = sight(plan, board, hand, command, False)
                key = ("gate open (replica)" if with_c else "gate closed in replica (hand reconstruction off)",
                       "needs commander-as-tutor" if with_c and not without else "open without commander" if without else "-")
                res[(deck,) + key] += 1
                if with_c and not without and len(examples) < 12:
                    examples.append((d.split("/")[1], deck, g, t, a["detail"], "line=", with_c[0], "outside=", with_c[1],
                                     "cmdzone=", sorted(command)))

for k, v in sorted(res.items()):
    print(v, k)
print()
for k, gm in early.items():
    n = 16
    le4 = sum(1 for t in gm.values() if t <= 4)
    le8 = sum(1 for t in gm.values() if t <= 8)
    print(k, "games with combo/tutor event:", len(gm), "/16; first event turn<=4:", le4, " <=8:", le8,
          " median first turn:", sorted(gm.values())[len(gm) // 2] if gm else None)
for k, gm in early_ss.items():
    print(k, "search_seen sighted=true games:", len(gm), " first<=4:", sum(1 for t in gm.values() if t <= 4))
print()
for e in examples:
    print(e)
