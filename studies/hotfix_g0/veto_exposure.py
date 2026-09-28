"""POST HOC (written after the G0a read, not pre-registered).

How often did each arm deal the state the early-burn veto needs?

The veto fires only when a plan seat holds a one-shot (instant or sorcery)
line piece in hand while every other piece of that line is in hand, on the
battlefield or in the command zone, and the line is not already assembled.
This counts, per arm, the games and seat-turns in which that state existed
at any point (a necessary condition, read from the shim's zone records), so
0 vetoes in arm C can be told apart as "never dealt" or "dealt and skipped".
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_g0a as R  # noqa: E402  (same $G0A_OUT as the runner)
OUT = R.OUT
SEAT = re.compile(r"^Ai\((\d+)\)-")
ONE_SHOT = ("Instant", "Sorcery")


def bare(p):
    return SEAT.sub("", p or "").strip()


def plan_lines(bed):
    plans = json.loads((OUT / f"plans_{bed}_v1.json").read_text(encoding="utf-8"))["decks"]
    return {name: [set(l["cards"]) for l in p.get("lines", []) if len(l.get("cards", [])) >= 2]
            for name, p in plans.items()}


def scan(arm):
    exposed_games, exposed_turns, veto_games, vetoes, games = set(), set(), set(), 0, 0
    by_line = defaultdict(lambda: [0, 0])  # line label -> [exposed games, veto games]
    for path in sorted((OUT / "runs" / arm).glob("*_rot*.jsonl")):
        bed = path.name.split("_rot")[0]
        lines = plan_lines(bed)
        zones = defaultdict(dict)       # (game, player) -> {cardId: (name, zone, types)}
        seen_games = set()
        game_exposed = defaultdict(set)  # game -> labels
        game_veto = defaultdict(set)
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.startswith("{"):
                continue
            try:
                r = json.loads(raw)
            except ValueError:
                continue
            g = r.get("game")
            if r.get("rec") == "result":
                seen_games.add(g)
            if r.get("rec") == "agent" and r.get("event") == "combo_hold" and "early burn" in (r.get("detail") or ""):
                vetoes += 1
                piece = r["detail"].split(" kept for the line")[0]
                for ln in lines.get(bare(r["player"]), []):
                    if piece in ln:
                        game_veto[g].add(" + ".join(sorted(ln)))
                veto_games.add((path.name, g))
            if r.get("rec") != "zone":
                continue
            # owner of the card after the move (fall back to before)
            owner = r.get("toPlayer") or r.get("fromPlayer")
            prev = r.get("fromPlayer")
            cid = r.get("cardId")
            if prev and prev != owner:
                zones[(g, prev)].pop(cid, None)
            zones[(g, owner)][cid] = (r.get("card"), r.get("to"), r.get("types") or "")
            st = zones[(g, owner)]
            deck = bare(owner)
            for ln in lines.get(deck, []):
                where = defaultdict(set)
                one_shot = {}
                for _, (name, z, types) in st.items():
                    if name in ln:
                        where[name].add(z)
                        if any(t in types for t in ONE_SHOT):
                            one_shot[name] = True
                have = all(where[p] & {"Hand", "Battlefield", "Command"} for p in ln)
                assembled = all("Battlefield" in where[p] for p in ln)
                shot_in_hand = any("Hand" in where[p] for p in one_shot)
                if have and not assembled and shot_in_hand:
                    label = " + ".join(sorted(ln))
                    game_exposed[g].add(label)
                    exposed_turns.add((path.name, g, owner, r.get("turn")))
        for g in seen_games:
            games += 1
            if game_exposed.get(g):
                exposed_games.add((path.name, g))
            for label in game_exposed.get(g, ()):
                by_line[label][0] += 1
            for label in game_veto.get(g, ()):
                by_line[label][1] += 1
    return {"games": games, "exposed_games": len(exposed_games), "exposed_seat_turns": len(exposed_turns),
            "veto_games": len(veto_games), "vetoes": vetoes,
            "by_line": {k: v for k, v in sorted(by_line.items(), key=lambda kv: -kv[1][0])}}


if __name__ == "__main__":
    for arm in sys.argv[1:] or ["C", "Z", "T"]:
        s = scan(arm)
        print(f"{arm}: games={s['games']} exposed_games={s['exposed_games']} exposed_seat_turns={s['exposed_seat_turns']} "
              f"veto_games={s['veto_games']} vetoes={s['vetoes']}")
        for k, (e, v) in list(s["by_line"].items())[:8]:
            print(f"    {e:3d} exposed / {v} vetoed  {k}")
