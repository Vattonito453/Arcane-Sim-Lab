# 02 — Telemetry in the UI

> **STATUS 2026-08-31: SHIPPED. Do not start this task.**
> `deck_telemetry.compute()` exists (the module is 263 lines, not the 59 this
> spec describes), the `/results/{file}/telemetry` endpoint is live, and the
> page renders win-con support rows, engine metrics and a damage-by-source
> table. The text below is kept for its constraints, which still bind, and for
> its acceptance criteria, which the shipped page should be re-read against.
> Two real gaps remain and are NOT this task: the watched-cards rows populate
> only from a hand-typed `?watch=` URL with no UI control, and the engine
> metrics are hardcoded to one archetype (charge counters, proliferate) so they
> render for every deck regardless of what it does.

**Why:** `engine/deck_telemetry.py` measures whether a deck's plan actually fired
and nothing in the product shows it. `engine/SIM_CALIBRATION.md` step 3 says a win
rate without function telemetry is unreadable — a deck whose machinery runs but
loses to archetype bias is probably fine; a deck whose machinery never fires is
broken. Same number, opposite verdict.

**Depends on: task 01 Stage 1.** This spec renders `deck_telemetry.compute()`. That
function does not exist yet — the module is 59 lines with a print-only `main()`.
Do not start here until Stage 1 of `01-coaching-pipeline.md` has landed and
`compute()` returns the structured schema with its documented status thresholds.

**Size:** small — one endpoint, one route, no new metrics.

**Done means:** the shared definition of done in `tasks/README.md` applies in full,
plus the acceptance criteria below.

---

## Constraints

- **One source of truth for status.** `compute()` already derives
  `healthy`/`partial`/`cold` from documented thresholds (01 Stage 1). The page maps
  those strings to `.st` classes and nothing more. Never recompute a threshold in
  TSX — the UI and the coach must agree.
- **Compute server-side.** A telemetry pass reads whole result files. The browser
  must not fetch them: `api.result(file)` is ~235 KB gzipped and CLAUDE.md gotcha 4
  exists because pages kept reintroducing whole-run fetches. Add an endpoint.
- **String matching is the measurement, and the UI must say so.** Telemetry counts
  substring hits in `event.raw` ("charge counter", "proliferate", watched card
  names). That is a real signal, not a rules-level read. Label it as event-log
  matches, per CLAUDE.md's "state uncertainty plainly".
- **Design rules** (`mockups/design_principles.md` Part 3): sentence case, prose
  lede computed from real data, `.st` dot + word for status, all numerals `.mono`,
  no pills, no emoji, no new CSS file. The telemetry view is a report, not an
  action — it should carry **zero** `.btn.pri`. One is the ceiling, not a quota.

---

## Stage 1 — `GET /results/{file}/telemetry`

Add the route in `engine/mtg_engine.py` beside the existing
`/results/{file}/summary` branch (currently around line 490, inside the
`parts[0] == "results"` block).

- Signature: `GET /results/{file}/telemetry?deck={substring}&watch=a|b|c`
  - `deck` — required. The substring `compute()` matches against
    `meta.decks`. Reject a missing or empty `deck` with 400.
  - `watch` — optional, pipe-separated, same convention as `GET /cards?names=a|b|c`.
- Implement a `_read_result_telemetry(name, deck, watch)` helper next to
  `_read_result_summary()`. It calls `_read_result(name)` — which already holds the
  path-traversal guard (`name != Path(name).name or not name.endswith(".json")`) —
  then `deck_telemetry.compute()`. **Do not open files directly from the handler**;
  the guard must stay on the single path.
- Public read, like every other GET. It is derived from an immutable file and is
  deterministic, so send the same `IMMUTABLE` cache header the sibling routes use
  (`public, max-age=31536000, immutable`). If `watch` is part of the key, note that
  it is already part of the query string, so caching stays correct.
- No deck matches the substring → 404 `{"error": "..."}`, matching how
  `FileNotFoundError` and `IndexError` are already surfaced in that block.
- Add `TelemetryReport` to `web/lib/types.ts` mirroring the Stage-1 schema exactly,
  and `api.runTelemetry(file, deck, watch?)` to `web/lib/api.ts` using the existing
  `get<T>()` helper with `{ cache: "force-cache" }`, as `runSummary` does.

**Verify:** with the API running on 8484 against a real result,

```bash
curl -s "http://127.0.0.1:8484/results/<file>.json/telemetry?deck=kilo" | python3 -m json.tool
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8484/results/<file>.json/telemetry"          # 400
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8484/results/<file>.json/telemetry?deck=zzz" # 404
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8484/results/../../etc/passwd/telemetry"     # not 200
curl -sD- -o /dev/null "http://127.0.0.1:8484/results/<file>.json/telemetry?deck=kilo" | grep -i cache-control
```

First call returns populated numbers; the last prints the immutable header.

## Stage 2 — the Telemetry tab

- New route `web/app/results/[file]/telemetry/page.tsx`, a client component in the
  shape of `web/app/results/[file]/page.tsx` (same `useParams` + `useEffect` fetch
  + `RateLimited` handling).
- Wire the tab row in **both** files. `results/[file]/page.tsx` line 203 currently
  passes `tabs={[{ label: "Overview", href: "#", on: true }]}`; make it
  `[{ label: "Overview", href: `/results/${enc}`, on: true },
    { label: "Telemetry", href: `/results/${enc}/telemetry` }]`
  and the mirror image on the new page. Do the same in that file's error and
  loading returns (lines 140 and 164) so the tab row does not vanish mid-load.
- Deck selection: a run has 2–4 decks. Read `meta.decks` from the telemetry
  response (or a `runSummary` call) and render a `.sel` control — the class already
  exists in `globals.css`. Default to `meta.decks[0]`. Put the selected deck in the
  URL as `?deck=` so the view is addressable (Part 3 rule 10, "every state
  addressable").
- Body layout, straight from `mockups/simlab_v3_report.html` lines 355–395:
  - `.sh` section header "Win-condition telemetry" with a `.sh .meta` count.
  - `.sdesc` one line of what the table measures.
  - `table.telet` rows: `td.nm` metric name with a `<small>` clarifier,
    `td.val` the figure (`6.9/g`, `T4 med`), `td.stc` a
    `<span className="st ok"><i />Healthy</span>` — `ok`/`warn`/`bad` from
    `compute()`'s `status`, worded "Healthy" / "Partial" / "Never fired".
  - A closing `.note` naming the measurement method and the game count.
- Prose lede (`.lede`) computed from the response, not hardcoded. Something in the
  shape of: commander cast in N of M games at median turn T; the engine metric at
  X/game; K of J watched cards cold. If the run is unrotated
  (`meta.source !== "rotated"`), say so in the lede — SIM_CALIBRATION rule 1.
- Death causes: render `deaths.by_source` as a second `.telet` table under its own
  `.sh`, or as the right column of a `.cols` grid beside the support chain. `.cols`
  already exists (`globals.css` line 147).
- No inline styles. This view has no bars, so the "computed percentages" exemption
  does not apply — expect zero `style=` attributes.

**Verify:**

```bash
cd web && npx tsc --noEmit          # clean
cd web && npx next build            # succeeds
grep -c "btn pri" app/results/\[file\]/telemetry/page.tsx      # 0
grep -n "style=" app/results/\[file\]/telemetry/page.tsx       # no matches
git status --porcelain web/ | grep '\.css$'                     # only globals.css, if anything
```

Then load `/results/<file>/telemetry?deck=<deck>` and confirm: the tab row shows
Overview + Telemetry with Telemetry active, the lede is real prose with real
numbers, every figure is monospaced, and switching the deck selector changes the
URL and the table.

## Stage 3 — the honest edges

- **Fixture trap, verify this explicitly.** `engine/tests/fixtures/sim_sample.json`
  carries `summary.games: 16` but contains only **2** games (its `meta.fixture`
  field says so). Per-game rates must divide by the games actually present in the
  file, and the UI must label the denominator it used. If the page prints "6.9/game
  across 16 games" from a 2-game payload, it is lying. Also note the summary's
  `wins`/`win_rates` keys carry **no** `Ai(n)-` prefix while `game.players` keys do
  — join on the stripped name (`stripAi()` in `web/lib/format.ts`).
- Empty state: a deck with no matching events → the table still renders its rows
  with `0/g` and `.st.bad` "Never fired", plus a `.note` explaining that zero can
  mean the card was never drawn as easily as never cast. Do not render an empty
  page.
- Rate limiting: reads are capped at `MTG_READ_PER_MIN` (240 default). Catch
  `RateLimited` and show the wait the way `results/[file]/page.tsx` lines 148–155
  do.

**Verify:** point the page at a run whose selected deck has no watched-card hits
and confirm the zero rows read as "Never fired" with the caveat note, and that a
telemetry response derived from the 2-game fixture reports 2 as its denominator:

```bash
cd engine && python3 -c "
import json, deck_telemetry as t
r = t.compute(json.load(open('tests/fixtures/sim_sample.json')), 'kilo')
print(r['games'])   # must be 2, not 16
"
```

---

## Acceptance criteria

- [ ] `GET /results/{file}/telemetry?deck=` returns `compute()` output; 400 without
      `deck`, 404 for an unmatched deck, immutable cache header on success
- [ ] The path-traversal guard is still the only way in — the new helper calls
      `_read_result()`, it does not open files itself
- [ ] `TelemetryReport` in `types.ts` matches the Stage-1 schema; `api.runTelemetry()` added
- [ ] Telemetry tab on the run results page; tab row present on the Overview,
      loading, and error states of both pages
- [ ] Deck selection reflected in the URL (`?deck=`)
- [ ] Statuses come from `compute()`'s `status` field, never recomputed in TSX
- [ ] `.telet` + `.st` markup reused verbatim; no new CSS file; no inline styles
- [ ] Zero `.btn.pri` on the telemetry view
- [ ] Prose lede computed from the response; unrotated runs say so
- [ ] The displayed game count is the count actually in the payload (2 for the fixture)
- [ ] A `.note` states that counts are event-log substring matches
- [ ] `RateLimited` handled like the sibling pages
- [ ] `test_adapter.py` passes, `tsc` clean, `board.py` accuracy unregressed

## Out of scope

New telemetry metrics (that is 01 Stage 1); charts or sparklines; comparing two
runs side by side; a telemetry view that is not scoped to one deck; caching
telemetry to disk — it is cheap to recompute and the responses are already
immutable-cached at the edge.
