# 12 — Deck picker rebuilt as an art gallery

Rebuild `/new` from a text table into an art-forward gallery. Reference: the
"Simulation Parameters" screen Vincent shared 2026-08-01 (a Forge-style deck
grid) — take its *layout ideas*, not its visuals. Everything renders in OUR
design system (`Design System/DESIGN_SYSTEM.md` binds): glass panels over the
backdrop, tokens only, Space Grotesk / JetBrains Mono, one primary.

## Layout (from the reference, translated)

- **Deck grid**: each deck is a tile showing its commander's Scryfall
  `art_crop` with the deck name on a scrim (never text on unscrimmed art).
  Click toggles selection; selected tiles get the cyan interaction treatment,
  not glow (glow is reserved for the primary and live activity).
- **Hover / focus decklist**: hovering (or keyboard-focusing) a tile surfaces
  the full decklist — grouped by type, counts, from the deck file. Must be
  reachable by keyboard, not hover-only, and must not be a panel nested in a
  panel (use a popover layer).
- **Right rail**: the selected decks (2–4) with their art thumbnails and seat
  order, the games-count select (persistent visible label), the runtime
  estimate, and the ONE primary — "Run N games". Primary never disabled;
  under 2 decks the blocker is stated beside it, as today.
- **Filter by color**: WUBRG + colorless filter using `ManaPips` (pips are
  data, never inside a button). Filters the grid by color identity.
- Page still opens with computed prose ("N decks on this engine…") and the
  `?deck=` preselect from the import page still works.

## What the engine must add

`GET /decks` today returns `{file, name, source}` — no commander, so no art.
Extend `_list_decks()` to parse the `[Commander]` section of each `.dck`
(same parsing `combos.parse_dck` already does — reuse it, don't duplicate)
and return `commander: string | null`. The web resolves commander art through
the existing `/cards` path (`lib/cards.ts loadCards` + `art_crop`) — batched,
cached, hotlinked. **Never loop single Scryfall lookups for tiles**, and a
deck whose commander art is unresolved renders a name-only tile, honestly,
not a broken image. (Task 11 fixes the reasons art goes unresolved; this
task must degrade cleanly regardless.)

For the hover decklist the web needs deck contents: add `GET /decks/{file}`
returning the parsed list (name, count, section), or fold contents into an
opt-in query param on `/decks`. Keep the default `/decks` payload small —
the small-payload rule (CLAUDE.md gotcha 4) applies here too.

## Design-system audit points (self-review the diff for these)

- No new CSS files, no inline styles except computed values; all styling in
  `web/app/globals.css`.
- No hardcoded hexes; tokens only. Cyan = interaction (selection), violet =
  secondary. Status shapes unchanged elsewhere.
- One primary on the page: Run. "Import a deck" stays a secondary/link.
- Persistent visible labels on the select and filter; 2px cyan focus ring;
  tiles are real buttons/checkboxes for a11y, `aria-pressed` or checked
  state, decklist popover keyboard-dismissable.
- Fan Content + Scryfall attribution footer at `--ink-4`, never below.

## Acceptance criteria

- [ ] `/new` shows the gallery: art tiles, color filter, hover/focus
      decklist, right rail with selected decks + games select + estimate +
      single live primary. `?deck=` preselect works.
- [ ] Works for bundled AND imported decks (`_find_deck` paths), including
      decks with no `[Commander]` section (name-only tile, no crash).
- [ ] Commander art arrives via one batched `/cards` call per page load;
      warm-cache load makes zero Scryfall network calls (check engine log).
- [ ] Keyboard-only run-through: filter, inspect a decklist, select 3 decks,
      start a run — no pointer needed.
- [ ] `cd web && npm run verify` clean; design-audit items above checked.
- [ ] Engine: `_list_decks` change covered by a smoke-test check;
      `test_adapter.py` still passes.

## Verification

```bash
python3 engine/tests/test_adapter.py
python3 engine/tests/smoke_test.py            # includes /decks shape
cd web && npm run verify
# manual: /new — filter to green, hover a tile for the decklist, select 3,
# confirm rail order and estimate, run 1 game end-to-end
```
