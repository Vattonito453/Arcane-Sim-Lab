# 16 — Tie post-run deck analysis together

**Read this before scoping work here — most of "expose analysis after a
sim" already shipped.** `web/app/results/[file]/page.tsx` already renders win
rate vs. the even-seats baseline and combo assembly/conversion; the Telemetry
tab (task 02) renders win-condition support metrics; the Coaching tab (task
01) renders a verdict against the archetype baseline with evidence-tagged
suggestions. `engine/analysis.py` computes per-game `win_method` (spell /
combat / commander / poison / concession / etc.) and rolls it up into
`summary.methods` — but that rollup is the one piece of the existing
`AnalysisReport` payload with **no UI at all** today; only the per-game
annotation (`decidedBy … — won by X`) reads it, one game at a time.

This task closes the two real gaps, not a re-do of 01/02/12.

## Gap 1 — the win-method distribution has no summary view

`analysis.py`'s `summary.methods` (e.g. `{"combat damage / life loss": 11,
"commander": 3, "spell": 2}`) is computed and shipped in the API response
today (`GET /analysis/{file}`) and never rendered as a rollup anywhere. Add
it to the results overview page as a small table or bar row beside the
existing win-rate section — same `.telet`/`.st` markup conventions as the
telemetry tab, no new chart library, no new CSS file. Label it honestly: this
is "how games ended," not "why a deck won," and a `not recorded` bucket
(older 2-player logs that only log the winner) must render as its own row,
never get silently dropped from the total.

## Gap 2 — the three analysis surfaces are hard to find as *one* answer

A user who just finished a run and asks "how did my deck do" has to already
know to click through Overview → Telemetry → Coaching separately; nothing
on the overview page tells them Telemetry and Coaching exist beyond the tab
row itself, and the tab row gives no hint of *what's in* each tab. Fix the
discoverability, not the content:

- The Overview page's lede (the computed prose line at the top) should name,
  in passing, what a viewer can go check next — e.g. mention telemetry
  status or the coaching verdict inline if already computed and cached, with
  a link into that tab, the same way the combo section already links out to
  the replay theater per game.
- Do not merge Telemetry and Coaching into Overview. They're intentionally
  separate views with separate concerns (per tasks 01/02's own scoping) —
  the fix here is wayfinding between them, not consolidation.

## What NOT to build

- No new metrics beyond the win-method rollup — that data already exists in
  `analysis.py`; this task surfaces it, it doesn't compute anything new.
- No redesign of the Telemetry or Coaching tabs themselves.
- No cross-run comparison ("how did this deck do across all its runs") —
  that's a bigger feature (a deck-level history view) and now has its own
  spec: [17-deck-history-page.md](17-deck-history-page.md). This task's
  win-method rollup is exactly what that page aggregates across runs, so
  land this one first.

## Acceptance criteria

- [ ] The results overview page renders `summary.methods` as a labeled
      breakdown (count and share per method), including a `not recorded`
      row when present, sourced from the existing `/analysis/{file}` payload
      already fetched on that page (`an` state) — no new endpoint.
- [ ] The lede or a line near it references telemetry/coaching status when
      available, with a working link into each tab.
- [ ] Zero new `.btn.pri` — this is a report addition, not a new action.
- [ ] No new CSS file, no inline styles except computed percentages; reuses
      `.telet`/`.st` conventions.
- [ ] `cd web && npm run verify` clean; `test_adapter.py` passes.

## Verification

```bash
python3 engine/tests/test_adapter.py
cd web && npm run verify
# manual: open a real run's /results/<file>, confirm the win-method
# breakdown sums to the game count shown elsewhere on the page, then follow
# the new link(s) into Telemetry and Coaching and confirm they land on the
# right deck's tab
```
