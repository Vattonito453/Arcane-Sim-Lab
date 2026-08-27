#!/usr/bin/env python3
"""How does stock Forge's play differ from human play? All axes, not just one.

Blocking was the obvious divergence and it is not the only one. This walks the
typed log in sequence, reconstructing whose turn it is and which step we are
in, and measures every behavioural axis the log can support:

  1 blocking          what fraction of attackers get blocked
  2 attack spread     how many opponents an attack declaration hits
  3 instant timing    are instants held for an opponent's turn, or dumped on
                      your own main phase like a sorcery?
  4 off-turn action   what share of ALL spells are cast on someone else's turn
  5 hand dumping      discards at cleanup, i.e. cards held past usefulness
  6 land drops        missed land drops per player-turn
  7 removal timing    is removal cast at instant speed or jammed on main
  8 game shape        turns, eliminations, how one-sided games are

Card types come from the local Scryfall cache, so a cast is classified by what
it actually is rather than by guessing from the name.
"""
from __future__ import annotations
import collections, glob, json, os, re, statistics as st, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "engine"))
import cards  # noqa: E402

# GREEDY and end-anchored: a player name is "Ai(1)-Deck Name", so a
# non-greedy group stops at the ")" inside "Ai(1)" and truncates the name to
# "Ai(1". That is the CLAUDE.md gotcha about Ai(n)- looking like Forge's
# (123) instance-id syntax, and it made every cast look off-turn.
TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)\s*$")
PHASE_RE = re.compile(r"^(.+?)'s (.+?) step|^(.+?)'s (.+)$")
CAST_RE = re.compile(r"^(.+?) cast (.+?)(?: targeting .*)?\.?$")
TO_ATTACK = re.compile(r"assigned (.+?) to attack (.+?)\.?$")
TO_BLOCK = re.compile(r"assigned (.+?) to block (.+?)\.?$")
NOBLOCK = re.compile(r"didn't block (.+?)\.?$")
LAND_RE = re.compile(r"^(.+?) played (.+?)\.?$")
DISCARD_RE = re.compile(r"^(.+?) discards (.+?)\.?$")
REF = re.compile(r"\s*\(\d+\)\s*$")


def clean(s):
    return REF.sub("", (s or "").strip()).strip()


_TYPES = {}


def load_types(names):
    """ONE batched lookup for the whole corpus. Looping single lookups is the
    anti-pattern CLAUDE.md calls out, and it silently returned nothing here."""
    todo = sorted({n for n in names if n not in _TYPES})
    for i in range(0, len(todo), 200):
        chunk = todo[i:i + 200]
        got = cards.get_many(chunk, fetch=False)
        for n in chunk:
            d = got.get(cards.key(n)) or got.get(n) or {}
            _TYPES[n] = d.get("type_line") or ""


def is_type(name, *want):
    tl = _TYPES.get(name, "")
    return any(w in tl for w in want), tl


def analyse(patterns, label):
    files = []
    for p in patterns:
        files.extend(glob.glob(p, recursive=True))
    st_ = collections.Counter()
    casts = []          # (caster, card, own_turn, step)
    defenders_per_decl = []
    lands_by_turn = collections.Counter()
    turns_seen = collections.Counter()
    game_turns = []
    for f in files:
        cur_turn_player, cur_step, cur_turn = None, None, 0
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                rec = r.get("rec")
                if rec == "result":
                    game_turns.append(r.get("turns") or 0)
                    continue
                if rec != "entry":
                    continue
                t, msg = r.get("type"), (r.get("message") or "")
                if t == "TURN":
                    m = TURN_RE.match(msg)
                    if m:
                        cur_turn = int(m.group(1))
                        cur_turn_player = clean(m.group(2))
                        turns_seen[(f, cur_turn_player, cur_turn)] += 1
                elif t == "PHASE":
                    low = msg.lower()
                    for k in ("upkeep", "draw", "main", "combat", "end", "cleanup",
                              "untap", "declare attackers", "declare blockers"):
                        if k in low:
                            cur_step = k
                            break
                elif t == "STACK_ADD":
                    m = CAST_RE.match(msg.strip())
                    if m:
                        caster = clean(m.group(1))
                        card = clean(m.group(2))
                        casts.append((caster, card, caster == cur_turn_player,
                                      cur_step or "?"))
                elif t == "LAND":
                    m = LAND_RE.match(msg.strip())
                    if m:
                        lands_by_turn[(f, clean(m.group(1)), cur_turn)] += 1
                elif t == "DISCARD":
                    if cur_step == "cleanup":
                        st_["cleanup_discards"] += 1
                    st_["discards"] += 1
                elif t == "COMBAT":
                    for one in msg.split("\n"):
                        one = one.strip()
                        if not one:
                            continue
                        m = TO_BLOCK.search(one)
                        if m:
                            st_["blocked"] += 1
                            continue
                        if NOBLOCK.search(one):
                            st_["unblocked"] += 1
                            continue
                        m = TO_ATTACK.search(one)
                        if m:
                            st_["attack_decls"] += 1
                            defenders_per_decl.append(1)
    load_types([c[1] for c in casts])

    # ---- report
    print("=" * 74)
    print(f"{label}   ({len(files)} files, {len(game_turns)} games)")
    print("=" * 74)
    dec = st_["blocked"] + st_["unblocked"]
    if dec:
        print(f"1 BLOCKING          {100*st_['blocked']/dec:5.1f}% of attackers blocked "
              f"({st_['blocked']}/{dec})")
    inst = [c for c in casts if is_type(c[1], "Instant")[0]]
    sorc = [c for c in casts if is_type(c[1], "Sorcery")[0]]
    if inst:
        off = sum(1 for c in inst if not c[2])
        print(f"3 INSTANT TIMING    {100*off/len(inst):5.1f}% of instants cast on "
              f"an OPPONENT's turn ({off}/{len(inst)})")
        own_main = sum(1 for c in inst if c[2] and c[3] == "main")
        print(f"                    {100*own_main/len(inst):5.1f}% dumped on the "
              f"caster's OWN main phase, like a sorcery")
    if casts:
        off_all = sum(1 for c in casts if not c[2])
        print(f"4 OFF-TURN ACTION   {100*off_all/len(casts):5.1f}% of ALL spells cast on "
              f"someone else's turn ({off_all}/{len(casts)})")
        byphase = collections.Counter(c[3] for c in casts)
        top = ", ".join(f"{k} {100*v/len(casts):.0f}%" for k, v in byphase.most_common(4))
        print(f"                    cast phase mix: {top}")
    if st_["discards"]:
        print(f"5 HAND DUMPING      {st_['cleanup_discards']} cleanup discards "
              f"of {st_['discards']} total discards")
    if game_turns:
        print(f"8 GAME SHAPE        median {st.median(game_turns):.0f} player-turns "
              f"(~{st.median(game_turns)/4:.0f} rounds), max {max(game_turns)}")
    print(f"   spells/game: {len(casts)/max(1,len(game_turns)):.1f}   "
          f"instants {len(inst)}  sorceries {len(sorc)}")
    print()
    return {"casts": casts, "stats": st_}


if __name__ == "__main__":
    analyse(["studies/precon_predict/runs_stock/c_r0*.jsonl",
             "studies/precon_predict/runs_stock/c_r1*.jsonl"],
            "STOCK FORGE - precon cohort")
