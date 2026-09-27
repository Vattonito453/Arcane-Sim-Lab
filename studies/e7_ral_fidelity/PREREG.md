# E7: Ral fidelity (pre-registration)

*Written and committed 2026-09-27, before any E7 game was played. Repair plan
`tasks/25-repair-plan.md` WS4 task 7 and the section 4.4 E7 row; Appendix B
task 17.*

## Why

The 2026-09 diagnosis found that Forge refused the joseph_ral commander,
written "Ral, Monsoon Mage // Ral, Leyline Prodigy", and played both Ral decks
without it: 0 command-zone exits in 30 games. The study decks have now been
regenerated with Forge's own names (commit `401d524`, `make_dck.py` on
`engine/forge_index.py`'s resolver), and a Forge load check of both pods
reports 0 refused cards. E7 checks the one thing that fix was for: whether the
commander now leaves the command zone in play.

This is a fidelity read, not a strength test. It says nothing about whether
Forge can pilot storm, and it is not evidence either way on the old
"Forge cannot pilot storm" verdict.

## Hypothesis

After normalisation, the Ral decks' commander (Ral, Monsoon Mage) is cast from
the command zone in at least 70% of games.

## Decks

Both Ral decks are the same list, `joseph_ral.dck`, seated in two pods:

| Pod | Test bed | Seats (rotation 1 order, as the human_ceiling study ran them) |
|---|---|---|
| `sZA0KqXCGrY` | cEDH-dev | joseph_ral, tyler_bluefarm, ashton_bluefarm, natalie_magda |
| `CxKMqO36DdM` | cEDH-holdout | dallas_bluefarm, alan_tnt, sterling_bluefarm, joseph_ral |

`joseph_ral.dck` SHA-256 (both pods, commit `401d524`):
`9cdd000d7ff1b717f5b514f1f3bf82454ebfb21eb5b2ca0a4a31e33f926ac172`. The
runner refuses to start if either copy differs. The other six decks' hashes
are recorded by the runner in `e7_run.json`.

## Design

- **n:** 8 games per pod, 16 in all, seat-rotated with `run_sim.py --rotate`
  (2 games in each of the 4 seat orders).
- **Pilots:** stock on every seat: `--agent shim` with no plans, so only
  input fidelity is under test.
- **Engine:** Forge 2.0.13 (desktop jar SHA-256
  `94d55a3602ede599d6a0884a3fee6c047c3e9cf44356f79898a942ce8f8386d3`), shim
  0.16.0, production's version, built from `62fe295` (jar SHA-256
  `f40ae8d2e1b49d921b1ed22a3eb1eb23ec61cdf6d60400d1e2d8d6e792ee8cd9`; the
  runner records the hash of the jar it was given).
- **Limits:** 900 s per-game clock, 120-turn cap, 4 GB heap. Both pods run at
  once (2 JVMs; the cap is 4).
- **Pairing:** none. 0.16.0 cannot seed Forge, so games are unpaired.
- **Commands:**
  `py studies/e7_ral_fidelity/run_e7.py run --out <scratch> --shim-jar <0.16.0 jar>`
  then `py studies/e7_ral_fidelity/run_e7.py extract --out <scratch>`.
- **Output:** under a scratch directory, never committed. Only `RESULTS.md`
  is committed.

## Metric

For each game, **cast** is true when the game's zone records contain at least
one record with:

- `card` equal to "Ral, Monsoon Mage" or "Ral, Leyline Prodigy",
- `from` equal to `Command` and `to` equal to `Stack`,
- `fromPlayer` equal to the joseph_ral seat (`Ai(n)-joseph_ral`).

Also counted per game, and reported: the number of such casts (a recast after
the commander returns counts again), and records from `Command` to
`Battlefield` (a put, not a cast; not expected, reported apart, not scored).

**Primary:** the share of games with a cast, pooled over both pods. Per-pod
counts are reported beside it.

**Denominator:** every game the run played, however it ended (natural end,
turn cap or clock). A game in which the Ral seat was knocked out before it
cast its commander counts as not cast.

## Verdict rule

- **PASS:** cast in at least 70% of games, which is at least 12 of 16 (in
  general ceil(0.7 x n)).
- **FAIL:** fewer.
- **INVALID:** Forge refused any card in either run (`meta.unsupported_cards`
  not empty, or missing). Then the decks under test are not the decks Forge
  played; fix the decks and run E7 again from scratch.
- **INCONCLUSIVE:** fewer than 12 games played in all (crashed rotations).
  Then the short pod is re-run once, in full, and its re-run replaces it. A
  shortfall that still leaves at least 12 games is reported, not re-run.

## What is read, and what is not

Read: the number of games per pod, `meta.unsupported_cards`, and the Ral
seat's zone records named above. `run_e7.py extract` reads nothing else.

Not read: winners, draws, win turns or rounds, any other seat's commander,
agent events, plays. `run_sim.py` prints per-deck wins at the end of a run;
the runner sends that console output to a log file that nobody opens, and the
result files are not opened except by `extract`. This is the carve-out that
`studies/holdout/HOLDOUT.md` rule 3 grants E7: `CxKMqO36DdM` is a holdout
pod, so nothing from it may inform any tuning before G3. (Its joseph_ral seat
duplicates the dev pod's list, which is why the owner's 2026-09-27 decision
reports holdout results with and without that seat; E7 reports no results of
that kind.)

## Actions

- **PASS:** the Ral seats count as real tests of their deck from here on,
  and the WS4 acceptance row "Ral commander leaves the command zone" is met.
  Whether Forge can pilot storm stays untested until a study built for it.
- **FAIL:** find out why without tuning on the holdout. Check the run's
  `commander_fidelity`; Ral is not scripted `AI:RemoveDeck` in the 2.0.13
  index, so a loaded commander that is rarely cast is a stock-AI casting
  question, investigated on the dev pod (`sZA0KqXCGrY`) only. Under the owner's
  2026-09-27 decision a commander that loaded but was never cast gets a
  visible note, not a polluted verdict.
- **INVALID or INCONCLUSIVE:** as above.
