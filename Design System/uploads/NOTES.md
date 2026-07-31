# Sim Lab — UX screen grabs

Captured 2026-07-29 from the production build (`npm run start`), 1512 CSS px wide
at 2x, full page. Real data throughout: 29 decks, 48 result files, live Scryfall
card art. Nothing is mocked.

## The flow, in order

| # | File | Screen | Route |
|---|---|---|---|
| 1 | `01-decks` | Deck picker / new run — the landing screen | `/` |
| 2 | `02-import` | Import a deck, empty state | `/import` |
| 3 | `03-results-index` | All finished runs, filterable | `/results` |
| 4 | `04-run-report` | One run's report: win rates vs baseline, per-game table | `/results/{file}` |
| 5 | `05-replay-tabletop` | Replay theater — top-down table + authoritative event log | `/results/{file}/replay/{n}` |
| 6 | `06-run-in-progress` | Run in flight, playing a buffered game back | `/runs/{id}` |
| 7 | `07-run-queued` | Run queued behind other work | `/runs/{id}` |

Primary path is 1 → 6 → 4 → 5. Screens 3 and 7 are secondary.

## Design observations from these captures

Things I noticed while shooting. Not fixed — raised for the board.

1. **Missing commander avatar.** In `06`, Ur-Dragon's seat has no round art while
   Kilo, Atraxa and Meren all do. `commanderGuess()` failed to resolve a card for
   that deck name, and the fallback is nothing rather than a placeholder.
2. **Unidentified cards read as broken.** In `05` and `06`, tokens and cards with
   no Scryfall type line render as empty dark rectangles. They carry a name in
   9.5px text, which is invisible at tile size, so they look like failed images
   rather than "type unknown".
3. **Header naming is inconsistent.** `04` has the H1 as the matchup ("Drana vs
   Kilo vs Wyleth vs Wilhelt") but the breadcrumb beside the logo still says
   `kilo-helm-final` — the first deck, not the matchup.
4. **A tab row with one tab.** `04` shows a single "Overview" tab; `05` adds
   "Replay". A one-item tab bar is chrome with no function.
5. **Page reads bottom-up when a run finishes mid-playback.** If the sim completes
   while you are still watching, the tabletop stays at the top and the run's H1 and
   "Done" summary render *below* it. The heading for the page ends up near the
   bottom.
6. **Queued state shows progress it does not have.** `07` reports "0 s elapsed" and
   a progress bar already showing a sliver, for a job Forge has not started.
7. **Empty right column on import.** `02`'s "Checks" panel is a tall empty region
   until you type. Roughly half the screen is unused in the default state.
8. **Deck table column widths.** `01` has a wide empty gap between the checkbox
   and the deck name, so the name column starts a fifth of the way across.
9. **Event log leaves a gap.** In `05` the right column stops while the left column
   continues, and the last visible log line is clipped mid-word.

## Worth knowing for design decisions

- **The table is inference, not a read.** Forge logs cards *leaving* the
  battlefield and never entering, so board membership is reconstructed at ~83–86%
  exit-match accuracy. The note under the table says so and should stay: the event
  log is the record.
- **Card art is hotlinked from Scryfall**, never rehosted — a legal constraint, not
  a technical one. Same for the Fan Content notice in the footer.
- **Pod size drives everything.** Two decks is ~2.5 s/game, four is 32–52 s. Any
  design that encourages four-deck gauntlets is designing for a multi-minute wait.
- There is **no feedback capture** anywhere in the product yet.
