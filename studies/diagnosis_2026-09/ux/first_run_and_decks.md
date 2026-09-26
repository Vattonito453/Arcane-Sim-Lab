# first_run_and_decks scratch notes (2026-09-26)

Evidence gathered on http://35.192.104.34 at 1440x900 and 375x812.

- /engine/sim-status: last 4-deck 8-game job elapsed 3356 s (56 min); server typical_seconds [1292, 3212].
  /new client estimate for same = 7.5 + 8*52 = 423 s ("about 7 min"). Home says "four decks ~ 8 min for 16".
- /new with 4 decks, 16 games -> "about 14 min" shown. CLAUDE.md typical 40-105 min.
- engine/mtg_engine.py:474-476 rounds requested up to a multiple of seats: 1 game x 4 decks -> 4 played.
- /engine/results: 46 runs; 25 clean, 12 polluted, 9 suspect.
- shortName() first-word split leaves commas: "Kess," "Kilo," "Deadpool," "Tergrid," and "The" (Unbeatable Squirrel Girl).
  Appears on home recent sims, /results rows, run page H1 + seat labels, report H1.
- Report for d0eb966b8d33: game 6 Duration "NaN:NaN".
- Deck page Skrat's Revenge: 75 card rows, 92 px each, page 9,370 px tall at 900 px viewport. Mana costs raw "{1}{G}{G}{G}".
- Gallery pip size 13 px (DS says black skull vanishes below ~20 px). Tergrid MDFC tile has no art.
- Import: 3 of 4 source tabs "coming soon". Lede promises suggested fixes that no UI implements.
- No per-route <title>; no favicon; backdrop PNG 2.65 MB on every page.
- In-progress runs are surfaced nowhere except /runs/[id].
- Archidekt deck page: commander art header, Bracket, tags, View as / Group by / Sort by, Playtester top right.
  Archidekt search tile: art, colour bar, name, "Commander - Bracket: Upgraded (3)", views, updated.
- Moxfield blocked by its loading gate in the pane (not bypassed).
