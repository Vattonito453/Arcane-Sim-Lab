#!/usr/bin/env python3
"""AI deck coaching: zero-token context assembly + one cached synthesis call.

Cost discipline (frontend_architecture.md §2): exactly ONE LLM call per
(deck_hash, gauntlet_id), then cached forever under MTG_DATA_DIR/coaching.
Everything the model reads — sim summary, telemetry, archetype, calibration
notes — is assembled locally for zero tokens; the model only writes the
coaching prose.

Calibration rules (engine/SIM_CALIBRATION.md) are enforced IN CODE, not left
to the model:
  - non-rotated runs are rejected as coaching input;
  - verdict.win_rate / baseline / sim_is_floor are overwritten from the
    context after generation, so a displayed rate always has its baseline;
  - every suggested change must carry an evidence tag from a fixed
    vocabulary or the output is rejected (one retry, then fail closed);
  - a card Forge's AI doesn't cast on its own (engine/disclosure.py) is never
    a "cut" and never "cold": the sim says nothing about a card its AI skips.
    New output that does either is rejected; a report cached before this
    rule has such rows withheld when it is served (`withheld_cuts`).
EDHREC consensus is not wired up yet, so "consensus" is not accepted as
evidence in v1 — changes are [sim-evidence] or [theory].
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import archetype as archetype_mod  # noqa: E402
import deck_telemetry  # noqa: E402
import llm  # noqa: E402
import os  # noqa: E402
import validity  # noqa: E402
from deck_plan import read_dck  # noqa: E402

EVIDENCE = {"sim-evidence", "theory"}   # "consensus" arrives with EDHREC data
# "ai_skips": a link on a card Forge's AI doesn't cast on its own, which the
# sim cannot judge (the telemetry status of the same name). Never "cold".
STATUSES = {"running", "partial", "cold", "ai_skips"}
_AI_PREFIX = re.compile(r"^Ai\(\d+\)-")

CALIBRATION_NOTES = [
    "Win rates are seat-rotated. Compare to the archetype baseline, never to 25%.",
    "Engine/combo decks simulate below their real strength: the AI cannot pilot "
    "politics, protection timing, or multi-turn loops.",
    "A deck whose machinery fires but loses to archetype bias is probably fine "
    "in human hands; a deck whose machinery never fires is actually broken.",
    "Telemetry counts are event-log substring matches, not rules-level reads.",
    "Cards listed in ai_wont_play are ones Forge's AI doesn't cast on its own "
    "(the pilot casts some while chasing a combo or tutoring). Their absence "
    "from the log says nothing about the card: never call one cold (use "
    "ai_skips), and never suggest cutting one.",
]

SYSTEM_PROMPT = (
    "You are a Commander deck coach reading one simulation gauntlet. Answer "
    "ONLY from the JSON context provided; if the context does not support a "
    "claim, omit the claim. Never state a win rate without the archetype "
    "baseline next to it. If archetype.sim_is_floor is true, say plainly that "
    "the simulated result is a floor, not a verdict. Every suggested change "
    "cites evidence: \"sim-evidence\" when a number in the context backs it, "
    "otherwise \"theory\"; community consensus data is not available, so "
    "never claim it. Only suggest cutting cards that appear in the decklist, "
    "and never suggest cutting, or mark cold, a card listed in ai_wont_play: "
    "Forge's AI doesn't cast those on its own, so the sim cannot judge them; "
    "a support_chain row about one that never fired has status \"ai_skips\" "
    "and names the card; use \"ai_skips\" for nothing else. "
    "Reply with STRICT JSON only — no markdown fences, no commentary — "
    "matching exactly:\n"
    "{\"verdict\": {\"headline\": string (<=80 chars), \"prose\": string "
    "(2-3 sentences, coaching voice)},\n"
    " \"support_chain\": [{\"link\": string, \"status\": \"running\"|"
    "\"partial\"|\"cold\"|\"ai_skips\", \"measured\": string, \"reading\": string}],\n"
    " \"matchups\": [{\"pod\": string, \"win_rate\": number, \"note\": "
    "string}],\n"
    " \"changes\": [{\"action\": \"add\"|\"cut\", \"card\": string, "
    "\"reason\": string, \"evidence\": \"sim-evidence\"|\"theory\"}],\n"
    " \"play_guide\": [string, ...]}\n"
    "support_chain rows restate the telemetry metrics; matchups come from "
    "the pod win rates (one row per opposing deck); give 2-5 changes and "
    "3-6 play_guide bullets."
)


def _coaching_dir() -> Path:
    base = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent)))
    return base / "coaching"


def _resolve_deck(deck_file: str) -> Path | None:
    p = Path(deck_file)
    if p.is_file():
        return p
    try:
        from mtg_engine import _find_deck
        return _find_deck(Path(deck_file).name)
    except Exception:
        return None


def deck_hash(deck_path: Path) -> str:
    """sha256 of the normalized decklist: casefolded card names, sorted.
    Count-insensitive on purpose — Commander is singleton and the hash keys
    a coaching report, not a legality check."""
    _, commanders, main = read_dck(deck_path)
    names = sorted(n.casefold() for n in commanders + main)
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def build_context(result: dict, deck_file: str) -> dict:
    """Everything the coach reads, assembled locally. Zero tokens."""
    deck_path = _resolve_deck(deck_file)
    if deck_path is None:
        raise FileNotFoundError(f"deck not found: {deck_file}")
    _, commanders, main = read_dck(deck_path)
    commander = commanders[0] if commanders else None

    telemetry = deck_telemetry.compute(result, deck_path.stem,
                                       commander=commander)
    arch = archetype_mod.classify(main, commander)
    # The same list telemetry exempted; read from the deck file itself when
    # the run's meta.decks names no file this deck resolves to.
    skipped = telemetry.get("ai_wont_play")
    if skipped is None:
        skipped = _ai_wont_play_of(deck_path)

    games = result.get("games", [])
    n = len(games)
    pod: dict[str, int] = {}
    for g in games:
        for p in g.get("players", []):
            pod.setdefault(_AI_PREFIX.sub("", p), 0)
        winner = (g.get("result") or {}).get("winner")
        if winner:
            key = _AI_PREFIX.sub("", winner)
            pod[key] = pod.get(key, 0) + 1
    me = _AI_PREFIX.sub("", telemetry.get("player_key") or "")
    opponents = [{"name": name, "wins": w,
                  "win_rate": round(w / n, 3) if n else 0}
                 for name, w in sorted(pod.items(), key=lambda kv: -kv[1])
                 if name != me]

    return {
        "deck": deck_path.name,
        "deck_name": me or deck_path.stem,
        "commander": commander,
        "decklist": main,
        "games": n,
        "rotated": result.get("meta", {}).get("source") == "rotated",
        "win_rate": telemetry["win_rate"],
        "wins": telemetry["wins"],
        "archetype": arch,
        "telemetry": telemetry,
        "opponents": opponents,
        # Cards Forge's AI doesn't cast on its own: never "cut", never "cold".
        "ai_wont_play": list(skipped or []),
        "calibration_notes": CALIBRATION_NOTES,
    }


def _ai_wont_play_of(deck_path: Path) -> list[str]:
    """This deck's cards Forge's AI doesn't cast on its own, from the deck
    file and the Forge index (engine/disclosure.py); [] when unknown."""
    try:
        import disclosure
        return disclosure.of_deck_text(
            deck_path.read_text(encoding="utf-8", errors="replace")).get("ai_wont_play") or []
    except Exception:  # noqa: BLE001 - coaching must still run without it
        return []


def _skipped_cold(row: dict, skipped) -> list[str]:
    """The skipped cards a support-chain row calls cold."""
    if row.get("status") != "cold":
        return []
    import disclosure
    return disclosure.mentions(str(row.get("link") or ""), skipped)


def withhold_skipped(report: dict, skipped) -> dict:
    """A served report never carries a cut or a "cold" verdict for a card
    Forge's AI doesn't cast on its own. New output is rejected for that
    (_validate); a report cached before the rule existed has such cuts moved
    to `withheld_cuts` and such rows re-marked "ai_skips", so the page can
    say what was withheld and why. Changes the report in place and returns it."""
    if not report.get("ok") or not skipped:
        return report
    import disclosure
    kept, withheld = [], []
    for c in report.get("changes") or []:
        if c.get("action") == "cut" and disclosure.matches(str(c.get("card") or ""), skipped):
            withheld.append(c)
        else:
            kept.append(c)
    if withheld:
        report["changes"] = kept
        report["withheld_cuts"] = withheld
    for row in report.get("support_chain") or []:
        if _skipped_cold(row, skipped):
            row["status"] = "ai_skips"
    report["ai_wont_play"] = list(skipped)
    return report


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def _validate(d: dict, decklist: list[str], skipped=()) -> None:
    """Schema + discipline checks; raises ValueError on any violation.
    `skipped` is the deck's ai_wont_play list: no cut and no cold row for one."""
    import disclosure
    v = d.get("verdict")
    if not isinstance(v, dict) or not v.get("headline") or not v.get("prose"):
        raise ValueError("verdict.headline/prose missing")
    for row in d.get("support_chain", []):
        if row.get("status") not in STATUSES:
            raise ValueError(f"bad support_chain status: {row.get('status')}")
        if not row.get("link"):
            raise ValueError("support_chain row without a link name")
        named = _skipped_cold(row, skipped)
        if named:
            raise ValueError(f"support_chain calls {named[0]} cold, but Forge's AI "
                             f"doesn't cast it on its own (use ai_skips)")
        # "ai_skips" renders as "Not judged": it may only stand for a card on
        # the list, or a model could hide any cold link behind it.
        if row.get("status") == "ai_skips" and not disclosure.mentions(
                " ".join(str(row.get(k) or "") for k in ("link", "measured", "reading")),
                skipped):
            raise ValueError(f"support_chain marks {row.get('link')} ai_skips, but it "
                             f"names no card Forge's AI doesn't cast on its own")
    for m in d.get("matchups", []):
        if not m.get("pod") or not isinstance(m.get("win_rate"), (int, float)):
            raise ValueError("malformed matchup row")
    lowered = {c.casefold() for c in decklist}
    for c in d.get("changes", []):
        if c.get("action") not in ("add", "cut"):
            raise ValueError(f"bad change action: {c.get('action')}")
        if c.get("evidence") not in EVIDENCE:
            raise ValueError(f"bad evidence tag: {c.get('evidence')}")
        if not c.get("card") or not c.get("reason"):
            raise ValueError("change without card/reason")
        if c["action"] == "cut" and c["card"].casefold() not in lowered:
            raise ValueError(f"cut suggests a card not in the deck: {c['card']}")
        if c["action"] == "cut" and disclosure.matches(c["card"], skipped):
            raise ValueError(f"cut suggests {c['card']}, which Forge's AI doesn't "
                             f"cast on its own, so the sim cannot judge it")
    if not isinstance(d.get("play_guide"), list) or not d["play_guide"]:
        raise ValueError("play_guide missing")


def synthesize(context: dict, *, model: str | None = None,
               api_key: str | None = None) -> dict:
    """The single LLM call. Validates before returning; retries once."""
    user = json.dumps(context, indent=1)
    last_err = "empty"
    for attempt in range(2):
        text = llm.complete(SYSTEM_PROMPT, user, model=model,
                            api_key=api_key, max_tokens=1500)
        try:
            out = _parse_json(text)
            _validate(out, context.get("decklist", []), context.get("ai_wont_play") or ())
            return out
        except (ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
            user = (json.dumps(context, indent=1) +
                    f"\n\nYour previous reply was rejected: {last_err}. "
                    "Reply again with STRICT JSON matching the schema.")
    raise ValueError(f"coach output invalid after retry: {last_err}")


def _load_result(result_file: str) -> tuple[dict, str]:
    """(result dict, gauntlet id). Bare names go through mtg_engine's
    traversal-guarded reader; explicit paths are for CLI use."""
    p = Path(result_file)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8")), p.stem
    from mtg_engine import _read_result
    return _read_result(result_file), Path(result_file).stem


def cached_report(result_file: str, deck_file: str) -> dict | None:
    """The stored report, or None. Never generates, never calls the model.

    A report is cached forever under (deck_hash, gauntlet_id), which is only
    safe while the advice would come out the same. It would not: reports
    written before 2026-08-06 were generated from runs whose win rates
    included clock-forced fake wins, with no stamp saying so, and advice built
    on a 40% win rate that was really 12% is wrong in a way the reader cannot
    see. A cache entry without the current validity stamp is discarded rather
    than served (audit A25).
    """
    deck_path = _resolve_deck(deck_file)
    if deck_path is None:
        return None
    key = f"{deck_hash(deck_path)}-{Path(result_file).stem}"
    f = _coaching_dir() / f"{key}.json"
    if not f.is_file():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    if (data.get("meta") or {}).get("validity_version") != validity.VALIDITY_VERSION:
        return None
    data["cached"] = True
    # A report cached before the ai_wont_play rule may still cut, or call
    # cold, a card Forge's AI doesn't cast on its own: withheld, and said so.
    return withhold_skipped(data, _ai_wont_play_of(deck_path))


def report(result_file: str, deck_file: str, *, refresh: bool = False) -> dict:
    """Cache-aware entry point. A hit makes no network call."""
    if not refresh:
        hit = cached_report(result_file, deck_file)
        if hit is not None:
            return hit
    result, gauntlet_id = _load_result(result_file)
    # The old gate checked meta.source alone, which a polluted rotated file
    # passes: it is rotated, and its win rates are still built on clock-forced
    # fake wins. Coaching a deck off those numbers produces confident advice
    # about a result that never happened.
    verdict = validity.assess(result)
    if verdict["quality"] == validity.POLLUTED:
        return {"ok": False,
                "reason": "this run's results are not trustworthy, so coaching "
                          "them would be advice about a game that did not "
                          "happen. " + " ".join(verdict["reasons"]),
                "validity": verdict}
    deck_path = _resolve_deck(deck_file)
    if deck_path is None:
        return {"ok": False, "reason": f"deck not found: {deck_file}"}
    if not llm.configured():
        return {"ok": False, "reason": "no LLM configured"}

    context = build_context(result, deck_file)
    try:
        synth = synthesize(context)
    except llm.LLMError as e:
        return {"ok": False, "reason": f"generation failed: {e}"}
    except ValueError as e:
        return {"ok": False, "reason": str(e)}

    dh = deck_hash(deck_path)
    # The displayed numbers are facts from the context, never model output.
    synth["verdict"]["win_rate"] = context["win_rate"]
    synth["verdict"]["baseline"] = context["archetype"]["baseline"]
    synth["verdict"]["sim_is_floor"] = context["archetype"]["sim_is_floor"]
    out = {
        "ok": True, **synth,
        # Named on the page: these were kept out of the cut suggestions.
        "ai_wont_play": context["ai_wont_play"],
        "archetype": context["archetype"],
        "games": context["games"],
        "deck": context["deck"],
        "cached": False,
        # Carried into the report so a suspect run's advice says so on the page
        # instead of reading as confidently as a clean one.
        "validity": verdict,
        "meta": {"model": llm.default_model(), "deck_hash": dh,
                 "gauntlet_id": gauntlet_id,
                 "validity_version": validity.VALIDITY_VERSION,
                 "generated": datetime.now(timezone.utc).isoformat()},
    }
    cache_dir = _coaching_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{dh}-{gauntlet_id}.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) != 2:
        sys.exit("usage: python3 coach.py <result.json> <deck.dck>")
    print(json.dumps(report(args[0], args[1],
                            refresh="--refresh" in sys.argv), indent=2))


if __name__ == "__main__":
    main()
