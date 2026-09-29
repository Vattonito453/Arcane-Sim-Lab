#!/usr/bin/env python3
"""Win-condition support-chain telemetry for a deck across sim results.

Answers, per result: is the commander being cast (and when)? Are the named
finishers doing anything? What's killing us?

There used to be two "engine" rows here for every deck: charge counters and
proliferate, counted across ALL seats. They were Atraxa-era metrics, so a
reanimator deck's lede read "The table logged charge counters 0.12 times a
game and proliferate 0" (UX review problem 11). They are gone (repair plan
WS11 task 8); a deck's own plan rows arrive with its win-con tags (WS12).

Measurement method — event-log substring matches. Every count here is a
substring hit over ``event.raw`` in the adapted Forge log, not a rules-level
read. That is a real signal (the log is authoritative for what was said),
but zero hits can mean "never drawn" as easily as "never cast". Per-game
rates divide by the games actually present in the payload, never by
``summary.games`` (the committed fixture carries a 16-game summary over a
2-game payload — see task 02). The win rate is the published one
(engine/standings.py): wins over decided games.

Status thresholds (documented so the UI and the coach agree; never recompute
these elsewhere — the UI maps the status strings, nothing more):
    watched cards, by events/game:
        healthy: >= 2.0    partial: > 0    cold: 0
    commander, by share of games with at least one cast:
        healthy: >= 0.8    partial: > 0    cold: 0
    ai_skips replaces cold for a card Forge's AI doesn't cast on its own
    (engine/disclosure.py, scripted AI:RemoveDeck:All): zero events for such
    a card say nothing about the card, so it gets no verdict and is never a
    cut candidate. The report lists those cards as ``ai_wont_play`` (None
    when the Forge index or the deck file is unavailable).

Usage:
  python3 deck_telemetry.py <deck_substring> [--cards "Lux Cannon,Dawnsire,..."]

Reads every sim_*rotated.json (and sim_*.json) in ./sim_results that includes
a deck whose filename contains <deck_substring>.
"""
from __future__ import annotations
import glob, json, re, statistics, sys
from pathlib import Path

_AI_PREFIX = re.compile(r"^Ai\(\d+\)-")
HEALTHY_EVENTS_PER_GAME = 2.0
HEALTHY_COMMANDER_CAST_RATE = 0.8


def _strip_ai(key: str) -> str:
    return _AI_PREFIX.sub("", key)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.casefold()).strip("_")


def _match_deck(decks: list[str], sub: str) -> str | None:
    sub_cf = sub.casefold()
    for d in decks:
        if sub_cf in d.casefold():
            return d
    return None


def _player_for(players: list[str], deck: str) -> str | None:
    """Map a deck filename to its (seat-prefixed) player key in one game."""
    stem = _norm(Path(deck).stem)
    for p in players:
        pn = _norm(_strip_ai(p))
        if stem in pn or pn in stem:
            return p
    tok = stem.split("_")[0]
    for p in players:
        if tok in p.casefold():
            return p
    return None


def _deck_file(deck: str) -> Path | None:
    """The .dck a meta.decks entry names, through mtg_engine._find_deck
    (imported first, then bundled; CLAUDE.md gotcha 9).

    meta.decks holds the paths the run was played with, which are CONTAINER
    paths ("/data/decks/skrat_s_revenge_239c6293.dck"). _find_deck refuses
    anything but a bare filename (its traversal rule), so it must be handed
    the basename. Handing it the path is what made every imported deck read
    "No commander could be identified" while the bundled ones resolved
    through the fallback below (UX review problem 11)."""
    name = Path(str(deck)).name
    try:
        # Lazy import: mtg_engine serves telemetry and imports this module.
        from mtg_engine import _find_deck
        path = _find_deck(name)
    except Exception:  # noqa: BLE001
        path = None
    if path is None:
        # The CLI, run without the server's data dir: the bundled decks only.
        local = Path(__file__).parent / "decks" / name
        path = local if local.is_file() else None
    return path


def _commander_of(deck: str, meta: dict | None = None,
                  player_key: str | None = None) -> str | None:
    """The deck's first commander, as Forge logs its name.

    meta.commanders first (run_sim and readapt write it, keyed by the deck's
    Name=, which is the seat's player name without its Ai(n)- prefix), so a
    deck deleted after the run still has one; else the deck file's
    [Commander] section, read by commanders.dck_identity (the rules every
    other surface uses: counts, comments, the |SET suffix, a DFC's front
    face). A partner deck reports its first commander."""
    stored = (meta or {}).get("commanders")
    if player_key and isinstance(stored, dict):
        names = stored.get(_strip_ai(player_key)) or []
        if names:
            return str(names[0])
    path = _deck_file(deck)
    if path is None:
        return None
    import commanders  # noqa: PLC0415  (lazy, like _find_deck)
    names = commanders.dck_identity(path)["commanders"]
    return names[0] if names else None


def _status(per_game: float) -> str:
    if per_game >= HEALTHY_EVENTS_PER_GAME:
        return "healthy"
    if per_game > 0:
        return "partial"
    return "cold"


_AUTO = object()


def _judged(status: str, skipped: bool) -> str:
    """No "cold" verdict for a card Forge's AI doesn't cast on its own."""
    return "ai_skips" if skipped and status == "cold" else status


def _ai_wont_play(result: dict, deck: str) -> list[str] | None:
    try:
        import disclosure
        row = disclosure.for_result_deck(result.get("meta") or {}, deck)
    except Exception:  # noqa: BLE001 - telemetry must still compute without it
        return None
    return None if row is None else row.get("ai_wont_play")


def compute(result: dict, deck_substring: str, watch: list[str] | None = None,
            commander: str | None = None, ai_wont_play=_AUTO) -> dict:
    """Structured telemetry for one deck across every game in one result.

    Raises ValueError when no deck in ``result.meta.decks`` matches
    ``deck_substring`` or the payload holds no games. ``commander`` overrides
    the [Commander] line lookup (useful when the deck file is unavailable).
    ``ai_wont_play`` overrides the disclosure lookup (engine/disclosure.py):
    the cards Forge's AI doesn't cast on its own, which get "ai_skips"
    instead of "cold". None means unknown, and then nothing is exempted.
    """
    decks = result.get("meta", {}).get("decks", [])
    deck = _match_deck(decks, deck_substring)
    if deck is None:
        raise ValueError(f'no deck matching "{deck_substring}" in this result')
    games = result.get("games", [])
    n = len(games)
    if n == 0:
        raise ValueError("result contains no games")
    watch = [c for c in (watch or []) if c]
    player_key = next((me for me in (_player_for(g.get("players", []), deck)
                                     for g in games) if me), None)
    if commander is None:
        commander = _commander_of(deck, result.get("meta"), player_key)
    if ai_wont_play is _AUTO:
        ai_wont_play = _ai_wont_play(result, deck)
    from disclosure import matches as _skips
    skipped = list(ai_wont_play or [])

    import standings  # noqa: PLC0415  the published denominator
    wins = 0
    decided = 0
    games_cast = 0
    cmd_casts = 0
    first_cast_turns: list[int] = []
    hits = {c: 0 for c in watch}
    dmg: dict[str, int] = {}
    death_turns: list[int] = []

    for g in games:
        me = _player_for(g.get("players", []), deck)
        # Wins over DECIDED games (engine/standings.py): a game the clock
        # cut off is a draw whatever winner its record carries, and it is
        # not in the denominator.
        winner = standings.winner_of(g)
        if me and winner is not None:
            decided += 1
            if winner == _strip_ai(me):
                wins += 1
        cast_raw = f"{me} cast {commander}" if (me and commander) else None
        life_re = re.compile(
            rf"Life:\s*{re.escape(me)}\s+-?\d+\s*>\s*(-?\d+)") if me else None
        first_cast = died_turn = lost_turn = None
        for t in g.get("turns", []):
            turn = t.get("turn")
            for e in t.get("events", []):
                r = e.get("raw", "")
                for c in watch:
                    if c in r:
                        hits[c] += 1
                if not me:
                    continue
                action = e.get("action")
                if cast_raw and action == "stack_add" and r == cast_raw:
                    cmd_casts += 1
                    if first_cast is None:
                        first_cast = turn
                elif action == "damage" and e.get("target") == me:
                    src = e.get("source", "?").split(" (")[0]
                    dmg[src] = dmg.get(src, 0) + e.get("amount", 0)
                elif action == "life_change" and died_turn is None and life_re:
                    m = life_re.match(r)
                    if m and int(m.group(1)) <= 0:
                        died_turn = turn
                elif (action == "game_outcome" and lost_turn is None
                      and "has lost" in r and me in r):
                    lost_turn = turn
        if first_cast is not None:
            games_cast += 1
            first_cast_turns.append(first_cast)
        death = died_turn if died_turn is not None else lost_turn
        if death is not None:
            death_turns.append(death)

    return {
        "games": n,
        "deck": deck,
        "player_key": player_key,
        "source": result.get("meta", {}).get("source"),
        "commander": ({
            "name": commander,
            "cast_rate": round(games_cast / n, 3),
            "median_turn": (statistics.median(first_cast_turns)
                            if first_cast_turns else None),
            "casts_per_game": round(cmd_casts / n, 2),
            "status": _judged("healthy" if games_cast / n >= HEALTHY_COMMANDER_CAST_RATE
                              else "partial" if games_cast else "cold",
                              _skips(commander, skipped)),
            "ai_wont_play": _skips(commander, skipped),
        } if commander else None),
        "watched": [{
            "name": c,
            "events": hits[c],
            "events_per_game": round(hits[c] / n, 2),
            "status": _judged(_status(hits[c] / n), _skips(c, skipped)),
            "ai_wont_play": _skips(c, skipped),
        } for c in watch],
        # This deck's cards Forge's AI doesn't cast on its own (None: unknown).
        "ai_wont_play": ai_wont_play,
        "deaths": {
            "by_source": [{"source": s, "damage": a} for s, a in
                          sorted(dmg.items(), key=lambda kv: -kv[1])[:6]],
            "median_turn": (statistics.median(death_turns)
                            if death_turns else None),
        },
        "wins": wins,
        "decided": decided,
        # The published rate: wins over decided games (engine/standings.py).
        # None when nothing was decided, never a 0 that reads as "lost all".
        "win_rate": round(wins / decided, 3) if decided else None,
        "method": ("event-log substring matches over event.raw; per-game "
                   "rates divide by games present in this payload; the win "
                   "rate divides by decided games"),
    }


def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else 'kilo_helm'
    watch = []
    if '--cards' in sys.argv:
        watch = [c.strip() for c in sys.argv[sys.argv.index('--cards')+1].split(',')]
    reports = []
    for f in sorted(glob.glob('sim_results/sim_*.json')) + sorted(glob.glob('sim_*.json')):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        try:
            reports.append(compute(d, sub, watch))
        except ValueError:
            continue
    if not reports:
        sys.exit(f'no results mention a deck matching "{sub}"')
    games = sum(r['games'] for r in reports)
    print(f'files: {len(reports)} | games: {games}')
    cmds = [r['commander'] for r in reports if r['commander']]
    if cmds:
        cast_games = sum(round(c['cast_rate'] * r['games'])
                         for c, r in zip(cmds, [r for r in reports if r['commander']]))
        turns = [c['median_turn'] for c in cmds if c['median_turn'] is not None]
        med = f", median first cast turn {statistics.median(turns):g}" if turns else ""
        print(f'commander {cmds[0]["name"]}: cast in {cast_games}/{games} games{med}')
    for c in watch:
        nhits = sum(w['events'] for r in reports
                    for w in r['watched'] if w['name'] == c)
        print(f'  watched card "{c}": {nhits} events ({nhits/games:.1f}/game)')
    dmg: dict[str, int] = {}
    for r in reports:
        for row in r['deaths']['by_source']:
            dmg[row['source']] = dmg.get(row['source'], 0) + row['damage']
    print('top damage sources against the deck:',
          sorted(dmg.items(), key=lambda kv: -kv[1])[:6])


if __name__ == '__main__':
    main()
