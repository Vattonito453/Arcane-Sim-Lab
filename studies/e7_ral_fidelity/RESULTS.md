# E7: Ral fidelity (results)

**Verdict: PASS.** After DFC normalisation, the joseph_ral commander (Ral,
Monsoon Mage) was cast from the command zone in **16 of 16 games** (100%;
the pre-registered line was 12 of 16, 70%). Before the fix it left the
command zone in 0 of 30 games, because Forge refused the card.

This is a fidelity read only, as pre-registered in `PREREG.md`. It says the
Ral seats now play with their commander. It says nothing about how well Forge
pilots the deck, and nothing about wins, which were not read.

## Provenance

| | |
|---|---|
| Pre-registration | `PREREG.md`, commit `4b45696`, 2026-09-27 17:58:29 UTC |
| Run | started 17:58:41 UTC, finished 18:21:11 UTC, the same day (after the pre-registration) |
| Decks | commit `401d524`; `joseph_ral.dck` SHA-256 `9cdd000d7ff1b717f5b514f1f3bf82454ebfb21eb5b2ca0a4a31e33f926ac172` in both pods, as pre-registered (the runner checked it before starting) |
| Engine | Forge 2.0.13; shim 0.16.0, jar SHA-256 `f40ae8d2e1b49d921b1ed22a3eb1eb23ec61cdf6d60400d1e2d8d6e792ee8cd9` |
| Pilots | stock on every seat (`--agent shim`, no plans) |
| Limits | 900 s clock, 120-turn cap, 4 GB heap, 2 JVMs at once |
| Games | 8 per pod, seat-rotated, 2 in each of the 4 seat orders; all 4 rotations complete in both pods (no crash, no shortfall) |
| Raw output | a scratch directory on the dev box; not committed |

**Validity precondition met.** `meta.unsupported_cards` is empty in both runs:
Forge loaded every card of every deck. (Before the regeneration, a load
check of the same pods reported 7 refused cards in each joseph_ral deck,
the commander among them.)

## Commander casts per game

From the zone records: a record for "Ral, Monsoon Mage" or "Ral, Leyline
Prodigy", owned by the joseph_ral seat, moving from `Command` to `Stack`.
A recast after Ral returned to the command zone counts again. Records from
`Command` to `Battlefield` were counted too; there were none.

| Pod (test bed) | Game | Casts | Put onto battlefield | Cast |
|---|---|---|---|---|
| `sZA0KqXCGrY` (dev) | 1 | 2 | 0 | yes |
| | 2 | 1 | 0 | yes |
| | 3 | 1 | 0 | yes |
| | 4 | 1 | 0 | yes |
| | 5 | 1 | 0 | yes |
| | 6 | 1 | 0 | yes |
| | 7 | 1 | 0 | yes |
| | 8 | 1 | 0 | yes |
| `CxKMqO36DdM` (holdout) | 1 | 1 | 0 | yes |
| | 2 | 2 | 0 | yes |
| | 3 | 1 | 0 | yes |
| | 4 | 1 | 0 | yes |
| | 5 | 2 | 0 | yes |
| | 6 | 1 | 0 | yes |
| | 7 | 1 | 0 | yes |
| | 8 | 1 | 0 | yes |

| | Games | Cast in | Share |
|---|---|---|---|
| `sZA0KqXCGrY` | 8 | 8 | 100% |
| `CxKMqO36DdM` | 8 | 8 | 100% |
| **Pooled** | **16** | **16** | **100%** (needed 12) |

## What was not read

Nothing about wins, draws, win turns, other seats' commanders, agent events
or plays. `run_sim.py`'s console output, which lists per-deck wins, went to a
log file that was not opened; `run_e7.py extract` read only the game counts,
the refused cards and the Ral seat's zone records above. `CxKMqO36DdM` is a
holdout pod, and this is the carve-out `studies/holdout/HOLDOUT.md` rule 3
grants E7; nothing from it informs any tuning before G3.

## What follows

Per the pre-registered action: the Ral seats count as real tests of their
deck from here on, and the WS4 acceptance row "Ral commander leaves the
command zone" (target: cast in at least 70% of games) is met. Whether Forge
can pilot storm stays untested until a study built for that question.

Reproduce: `py studies/e7_ral_fidelity/run_e7.py run --out <scratch>
--shim-jar <0.16.0 jar>`, then `py studies/e7_ral_fidelity/run_e7.py extract
--out <scratch>`. Games are unpaired (0.16.0 cannot seed Forge), so a re-run
plays different games.
