#!/usr/bin/env python3
"""Win-condition support-chain telemetry for a deck across sim results.

Answers, per result: is the commander being cast (and when)? Are charge
counters happening? Is proliferate resolving? Are the named finishers doing
anything? What's killing us?

Measurement method — event-log substring matches. Every count here is a
substring hit over ``event.raw`` in the adapted Forge log, not a rules-level
read. That is a real signal (the log is authoritative for what was said),
but "proliferate" also matches oracle reminder text, and zero hits can mean
"never drawn" as easily as "never cast". Rates always divide by the games
actually present in the payload, never by ``summary.games`` (the committed
fixture carries a 16-game summary over a 2-game payload — see task 02).

Status thresholds (documented so the UI and the coach agree; never recompute
these elsewhere — the UI maps the status strings, nothing more):
    watched cards and engine metrics, by events/game:
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


def _commander_of(deck: str) -> str | None:
    """Read the [Commander] line from the deck file, if we can find it."""
    path = None
    try:
        # Lazy import: mtg_engine serves telemetry and imports this module.
        from mtg_engine import _find_deck
        # meta.decks holds container paths ("/data/decks/x.dck") and
        # _find_deck refuses anything but a bare filename, so an imported
        # deck's commander was never found here (production telemetry showed
        # "No commander could be identified" for every imported deck).
        path = _find_deck(Path(deck).name)
    except Exception:
        path = None
    if path is None:
        local = Path(__file__).parent / "decks" / Path(deck).name
        path = local if local.is_file() else None
    if path is None:
        return None
    in_cmd = False
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("["):
            in_cmd = line.casefold() == "[commander]"
            continue
        if in_cmd and line:
            parts = line.split(" ", 1)
            name = parts[1] if parts[0].isdigit() and len(parts) == 2 else line
            # Forge's "|SET|art" printing suffix is not part of the name: a
            # precon line "1 Winter, Cynical Opportunist|DSC|1" is logged and
            # cast as "Winter, Cynical Opportunist".
            return name.split("|", 1)[0].strip()
    return None


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
    if commander is None:
        commander = _commander_of(deck)
    if ai_wont_play is _AUTO:
        ai_wont_play = _ai_wont_play(result, deck)
    from disclosure import matches as _skips
    skipped = list(ai_wont_play or [])

    player_key = None
    wins = 0
    games_cast = 0
    cmd_casts = 0
    first_cast_turns: list[int] = []
    charge = prolif = 0
    hits = {c: 0 for c in watch}
    dmg: dict[str, int] = {}
    death_turns: list[int] = []

    for g in games:
        me = _player_for(g.get("players", []), deck)
        if player_key is None and me:
            player_key = me
        winner = (g.get("result") or {}).get("winner")
        if me and winner and _strip_ai(winner) == _strip_ai(me):
            wins += 1
        cast_raw = f"{me} cast {commander}" if (me and commander) else None
        life_re = re.compile(
            rf"Life:\s*{re.escape(me)}\s+-?\d+\s*>\s*(-?\d+)") if me else None
        first_cast = died_turn = lost_turn = None
        for t in g.get("turns", []):
            turn = t.get("turn")
            for e in t.get("events", []):
                r = e.get("raw", "")
                rl = r.casefold()
                if "charge counter" in rl:
                    charge += 1
                if "proliferate" in rl:
                    prolif += 1
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
        "engine": {
            "charge_events": charge,
            "charge_events_per_game": round(charge / n, 2),
            "charge_status": _status(charge / n),
            "proliferate_events": prolif,
            "proliferate_per_game": round(prolif / n, 2),
            "proliferate_status": _status(prolif / n),
        },
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
        "win_rate": round(wins / n, 3),
        "method": ("event-log substring matches over event.raw; "
                   "rates divide by games present in this payload"),
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
    charge = sum(r['engine']['charge_events'] for r in reports)
    prolif = sum(r['engine']['proliferate_events'] for r in reports)
    print(f'files: {len(reports)} | games: {games}')
    cmds = [r['commander'] for r in reports if r['commander']]
    if cmds:
        cast_games = sum(round(c['cast_rate'] * r['games'])
                         for c, r in zip(cmds, [r for r in reports if r['commander']]))
        turns = [c['median_turn'] for c in cmds if c['median_turn'] is not None]
        med = f", median first cast turn {statistics.median(turns):g}" if turns else ""
        print(f'commander {cmds[0]["name"]}: cast in {cast_games}/{games} games{med}')
    print(f'charge-counter events: {charge} ({charge/games:.1f}/game)')
    print(f'proliferate resolutions: {prolif} ({prolif/games:.1f}/game)')
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
