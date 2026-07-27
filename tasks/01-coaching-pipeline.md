# 01 — AI deck coaching pipeline

**Why:** This is the flagship feature. Without it Sim Lab is a simulation viewer.
Source of truth: `frontend_architecture.md` §6 and `engine/SIM_CALIBRATION.md`.

**Size:** the largest task here. Ship it in the four stages below — each is
independently useful and independently verifiable.

---

## Non-negotiables

Read `engine/SIM_CALIBRATION.md` in full first. These are enforced **in code**,
not left to the model:

- **Never display a raw win rate without its archetype baseline.** Engine/spell
  decks average 12%; creature-forward decks average 38%. A 20% engine deck is
  *above* average and must read that way.
- **Seat rotation always.** Reject any run that isn't seat-rotated as a coaching
  input; single-seat numbers are not comparable.
- **Voltron/politics decks are labelled "sim = floor."** The AI can't pilot
  politics or protection timing.
- **Telemetry sits next to outcomes.** A deck can lose sims and be healthy.
- Every recommendation carries an evidence tag: `[sim-evidence]`,
  `[consensus]`, or `[theory]`. No untagged claims.

**Cost discipline** (`frontend_architecture.md` §2): exactly **one** LLM call per
`(deck_hash, gauntlet_id)`, ~4k in / 1k out on a small-model tier, then cached
forever. Retrieval, telemetry, and sim results are all zero-token. If you find
yourself making a second call per deck, stop and reconsider.

---

## Stage 1 — make telemetry importable and structured

`engine/deck_telemetry.py` currently only prints (59 lines, `main()` only). The
coach needs data.

- Add `compute(result: dict, deck_substring: str, watch: list[str] | None = None) -> dict`
  returning a stable schema. Keep `main()` working as a CLI wrapper over it.
- Suggested shape (adjust to what the events actually support — verify against
  the fixture, don't invent metrics you can't measure):

```python
{
  "games": 16, "deck": "kilo_helm_final.dck", "player_key": "Ai(1)-Kilo Helm Final",
  "commander": {"name": str, "cast_rate": 0.95, "median_turn": 4},
  "engine": {"charge_events_per_game": 6.9, "proliferate_per_game": 7.1},
  "watched": [{"name": "Lux Cannon", "events_per_game": 2.7, "status": "partial"}],
  "deaths": {"by_source": [{"source": "Kambal", "damage": 14}], "median_turn": 11},
  "win_rate": 0.203, "wins": 13,
}
```
- `status` per watched card must be derived from a documented threshold, not vibes.
  State the thresholds in a docstring (e.g. `>=2/game healthy`, `>0 partial`,
  `0 cold`) so the UI and the LLM agree.

**Verify:** `python3 engine/deck_telemetry.py kilo_helm` still prints; and
`python3 -c "import deck_telemetry, json; print(json.dumps(deck_telemetry.compute(json.load(open('tests/fixtures/sim_sample.json')), 'kilo'), indent=2))"`
returns populated numbers. Every rate must be reproducible by hand from the fixture.

## Stage 2 — archetype classification and baselines

- New `engine/archetype.py`: `classify(decklist: list[str], commander: str) -> dict`
  returning `{"class": "engine"|"creature"|"voltron"|"politics"|"unknown",
  "baseline": 0.12, "sim_is_floor": bool, "why": str}`.
- Baselines come from the table in `SIM_CALIBRATION.md` — import them from one
  place, don't hardcode duplicates.
- Classification can be simple and rule-based (creature count, mana curve,
  commander-damage cards, counterspell/removal density). **It must explain itself**
  via `why`, because that string is shown to the user and fed to the LLM.
- `"unknown"` is a valid answer. Don't force a class you can't justify.

**Verify:** classify the four decks in the fixture; assert Kilo → `engine`
(baseline 0.12) and Wyleth → `voltron` with `sim_is_floor: true`. Write these as
assertions in `engine/tests/test_archetype.py`.

## Stage 3 — the synthesis call

- New `engine/coach.py` with:
  - `build_context(result, deck_file) -> dict` — assembles sim summary, telemetry
    (Stage 1), archetype + baseline (Stage 2), and the calibration correction
    notes. **Zero tokens.** This is most of the work.
  - `synthesize(context, *, model, api_key) -> dict` — the single LLM call.
  - `report(result_file, deck_file, *, refresh=False) -> dict` — cache-aware entry
    point. Cache key: `sha256(normalized_decklist) + gauntlet_id`. Store under
    `MTG_DATA_DIR/coaching/{key}.json`. A cache hit makes no network call.
- Provider: read `MTG_LLM_API_KEY` and `MTG_LLM_MODEL` from env; default to a
  small/cheap model. **Never commit a key.** If the key is absent, `report()`
  returns `{"ok": false, "reason": "no LLM configured"}` — the endpoint must
  degrade, not crash.
- Output schema (validate it before caching; reject and retry once on malformed):

```python
{
  "verdict": {"headline": str, "prose": str,            # 2-3 sentences, coaching voice
              "win_rate": float, "baseline": float, "sim_is_floor": bool},
  "support_chain": [{"link": str, "status": "running"|"partial"|"cold",
                     "measured": str, "reading": str}],
  "matchups": [{"pod": str, "win_rate": float, "note": str}],
  "changes": [{"action": "add"|"cut", "card": str, "reason": str,
               "evidence": "sim-evidence"|"consensus"|"theory"}],
  "play_guide": [str],
  "meta": {"model": str, "deck_hash": str, "gauntlet_id": str, "generated": iso8601},
}
```
- System prompt requirements: answer only from the supplied context; never restate
  a raw win rate without its baseline; label floor decks; tag every change with
  evidence; if the context doesn't support a claim, omit it. Mirror the discipline
  of the rules-assistant prompt in `frontend_handoff/API_SPEC.md`.
- EDHREC consensus (§6 step 3) is **optional for v1**. Ship sim + telemetry first;
  changes then carry `[sim-evidence]` or `[theory]`. Add `[consensus]` later.

**Verify:** with no API key, `report()` returns the degraded response and makes no
network call. With a key, run it once on a real result and assert the output
validates against the schema, the verdict cites the baseline, and a second call
hits the cache (prove it: no second request, identical `generated` timestamp).

## Stage 4 — API and UI

- `GET /coaching/{result_file}?deck={deck.dck}` — returns a cached report, or
  `{"ok": false, "reason": "not generated"}`. Public read, like other GETs.
- `POST /coaching` `{result_file, deck}` — generates. **Requires an API key** and
  its own quota (suggest `MTG_COACH_PER_HOUR=20`) — it's the only paid-token path
  in the app. Follow the existing pattern in `mtg_engine.py` exactly:
  `_authed()`, `_rate_ok()`, `_deny()`.
- UI: a `Coaching` tab on the run results page. The v3 report wireframe
  (`mockups/simlab_v3_report.html`) already has the target layout — prose lede,
  `.telet` support-chain rows with `.st` dot+word statuses, `.chg` add/cut rows
  with evidence in `.ev2`. **Reuse those classes; add no CSS.**
- Empty state: a `.btn.pri` "Generate coaching report (~$0.01, about 20 s)" —
  descriptive, per the design rules. One primary button on the view.
- Handle `RateLimited` (`web/lib/api.ts`) the way the other pages do.

**Verify:** `cd web && npx tsc --noEmit` clean; `npx next build` succeeds; the tab
renders a cached report; the generate button is the only `.btn.pri` on the page;
unauthenticated `POST /coaching` returns 401.

---

## Acceptance criteria

- [ ] `deck_telemetry.compute()` returns structured data; CLI still works
- [ ] `archetype.classify()` returns class + baseline + `why`; tests assert Kilo=engine, Wyleth=voltron floor
- [ ] Exactly one LLM call per `(deck_hash, gauntlet_id)`; cache hit makes zero calls
- [ ] No API key configured → graceful degraded response, no crash
- [ ] Output validated against the schema before caching
- [ ] Every displayed win rate is accompanied by its baseline
- [ ] Floor decks labelled "sim = floor"
- [ ] Every recommendation carries an evidence tag
- [ ] `POST /coaching` is authenticated and quota'd; `GET` is public
- [ ] Coaching tab obeys the design rules (one `.btn.pri`, no new CSS, prose lede)
- [ ] `test_adapter.py` passes, `tsc` clean, `board.py` accuracy unregressed

## Out of scope

Streaming the report token-by-token; multi-model comparison; coaching on
non-rotated runs; anything that makes a second LLM call per deck version.
