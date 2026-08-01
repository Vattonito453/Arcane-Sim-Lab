# 08 — Goldfish mode (solo playtest sandbox + speed telemetry)

Goldfishing = playing a deck with no opposition to feel its speed and
consistency. Two complementary deliverables share this task:

- **Part A — the playtest sandbox** (Vincent's ask, ship first): load ONE
  deck, draw hands, play cards. The user pilots; there are no rules, no
  opponent, no engine. Moxfield/Archidekt-style.
- **Part B — automated goldfish telemetry** (later): AI-piloted batch stats
  (commander cast turn, combo-assembly turn, dead cards) once task 07's shim
  offers a passive opponent seat.

## The legal line (read before building)

A solo, rules-free sandbox is NOT the banned "gameplay client." The banned
category is an *adjudicated Magic experience* — rules enforcement, an
opponent, an outcome — which competes with Arena. The sandbox has none of
those: the user is the rules engine, same as goldfishing at a kitchen table.
Moxfield, Archidekt, and TappedOut have shipped exactly this for years within
the tolerated deck-tool posture. The bright line, in order of tripwires:

1. **No opponent** — not AI, not another human, not a scripted one.
2. **No rules adjudication** — the app never enforces legality, resolves a
   spell, or applies a trigger. It moves cards where the user drags them.
3. **No win/loss** — nothing declares an outcome, ever.

Any feature request that crosses one of these goes back through legal review.
Forge is not involved anywhere in Part A, so no GPL surface either.

## Part A — playtest sandbox (web-only, no engine changes)

Route: `/playtest/[deck]` (or a tab on the deck page).

- Client-side shuffle (Fisher–Yates), draw 7, London mulligan (draw 7,
  bottom N), free first mulligan toggle for Commander.
- Zones: hand, battlefield, graveyard, exile, library count, command zone
  (commander starts there; click to "cast" = move to battlefield — a zone
  move, not a rules action).
- Interactions: drag between zones, tap/untap on click, next-turn button
  (untap all + draw 1), life counter, generic +1/+1-style counter badges on
  cards, "add token" as a blank counter card, reset/reshuffle.
- Card images hotlinked from Scryfall per existing etiquette (`lib/cards.ts`
  already resolves them for replays — reuse it).
- Design system rules apply: opens with computed prose ("Drawing from Kilo's
  99 — 36 lands, 3.2 average mana value…"), one primary action, all styling
  in `web/app/globals.css`, no new CSS files.
- State is ephemeral client state — no API, no persistence, no job queue.

## Part B — automated goldfish telemetry (after task 07 Stage 0)

The shim provides a passive opponent seat (never mulls, casts, or blocks),
so Forge can run N solo-ish games with full rules enforcement. Compute per
game: commander cast turn, first combo-piece / full-combo turn (from
`combos.py` lines), turn lethal is first on board, never-cast cards, curve
execution. Surface next to the sandbox with the honesty note: goldfish
numbers measure **speed and consistency, not strength** — no interaction
faced. (An interim dummy-pacifist-deck version is possible without the shim
but produces log noise; only build it if Part B is wanted before 07 lands.)

## Acceptance criteria

- [ ] Part A: import a deck, open playtest, draw/mull/play/next-turn through
      a full goldfish without touching the server after initial deck load.
- [ ] The three tripwires are respected — code review the diff specifically
      for accidental adjudication (e.g. auto-tapping lands for costs: no).
- [ ] Works with the existing deck list (both `engine/decks/` bundled and
      imported `MTG_DATA_DIR/decks` decks).
- [ ] Scryfall images hotlinked, batched lookups via the existing cache path,
      Fan Content + Scryfall attribution footer present.
- [ ] `cd web && npm run verify` clean; no new CSS files; design-principles
      audit (no ALL-CAPS labels, one primary, no emoji).
- [ ] Part B (when built): metrics JSON + UI panel with the honesty note;
      adapter tests still pass.

## Verification

```bash
cd web && npm run verify
# manual: /playtest/<deck> — draw, mulligan to 5, play a land, tap it,
# next turn, confirm library count and graveyard drag work
```
