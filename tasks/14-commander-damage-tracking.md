# 14 — Live commander damage on the replay

Commander damage only shows up today as the post-hoc win reason: `replay.ts`
(`decidedBy`, around line 479) detects `"damage from generals"` in the loss
line and names *one* source card at the moment the game ended. Nothing shows
the running per-opponent total as the game plays out, so a viewer watching a
close multiplayer game can't tell someone is one hit from dying to commander
damage until Forge announces it.

## What Forge's log gives us

Individual damage events (`forge_log_adapter.py` `"damage"` action, parsed by
`parseDamage()` in `replay.ts`) do **not** tag whether a hit was combat damage
from a commander — that information only appears at death, in the loss line's
`"damage from generals"` phrase. To build a running total we have to
cross-reference each damage event's `source` against the known commander name
for that source's controller, not read a per-event "this was commander damage"
flag that doesn't exist.

- Each deck's commander is already known — `/decks` returns it (task 12), and
  `combos.parse_dck` extracts it server-side today.
- A damage event's `source` is a card name with no controller attached; match
  it against the seat whose commander shares that name, not by proximity or
  ordering.
- **Partner commanders / Backgrounds**: a seat can have two commander names.
  Track both, and keep the running total per (commander name → victim) pair,
  not per (seat → victim), so a viewer can see partner A did 12 and partner B
  did 9 rather than a single blended 21.
- This running total is inference layered on inference (it depends on
  `parseDamage`'s regex plus a name match), same honesty posture as board
  reconstruction. The authoritative "who actually lost to commander damage"
  signal stays the loss-line detection already in `decidedBy` — never let the
  running counter override that at game end, only complement it.

## What to build

1. **`web/lib/replay.ts`**: a `commanderDamage(flat, commanders)` helper that
   walks the flattened event list once, and for each `damage` event whose
   `source` matches a known commander name, accumulates
   `{ [commanderName]: { [victim]: total } }` up to the current playback
   index (so it's replayable at any scrub position, consistent with how the
   rest of the theater works — no full-game precompute that ignores the
   scrubber).
2. **Replay UI**: a small per-player commander-damage row (JetBrains Mono
   figures) beside the existing life total, showing damage taken from each
   opposing commander that has dealt any. Zero-total opponents don't get a
   row — don't pad the display with 0s for commanders that never connected.
3. **Lethal-range cue**: when a running total for a (commander, victim) pair
   reaches 21, that pair's badge gets the same "about to lose" treatment life
   total gets at 0-adjacent — reuse the existing status-shape language
   (CLAUDE.md: status is shape, not hue), don't invent a new color meaning.
4. **Honesty note**: extend the existing "board is inference" note (or add a
   sibling one beside the commander-damage row) stating this total is derived
   by name-matching damage sources to known commanders, not read from a
   structural field Forge provides.

## Acceptance criteria

- [ ] `test_adapter.py` gains fixture coverage: a game where a commander deals
      damage across multiple turns, confirm the running total is correct at
      an arbitrary scrub position (not just at game end).
- [ ] Partner-commander deck (two named commanders) tracked as two separate
      totals against the same victim.
- [ ] Replaying the fixture shows the commander-damage row updating turn by
      turn, and it matches the existing `decidedBy` win-reason string at the
      final event if the game ended by commander damage.
- [ ] No commander-damage row rendered for an opponent at 0 — verified by
      inspecting a fixture where one seat never took commander damage.
- [ ] `cd web && npm run verify` clean; no new CSS file; badge uses tokens
      and the existing `.st` shape language.

## Verification

```bash
python3 engine/tests/test_adapter.py
cd web && npm run verify
# manual: replay a fixture game with commander damage, scrub to mid-game and
# confirm the row shows a partial total, scrub to the end and confirm it
# matches the win reason already shown today
```
