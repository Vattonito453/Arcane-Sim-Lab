#!/usr/bin/env python3
"""Convert simlab-forge-shim JSON-lines output into the standard result schema.

The shim (separate GPL repo; see CLAUDE.md "Legal posture") emits typed
GameLog entries whose `message` fields are the exact texts Forge prints in
`sim` mode, minus the `<Caption>: ` prefix. This module rebuilds that
pseudo-stdout and reuses forge_log_adapter.parse_forge_log verbatim, so the
downstream schema (games/turns/events/summary) is identical to a stock run.

What the shim adds on top — and what this module preserves — is the `zone`
records from Forge's event bus: EVERY card movement including battlefield
ENTRIES, which the stdout log never contains (the measured 86.5% board
reconstruction ceiling). They are attached per game under `"zones"`, an
additive key no existing consumer reads yet.

Zero dependencies (stdlib only).
"""
from __future__ import annotations

import json
import sys

from forge_log_adapter import parse_forge_log, summarize

# GameLogEntryType enum name -> the caption Forge prints in sim mode
# (forge_log_adapter's CAPTION_TO_ACTION is keyed on the captions).
TYPE_TO_CAPTION = {
    "TURN": "Turn",
    "PHASE": "Phase",
    "MULLIGAN": "Mulligan",
    "ANTE": "Ante",
    "DRAFT": "Draft",
    "ZONE_CHANGE": "Zone Change",
    "PLAYER_CONTROL": "Player Control",
    "DAMAGE": "Damage",
    "LIFE": "Life",
    "LAND": "Land",
    "DISCARD": "Discard",
    "COMBAT": "Combat",
    "INFORMATION": "Information",
    "STACK_RESOLVE": "Resolve Stack",
    "STACK_ADD": "Add To Stack",
    "EFFECT_REPLACED": "Replacement Effect",
    "MANA": "Mana",
    "GAME_OUTCOME": "Game Outcome",
    "MATCH_RESULTS": "Match Result",
}


def parse_shim_jsonl(text: str, source: str = "simlab-forge-shim") -> dict:
    """Parse one shim invocation's JSONL (may contain several games)."""
    meta_rec: dict = {}
    entries: dict[int, list[dict]] = {}
    results: dict[int, dict] = {}
    zones: dict[int, list[dict]] = {}
    agent_events: dict[int, list[dict]] = {}
    # Board-state streams (shim >= 0.12.0): per-card tap state, counter
    # totals, and attachments, each stamped with turn + phase so the replay
    # can place them WITHIN a turn at phase granularity (the text log and the
    # shim streams share no sequence number; phase is the honest resolution).
    boardfx: dict[int, list[dict]] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue  # defensive: a stray non-JSON line loses one record, not the run
        rec = r.get("rec")
        if rec == "meta":
            meta_rec = r
        elif rec == "entry":
            entries.setdefault(r["game"], []).append(r)
        elif rec == "result":
            results[r["game"]] = r
        elif rec in ("tap", "counters", "attach"):
            boardfx.setdefault(r["game"], []).append(
                {k: r[k] for k in ("rec", "turn", "phase", "cardId", "card",
                                   "tapped", "type", "n", "to") if k in r})
        elif rec == "zone":
            # types/pt/token arrive from shim >= 0.3.0 and are what let board.py
            # read the battlefield instead of inferring it. Older logs simply
            # lack the keys, and the reader falls back to Scryfall typing.
            zones.setdefault(r["game"], []).append(
                {k: r[k] for k in ("turn", "phase", "card", "cardId", "from", "to",
                                   "fromPlayer", "toPlayer",
                                   "types", "pt", "token") if k in r})
        elif rec == "agent":
            agent_events.setdefault(r["game"], []).append(
                {k: r[k] for k in ("turn", "player", "event", "detail") if k in r})

    # Rebuild the stdout Forge's sim mode would have printed.
    lines: list[str] = []
    game_order = sorted(entries.keys() | results.keys())
    for g in game_order:
        for e in entries.get(g, []):
            caption = TYPE_TO_CAPTION.get(e.get("type", ""))
            if caption:
                lines.append(f"{caption}: {e.get('message', '')}")
        res = results.get(g)
        if res:
            ms = res.get("ms", 0)
            if res.get("draw") or not res.get("winner"):
                lines.append(f"Game Result: Game {g + 1} ended in a Draw! Took {ms} ms.")
            else:
                lines.append(f"Game Result: Game {g + 1} ended in {ms} ms. "
                             f"{res['winner']} has won!")
        else:
            # A game with entries but no result record — a truncated JSONL
            # line, an OOM-kill mid-flush, a crash. parse_forge_log splits on
            # "Game Result" lines, so without one here that game's entries
            # merge into the NEXT game's and every zones/agent_events/timedOut
            # attachment after the gap lands on the wrong game (audit A6).
            # Emitting a placeholder keeps one parsed game per source game, so
            # the positional attachment below stays true by construction. The
            # placeholder is flagged below and never counted as a result.
            lines.append(f"Game Result: Game {g + 1} ended in a Draw! Took 0 ms.")

    result = parse_forge_log("\n".join(lines), source=source)
    result["meta"]["agent"] = f"simlab-forge-shim/{meta_rec.get('shim', '?')}"
    # Honesty label: plan-agent results are NOT stock-Forge numbers and must
    # never be compared against stock baselines unlabeled (SIM_CALIBRATION).
    result["meta"]["humanized"] = bool(meta_rec.get("humanized"))
    # Per-seat pilot ("plan" | "stock"), positionally aligned with meta.players.
    # humanized is a single bool for the whole pod; this is what distinguishes a
    # genuinely humanized run from a mixed one, and a mixed pod is a different
    # experiment. Absent on logs written before the shim emitted it.
    if meta_rec.get("agents"):
        result["meta"]["agents"] = meta_rec["agents"]
    # Per-seat AI profile, aligned the same way. Arm identity is the PAIR
    # (controller, profile): SimLabHuman is Default with the counterspell
    # chances maxed, and it is designed to be gated by the plan controller's
    # threat veto, so "plan" alone does not identify what a seat was running.
    if meta_rec.get("profiles"):
        result["meta"]["profiles"] = meta_rec["profiles"]
    # Enough to reconstruct any seat's RNG stream in any game:
    #   seed = seedBases[seat] + playerId + seedGameStride * gameIndex
    # The raw JSONL is not kept (sim_results is gitignored and the logs are
    # swept), so a run whose randomness is only recorded there is a run whose
    # randomness is not recorded at all. Shim >= 0.4.0 (audit A2).
    for k in ("seedBases", "seedGameStride"):
        if meta_rec.get(k) is not None:
            result["meta"][k] = meta_rec[k]

    # One parsed game per source game, guaranteed by the placeholder above.
    # Assert it rather than trust it: a silent mismatch here shifts every
    # attachment after the gap onto the wrong game, which is invisible in the
    # output and was reproducible from a single truncated line (audit A6).
    if len(result["games"]) != len(game_order):
        raise ValueError(
            f"shim log misalignment: {len(game_order)} game(s) in the JSONL but "
            f"{len(result['games'])} parsed. Refusing to attach zones and agent "
            f"telemetry positionally, because the mapping would be wrong.")

    # Attach ground-truth zone movements per game (order matches game_order
    # because every shim game produces exactly one parsed game).
    missing_results = 0
    errored = 0
    for i, g in enumerate(game_order):
        game = result["games"][i]
        game["zones"] = zones.get(g, [])
        # Additive: readers that predate 0.12.0 ignore this key.
        game["boardfx"] = boardfx.get(g, [])
        # Agent self-telemetry: authoritative for agent behavior — the
        # GameLog writes some combat lines before the agent's adjustments.
        game["agent_events"] = agent_events.get(g, [])
        res = results.get(g)
        if res is None:
            # The placeholder case. Mark it so nothing reads the stand-in draw
            # as a real one.
            missing_results += 1
            game["result"]["missingResult"] = True
            game["result"]["draw"] = False
            game["result"]["winner"] = None
            continue
        # The reconstructed text line above only carries draw/winner —
        # timedOut has no stock-Forge equivalent to rebuild it from, so
        # stamp it on directly from the raw shim record. Recompute the
        # summary after: it was built from the text-only result dict,
        # before this key existed, so its "timeouts" count would
        # otherwise silently stay 0 no matter how many games hit the
        # clock (see forge_log_adapter.summarize).
        game["result"]["timedOut"] = bool(res.get("timedOut"))
        # Per-seat life and survival at termination. The only thing a
        # timed-out game carries: it has no winner, so excluding it
        # drops the whole game, and timed-out games are the long ones,
        # a biased slice rather than a random one. Survival is a
        # separate outcome and must never be folded into a win rate.
        if res.get("seats"):
            game["result"]["seats"] = res["seats"]
        if res.get("error"):
            # A crashed game (shim >= 0.4.0, audit A4). It is neither a win nor
            # a draw: it is an absence of a result, and counting it as a draw
            # is what silently inflated draw rates.
            errored += 1
            game["result"]["error"] = True
            game["result"]["errorClass"] = res.get("errorClass")
            game["result"]["draw"] = False
            game["result"]["winner"] = None

    total_zones = sum(len(z) for z in zones.values())
    entries_bf = sum(1 for zz in zones.values() for z in zz if z.get("to") == "Battlefield")
    result["meta"]["zone_records"] = total_zones
    result["meta"]["battlefield_entries"] = entries_bf
    if missing_results:
        result["meta"]["games_missing_result"] = missing_results
    if errored:
        result["meta"]["games_errored"] = errored
    result["summary"] = summarize(result["games"])
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: shim_log_adapter.py <shim_out.jsonl> [out.json]", file=sys.stderr)
        sys.exit(1)
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    result = parse_shim_jsonl(text, source=sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None
    payload = json.dumps(result, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {out}: {result['summary']}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
