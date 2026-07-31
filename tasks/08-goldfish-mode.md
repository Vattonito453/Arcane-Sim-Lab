# 08 — Goldfish mode (solo deck speed & consistency)

Goldfishing = playing a deck against no opposition to measure its raw speed
and consistency: when does the commander land, when does the combo assemble,
what turn does it present lethal, which cards rot in hand. Deck builders do
this by hand constantly; we can do it 50 games at a time with real rules
enforcement.

**Legal guardrail:** goldfish mode is AI-piloted batch simulation displayed
as replays/telemetry, exactly like the gauntlet. An *interactive* goldfish
where the user plays their own hands is a gameplay client — permanently out
of scope (CLAUDE.md legal). Do not build a "step my own turns" affordance.

## v1 — zero new infrastructure (ship first)

Forge needs opponents, so give it inert ones: generate a **dummy pacifist
deck** (a legal Commander deck that does nothing — a defensive commander and
98 basics/do-nothing permanents; worst case it plays lands and passes).
Run 2-seat sims: target deck vs dummy.

- `engine/goldfish.py` — builds the dummy deck once, runs
  `run_sim.py --decks <target> <dummy> --games N`, then computes per-game:
  commander cast turn, first combo-piece and full-combo turn (from
  `combos.py` lines), turn lethal damage was first presented on board
  (sum of attacker power vs 40), cards never cast (dead weight), curve
  execution (mana spent / mana available by turn).
- Seat rotation still applies (Forge seat bias exists even 2-seat) — reuse
  `--rotate`.
- Honesty note in UI: goldfishing measures **speed and consistency, not
  strength** — no interaction, no removal faced. Show it beside gauntlet
  results, never as a substitute.

## v2 — after task 07 Stage 0 (shim exists)

Replace the dummy deck with a shim `PassiveController` seat: never mulls,
never casts, never blocks. Cleaner (no dummy-deck artifacts in logs, no
accidental interactions) and enables 1-seat "true goldfish" if Forge's Match
permits it; otherwise keep the passive seat.

## UI (web/app/goldfish or a tab on the deck page)

- Opens with computed prose (design system rule): "Kilo goldfishes a turn-6
  Dawnsire; the commander lands on turn 3.4 on average; 7 cards never left
  hand across 50 games."
- Timeline strip T1–T12: median mana spent, commander cast marker, combo
  assembled marker, lethal-on-board marker.
- Dead-cards list (never-cast rate per card) — directly actionable for cuts.
- All styling from `web/app/globals.css`; no new CSS files.

## Acceptance criteria

- [ ] `python3 engine/goldfish.py <deck.dck> --games 20` produces a goldfish
      JSON with the metrics above; runs on the existing worker path
      (jobqueue job type `goldfish`).
- [ ] Dummy deck is validated legal by `convert_decklist.py` and committed
      to `engine/decks/`.
- [ ] UI tab renders from a small payload endpoint (follow the
      runSummary/runGame pattern — no whole-result fetches).
- [ ] Honesty note present; goldfish numbers visually distinct from gauntlet
      win rates.
- [ ] test_adapter still passes; `npm run verify` clean.

## Verification

```bash
python3 engine/goldfish.py engine/decks/kilo_helm_final.dck --games 4
python3 engine/tests/test_adapter.py
cd web && npm run verify
```
