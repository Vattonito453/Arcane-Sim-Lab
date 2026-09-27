# G0a results: the tutoring hotfix passes (experiment E0)

Read 2026-09-27 with `read_g0a.py`, unchanged since the pre-registration commit (26f8571, before any game). 240 games: 80 per arm, every cell complete.

**Decision, per PREREG.md: PASS.** Every pre-registered rule passes: P1-P3, G1-G4, E1 and E2. R1 ships the hotfix: the shim is tagged `v0.17.0` at the tested commit, production is pinned to it, and `MTG_PLAN_VERSION=2` is set at the R1 deploy.

One event type, `combo_hold`, appeared in arm Z (0.16.0) and never in arm C (0.17.0, flags off). The pre-registered E2 rule could not test it, because it tested only events present in both arms. It was investigated after the read (below). The cause is which hands were dealt, not a code change, so the equivalence claim stands. The gap in the protocol is recorded under "Protocol notes".

## Arms

| Arm | Jar | Plans | Seeds |
|---|---|---|---|
| C | 0.17.0 (b8894e1, `c2273bef...`) | version 1 | `--seed-forge`, same list as T |
| T | 0.17.0 (b8894e1) | version 2, every fix flag on | same list as C |
| Z | 0.16.0 (62fe295, `f40ae8d2...`) | version 1 | none (0.16.0 cannot seed) |

Beds: cEDH-A (pods `n7WpsqsZtdQ` and `2iA_Jt0d6sM`, 64 games per arm) and Richard's pod (16 games per arm). 900 s clock, 120-turn cap.

## Primary rules (arm T, both beds pooled)

| # | Metric | T | C (flags off) | Rule | Verdict |
|---|---|---|---|---|---|
| P1 | Unreachable shim tutor casts, every basis | **0 / 36** (0%) | 147 / 222 (66.2%) | <= 5%, at least 20 casts | PASS |
| | same, restriction only | 0 | 99 | reported | |
| P2 | Graveyard steers onto a card with no graveyard use | **0** of 11 | 13 of 25 | 0 | PASS |
| P3 | Tutor casts with X = 0 | **0** | 14 | 0 | PASS |
| P3 | Tutor casts that failed to target | **0** | 22 | 0 | PASS |

The playtester's own complaint, on their own pod (16 games per arm):

| Richard's pod | C (flags off) | Z (0.16.0) | T (hotfix) |
|---|---|---|---|
| Plan steers that put Sol Ring in the graveyard | 12 | 9 | **0** |
| Unreachable shim tutor casts | 13 / 22 | – | **0 / 3** |
| Graveyard steers onto a card with no graveyard use | 7 of 19 | – | **0** of 10 |

## Guards (T against C)

| # | Metric | T | C | Rule | Verdict |
|---|---|---|---|---|---|
| G1 | Tutor spells cast per tutor drawn, plan seats | **59.0%** | 68.0% | T >= 50% | PASS |
| G2 | Games won by Thassa's Oracle | **6** | 4 | T >= 70% of C | PASS |
| G3 | `counter_fire` per seat-game | **0.472** | 0.516 | within +/- 25% of C (T is -8.5%) | PASS |
| G4 | Per-deck win share, decided games | largest drop: derevi 4/24 vs 9/27, -16.7 pp, SE 12.2 pp (1.4 SE) | | no deck down by more than 2 SE | PASS |

Per deck (decided games, wins/games):

| Deck | C | T | T - C | SE |
|---|---|---|---|---|
| magda | 10/29 | 10/28 | +1.2 pp | 12.6 |
| rog_ishai | 5/29 | 7/28 | +7.8 | 10.8 |
| selvala_archetype | 10/29 | 6/28 | -13.1 | 11.9 |
| tymna_thrasios | 4/29 | 5/28 | +4.1 | 9.7 |
| derevi | 9/27 | 4/24 | -16.7 | 12.2 |
| godo_archetype | 9/27 | 11/24 | +12.5 | 13.7 |
| nadu | 6/27 | 5/24 | -1.4 | 11.5 |
| rograkh_silas | 3/27 | 4/24 | +5.6 | 9.7 |
| Kess, Reanimator | 6/15 | 4/16 | -15.0 | 16.8 |
| Skrat's Revenge | 5/15 | 3/16 | -14.6 | 15.7 |
| Stella Lee, Wild Card | 0/15 | 3/16 | +18.8 | 10.6 |
| Krenko Goblins | 4/15 | 6/16 | +10.8 | 16.8 |

These are catastrophe checks only. 16 to 29 decided games per deck cannot show a win-rate effect, and none is claimed.

## Equivalence (C against Z: 0.17.0 flags off against 0.16.0)

| # | Metric | Result | Rule | Verdict |
|---|---|---|---|---|
| E1 | Crashed or short cells | 0 in every arm (80/80/80 games) | 0 | PASS |
| E2 | Agent-event rates, 18 types present in both arms, game-clustered, Holm at 0.05 | none significant; smallest p = 0.083 (`mull_keep`, z = -1.73) | none significant | PASS |

No event type differs by more than 2 SE even without correction (largest |z| = 1.73), so the plan's looser wording of this row ("within 2 SE") passes too.

Per seat-game rates, Z then C: `added_block` 0.778 / 0.644, `attack_reask` 0.087 / 0.106, `block_skip` 1.925 / 1.656, `combo_cast` 0.581 / 0.575, `counter_fire` 0.472 / 0.516, `counter_veto` 1.016 / 0.947, `finisher_hold` 0.009 / 0.006, `instant_hold` 2.625 / 2.641, `instant_window` 1.250 / 1.278, `kingmaker_reaim` 0.706 / 0.619, `line_completion_seen` 0.037 / 0.050, `mull_keep` 0.866 / 0.812, `mull_take` 0.512 / 0.613, `open_reaim` 0.603 / 0.600, `search_seen` 3.622 / 3.575, `split` 1.400 / 1.334, `tutor_cast` 0.619 / 0.694, `tutor_steer` 1.700 / 1.519.

Present in one arm only: `tutor_skip` in C (0.17.0 writes it by design, excluded by the pre-registration) and `combo_hold` in Z (not anticipated; see below).

## The `combo_hold` investigation (post hoc)

Arm Z logged 11 `combo_hold` events and arm C logged none. All 11 are the early-burn veto ("kept for the line (early burn vetoed)"): Tainted Pact 8 times in one tymna_thrasios game, Jeska's Will twice in one rograkh_silas game, and Brass's Bounty once. That is 3 games of 80. An event that 0.16.0 emits and 0.17.0 with its flags off never emits could mean the flags-off path changed, which is the pre-registered failure branch. Four checks say it did not.

1. **The code path is identical.** In the diff from v0.16.0 to b8894e1, the veto (`stockBurnsPiece = sight.missingOutside == null` and the hold that follows) is unchanged. The piece-casting loop is unchanged. The tutor loop picks the same tutor under the same conditions when every flag is off. The new calls are logging (`skipRoll`, `noteTutors`, `noteSkip`, `profileOf`, `reachOf`). Their only calls into Forge are the two 0.16.0's `castableSpell` already makes, setting the activating player to the card's owner and asking `canPlay`, plus a read-only `filterListByType`. The controller's random stream has the same nine draw sites in both versions, and the new code adds none. A version-1 plan parses to the same lines, with `threatLines` aliased to `lines`.
2. **The veto fires on the same jar.** Arm T, on the b8894e1 jar, logged 6 early-burn vetoes (Tainted Pact, tymna_thrasios, one game). The veto is not behind any fix flag.
3. **Arm C was rarely dealt the state the veto needs.** The veto needs a one-shot line piece in hand while every other piece of the line is in hand, on the battlefield or in the command zone. `veto_exposure.py` reads that state from the zone records.

   | Arm | Games with the state on any line | on the lines that vetoed anywhere (Tainted Pact + Oracle, Jeska's Will + Breach + Wheel, Brass's Bounty + Reversal + Storm) | Veto games |
   |---|---|---|---|
   | C | 19 | **1** | 0 |
   | Z | 24 | **4** | 3 |
   | T | 27 | **2** | 1 |

   The common exposure, Demonic Consultation + Thassa's Oracle (19 to 24 games per arm), produced no veto in any arm, 0.16.0 included. The lines that do produce vetoes were dealt once in C's 80 games. C's seeded deal list simply held fewer of them than Z's random deals.
4. **It is not a significant difference.** Tested as the pre-registration would have tested it with absent counted as zero: 0.034 vs 0.000 per seat-game, clustered z = -1.33, p = 0.18. Added to the Holm family (19 types), nothing is significant.

So `combo_hold` is deal rarity, and G0a stands.

## Not gated, reported

- **The shim now casts far fewer tutors itself, and Forge's AI casts most of the rest.** Shim tutor casts fell from 222 to 36, while casts per tutor drawn fell only from 68% to 59%. The tutor-skip records in T give the reasons, counted per tutor per turn: `not-castable` 2,125, `gate-closed` 1,107, `no-lines` 790, `unreachable` 540, `no-mana` 50, `line-owned` 47, `forced-choice` 22, `piece-first` 2. The `unreachable` records are the hotfix working. A tutor whose search cannot find the missing piece is left to Forge's own AI instead of being fired at nothing.
- **Closer overrides did not fall as expected: 41 to 34** (Magda's pod 40 to 33). Version 2 did remove the Clock of Omens lines, as expected. But the remaining Magda lines (Battered Golem + Dwarven Bloodboiler + Maskwood Nexus or Stalactite Dagger) put their pieces in the search targets at weight 8, and Portal to Phyrexia sits at 6. So the plan still steers a search that stock would have spent on Portal. The owner fix is E6 (proven closers at tier 9, week 6). It goes on R1's "not fixed yet" list.
- **Kess's graveyard steers**: 10 on Richard's pod in T, every one onto a card with a graveyard use. The Hullbreaker Horror vs Blasphemous Act choice with Unmarked Grave goes to Richard as the R1 review question.
- **Known classifier limitation** (recorded before the run): Umbral Mantle lines stay in the version-2 pilot lines. This gate tested harm removal, not line quality.

## Protocol notes

1. **E2 tested only the event types present in both arms.** The pre-registration excluded events that exist only in 0.17.0, such as `tutor_skip`, and said nothing about an event that appears in only one arm by chance. `combo_hold` was therefore untested by the pre-registered rule. It was handled after the read (the section above) and is labelled post hoc. For future equivalence gates: test the union of event types with an absent type counted as zero, and name the by-design exclusions individually.
2. **Arm Z cannot be seeded**, so C and Z play different deals. Rare, deal-dependent events can appear in one arm only for that reason. C and T share their deals by construction, which is what makes the P and G comparisons paired.
3. The plan's G0a row says "within 2 SE" for the equivalence. The pre-registration, committed before any game, uses Holm-corrected tests and governs. Both readings pass.

## What happens at R1

1. Merge simlab-forge-shim PR #15 and tag `v0.17.0` **at b8894e1**, the commit this gate tested. Anything that lands on the branch after b8894e1 is not covered by G0a.
2. Set `SIMLAB_SHIM_REF=v0.17.0` and `MTG_PLAN_VERSION=2` at the R1 deploy. Preflight refuses plan version 2 on an older shim.
3. The worker image will contain the 0.17.0 shim. Running it on our server imposes nothing. Publishing that image would require the shim repo to stay public at the tagged commit (CLAUDE.md, legal posture).
4. Richard's before-and-after pack uses the mechanism counts above: Sol Ring put in the graveyard, 12 to 0, and unreachable tutor casts, 13 of 22 to 0 of 3, each shown against the same kind of moment after the fix. No win rates.

## Reproduce

```bash
G0A_OUT=<scratch>/g0a py studies/hotfix_g0/read_g0a.py --json reading.json   # pre-registered read
G0A_OUT=<scratch>/g0a py studies/hotfix_g0/veto_exposure.py C Z T            # post hoc combo_hold check
```

Raw JSONL, plans and caches stay outside git (Richard's decks are user data). Jar hashes are checked by `run_g0a.py` before any cell runs.
