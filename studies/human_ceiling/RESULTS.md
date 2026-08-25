# Human ceiling study — results

**Status: COMPLETE 2026-08-24. 8 pods x 4 rotated sim games (32 games), 8
video traces (12 human games).**

All rounds are table rounds (the winner's own elapsed turns). Stock Forge =
`--agent shim` without plans: stock `PlayerControllerAi` decisions, zone-truth
logs, 900 s clock, 4 games seat-rotated per pod, one JVM at a time.

## Per-pod comparison

| Video | Human winner (round, method) | Forge wins (of 4) | Forge win rounds | Winner agreement |
|---|---|---|---|---|
| n7WpsqsZtdQ (pilot) | Magda R5 and ~R6, Portal to Phyrexia toolbox | magda 3, selvala 1 | 10, 11, 11, 12 | YES (deck), NO (line: combat, never Portal) |
| sZA0KqXCGrY | Ral **R2** storm (Grapeshot, Breach loop; mull to 4) | natalie_magda 3, ashton_bluefarm 1; **ral 0** | 9, 9, 10, 10 | **NO.** Forge cannot pilot storm; the deck the human won with never wins in sim |
| 2iA_Jt0d6sM | Derevi R5 (Chord into Nadu, Emiel loop) | godo_archetype 3, rograkh_silas 1; derevi 0 | 4, 7, 13, 14 | NO |
| 5A6o18Bra0Y | Cabbage Merchant R6 (Grinding Station mill loop, Seedtime turn) | godo 2, rog_ishai 1, cabbage 1 | 8, 11, 12, 13 | WEAK (1 of 4) |
| Bq-nFi0f1jA | 3 duels: Kinnan R4, Cabbage R4, Rog/Thras R4 | cabbage 2, kinnan 1, 1 timeout | 8, 12, 12 | PARTIAL (kinnan seat is the wrong-deck list; see manifest) |
| OuY6mdiXbHU | Lua won both (R4 concession, R5 Kiki combo) | perfect 1/1/1/1 split | 8, 9, 9, 11 | N/A (mirror): humans differentiate on skill, Forge cannot |
| B421mac67IE | Sisay ~R10 (range 9-12): Ouphe lock froze the table ~45 min; Sisay stolen, Matt won out of his 99 via all-activated-ability Deadpool text-swap line | yisan 1, kinnan 1, malcolm_vial 1, 1 timeout; **sisay 0** | 8, 12, 16 | NO. The one human game in Forge's round range, but through a negotiated stax grind and a routing-around-Damping-Sphere line no sim exhibits |
| CxKMqO36DdM | Dallas Blue Farm R5 (~R6): won a counter-war, Jeska's Will for 38, Underworld Breach through taxes | alan_tnt 2, dallas_bluefarm 1, sterling_bluefarm 1 | 10, 12, 13, 13 | PARTIAL (Forge spreads wins across the three blue decks; the human game hinged on a 40-minute stack war no sim exhibits). Dallas's list is drifted: Jeska's Will and Harnfel frame-verified on stream, absent from the simmed list, both central to his win |

## Aggregate findings

1. **Speed gap ~2x and almost non-overlapping.** Human wins across all 12
   extracted games: rounds 2-10, mean 5.0, with 11 of 12 in rounds 2-6. Stock
   Forge wins across 30 decided games (of 32; 2 timeouts): rounds 5-16 by
   table round, mean ~10.9. One Forge
   game (Godo equipment swing, R4) lands inside the human core range; one
   human game (the Pittsburgh Ouphe-lock stax grind, ~R10) lands inside
   Forge's — and that game was slow because of a resolved stax lock and table
   deals, mechanisms the sims don't have. For clock math note Forge counts
   player-turns: a "45-turn" 4-pod game is ~11 rounds.

2. **Forge's winner tracks combat-capability, not deck strength.** Every pod
   where the human winner won through a loop/storm/combo line (Ral storm,
   Derevi-Nadu, Grinding Station mill), Forge handed the pod to whichever deck
   can win by attacking: Godo, Magda, Winota. Magda "agreeing" with the human
   result in two pods is partially coincidence: the deck is both the strongest
   in those pods AND the most combat-capable, so Forge gets the right answer
   through the wrong mechanism (it never fetched Portal to Phyrexia in any of
   the 8 Magda-pod games).

3. **Interaction is the invisible half of the gap.** Human games are decided
   by stack fights the sims barely feature (Subtlety, Force of Will, Mental
   Misstep protecting the win; commentary explicitly grading players' keeps
   and tutor choices as errors). This study now holds ~12 expert-labeled
   decision annotations (correct fetch targets, wrong keeps, wrong tutors),
   which are directly usable as shim tuning targets.

4. **Timeout rate 2/32 (6%)** at clock 900 in stax-heavy pods only
   (B421 Sisay/Yisan, Bq-nFi0f1jA). Consistent with the clock calibration in
   `engine/SIM_CALIBRATION.md`; no action needed.

5. **Decklist fidelity is the pipeline's weakest link, and it is now
   measured.** Tournament-registered lists (topdeck.gg) are exact;
   same-episode TCGplayer links are exact; *different*-episode links and
   post-event Moxfield edits drift by 1-6 cards (in one case the drift
   includes a combo piece the human win used, in another the linked Kinnan is
   an entirely different build). Every seat's tier is in `manifest.json`.

## What this feeds into

The shim tuning priority list this pilot batch supports, in order:

1. **Win-line pursuit** (Stage 5 combo pursuit work): the entire agreement
   failure is Forge never attempting the deck's actual win line. Magda fetch
   targets are the cleanest single test case (expected: God-Pharaoh's Gift
   proactive, Portal reactive; observed: neither, ever).
2. **Win-speed calibration**: humans convert assembled engines within 1-2
   rounds; Forge sits on them (Godo winning R13-14 with a deck whose human
   line is R4-5).
3. **Keep/mulligan quality facing seat threats** (Natalie's graded keep error
   is a labeled example).

## Data inventory

- `traces/*.json` — 8 videos, 12 human games, with per-play caption
  repairs, frame verification, confidence labels, and expert error
  annotations.
- `runs/sim_*_rotated.json` — 8 pods x 4 rotated games, zone-truth logs
  (board basis `zone_stream`, exit_match_rate 1.0 on the pilot check).
- `decks/` — 32 converted .dck files with recorded substitutions.
- `manifest.json` — provenance and fidelity tier per seat.
