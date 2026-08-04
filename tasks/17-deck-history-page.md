# 17 — A deck's own analysis/history page

Every analysis surface today (Overview, Telemetry, Coaching, and task 16's
win-method rollup) is scoped to **one run**. A deck that's been sim'd ten
times has ten disconnected reports; nothing says "here's everything we know
about this deck across every gauntlet it's played." Give each deck a page of
its own: a recall list of the runs it's appeared in, plus whatever stands out
once you look across all of them together.

**Depends on:** task 12 (`/decks` returning commander, needed for the header
art) and benefits from task 16 landing first (the win-method rollup is one of
the things this page aggregates) — not a hard blocker, but do 16 first if
both are open.

## Deck identity — read this before writing the query

A deck is identified by its **file**, not its display name.
`_import_deck()` already hashes content into the filename
(`{slug}_{digest}.dck`) specifically because two decks can share a name
(CLAUDE.md gotcha / the comment at `mtg_engine.py` `_import_deck`). This page
must key history lookups on the exact deck file, matching runs whose
`meta.decks` contains that filename. **Do not group by display name** — two
different lists that happen to both be called "Kilo Helm" are two different
decks, and conflating them would silently blend unrelated performance data.
A consequence: if a user tweaks a decklist and re-imports it, they get a new
file and a fresh history, not a continuation of the old one. That's correct
given the current identity model — don't try to paper over it here; if
tracking edits-of-a-deck as one lineage is wanted later, that's a separate,
bigger task (deck identity would need to change, which ripples into
`_import_deck`, `/decks`, and every result's `meta.decks`).

## What to build

1. **Route**: `/decks/{file}/history` (or fold into a `/decks/{file}` page if
   one doesn't exist yet — check before adding a second route for the same
   deck).
2. **The recall list**: every run this deck file appears in. `GET /results`
   already returns a lightweight index with `decks: string[]` per entry
   (`web/app/results/page.tsx` already filters this client-side via `?q=`) —
   reuse that same filter client-side rather than adding a new endpoint,
   unless the index has grown large enough that shipping the whole thing to
   filter one deck is wasteful (check the actual `/results` payload size
   before deciding; CLAUDE.md gotcha 4's small-payload rule applies here). Each
   row links straight into that run's Overview, same as `/results` today.
3. **Cross-run rollup** — computed from each matching run's already-cached
   per-run reports, not recomputed from raw event logs:
   - Win rate for this deck across all its runs, shown beside the even-seats
     baseline the same way the per-run Overview does it — an aggregate 20%
     is exactly as meaningless as a single-run 20% without that baseline.
   - Win-method distribution rolled up across runs (task 16's per-run
     `summary.methods`, summed), so "how does this deck usually win" is
     answerable at a glance.
   - Telemetry status trend, if telemetry (task 02) has been computed for
     enough of these runs — e.g. "healthy in 6 of 8 measured runs" — not a
     new metric, just the existing per-run `status` tallied.
   - Combo assembled-vs-converted, summed across runs (task 01/`analysis.py`
     already computes this per run).
4. **"Interesting findings" — surface outliers, don't invent new metrics.**
   This is a highlight reel over data that already exists per run, not a new
   analysis engine:
   - Fastest win / latest loss (by ended-turn) across the deck's runs.
   - The run where the deck most over- or under-performed its baseline.
   - Any combo that has assembled but never converted across every run it
     appeared in (this is exactly `analysis.py`'s `not_assembled` /
     `assembled_not_fired` reading, just noticed across runs instead of one).
   - A telemetry metric that went from healthy to cold (or vice versa)
     between two runs, if there are enough runs to compare.
   Cap this to a handful of call-outs — a wall of every possible superlative
   is not a highlight, it's the same table again. If nothing stands out (too
   few runs, or everything is unremarkable), say that plainly rather than
   manufacturing a finding.
5. **Cheap to compute.** Don't fetch every full result file to build this
   page — per-run analysis/telemetry are already cached on disk beside their
   results (`analysis.py`'s `analysis_<file>` cache, task 02's telemetry
   route). Read those caches; only fall back to computing a run's report live
   if it's never been computed, same as the existing per-run pages already
   do.

## What NOT to build

- No deck-lineage tracking across edits (see "Deck identity" above) — out of
  scope, bigger task if wanted.
- No new per-game metrics — everything here is a rollup or a call-out over
  numbers `analysis.py`/`deck_telemetry.py` already produce.
- No cross-**deck** comparison ("how does this deck compare to that one") —
  this page is about one deck's own history, not a leaderboard.

## Acceptance criteria

- [ ] `/decks/{file}/history` lists every run containing that exact deck
      file, each row linking to that run's Overview.
- [ ] Aggregate win rate shown beside the even-seats baseline, computed only
      from runs where this deck actually played (not runs where it didn't
      appear).
- [ ] Win-method distribution and combo assembled/converted totals rolled up
      across the deck's runs, sourced from cached per-run reports.
- [ ] At least one "interesting finding" call-out renders when the deck has
      enough runs to support one, and the page says plainly when it doesn't
      (fewer than ~3 runs, say) rather than forcing a finding.
- [ ] Two decks sharing a display name but different files show separate,
      uncombined histories — verified with two fixture decks named the same.
- [ ] Page reads only cached per-run reports plus the existing `/results`
      index — no new whole-run (`api.result(file)`) fetches, per CLAUDE.md
      gotcha 4.
- [ ] `cd web && npm run verify` clean; no new CSS file; reuses `.telet`/`.st`
      conventions; zero or one `.btn.pri` (linking into a run is navigation,
      not a new primary action).

## Verification

```bash
python3 engine/tests/test_adapter.py
cd web && npm run verify
# manual: pick a deck that has appeared in 3+ existing runs, open its history
# page, confirm the run list matches what /results?q=<deck> shows, and that
# the rollups match hand-summing the individual runs' Overview/Telemetry pages
```
