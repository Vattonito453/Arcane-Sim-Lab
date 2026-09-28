# E2 results: `--seed-forge` pairs opening hands (PASS)

Read 2026-09-28 with `read_e2.py`, unchanged since it was committed (df56f51) before the first run. The pre-registration is 753a852; every cell records it. 26 runs, all exit code 0, none re-run, 07:24 to 07:30.

**Decision, per PREREG.md: PASS, 10/10.** With the same `--seed-forge` value, two separate JVMs on shim 0.17.0 (b8894e1, `c2273bef...`) dealt the same opening seven to every seat, card for card and card id for card id, picked the same first player and logged the same first mulligan decision, in all 10 pairs. The WS1 row "Same seed gives the same opening hands" is met.

**What pairing does not give you.** Play after the opening is not guaranteed to match. On the same seed, jar, plans and decks, 1 of 10 game-0 pairs diverged in play within 16 turns (turn 11, the mode of a modal spell), and 3 of 20 over both games of each cell. Two more game-0 pairs tapped the same lands for one spell in the opposite order and were otherwise identical record for record; the pre-registered raw measure counts them, so it reads 7 of 10 identical through turn 16. The play divergences come from an unseeded shuffle inside Forge's AI that `--seed-forge` does not reach (below; this diagnosis was corrected by the review). So a shared seed list guarantees the deal, the first player and the first mulligan round. After that, two same-arm games stay identical only until the AI takes one of those shuffled decisions, and two arms only until the treatment changes a decision. That is the pairing E2 was asked to prove, and it is real. Anything measured later in the game should be treated as coming from independent games.

## Setup (as pre-registered)

Pod cEDH-A `n7WpsqsZtdQ` in G0a's rotation-0 seat order (magda, rog_ishai, selvala_archetype, tymna_thrasios), every seat `plan:SimLabHuman`, G0a arm T's version-2 plans (`9f058857...`). Forge 2.0.13. `--games 2 --max-turns 16 --timeout 900`, `-Xmx3g`, at most 4 JVMs. Seeds `s_k = 2026092700 + 104729 k`, k = 0..9. Each seed ran twice (replicates a and b). Every replicate-a run had finished before any replicate-b run started. Games took a median of about 17 s (46 games, maximum 38 s).

## Primary: game 0, replicate a against replicate b

| k | Seed | First player | First mulligan record | Deal | First player | First record | Identical |
|---|---|---|---|---|---|---|---|
| 0 | 2026092700 | magda | magda mulliganed to 7 | same | same | same | **yes** |
| 1 | 2026197429 | selvala_archetype | tymna_thrasios mulliganed to 7 | same | same | same | **yes** |
| 2 | 2026302158 | rog_ishai | rog_ishai mulliganed to 7 | same | same | same | **yes** |
| 3 | 2026406887 | magda | magda mulliganed to 7 | same | same | same | **yes** |
| 4 | 2026511616 | magda | rog_ishai mulliganed to 7 | same | same | same | **yes** |
| 5 | 2026616345 | tymna_thrasios | tymna_thrasios mulliganed to 7 | same | same | same | **yes** |
| 6 | 2026721074 | tymna_thrasios | rog_ishai mulliganed to 7 | same | same | same | **yes** |
| 7 | 2026825803 | rog_ishai | tymna_thrasios mulliganed to 7 | same | same | same | **yes** |
| 8 | 2026930532 | tymna_thrasios | tymna_thrasios mulliganed to 7 | same | same | same | **yes** |
| 9 | 2027035261 | rog_ishai | rog_ishai kept 7 | same | same | same | **yes** |

Every deal held 7 records per seat, and every run echoed its seed in `meta.seedForge`. As a sanity check, the 10 seeds produced 10 different deals, so seeding varies the deal and does not pin it.

## Secondary (descriptive): where each pair first diverged

The comparison covers three streams, turn <= 16: shim events (zone, tap, counters, attach, rubric), Forge's log, and agent events. The index is the first record that differs in that stream.

| k | First divergence | events | log | agent | The differing decision |
|---|---|---|---|---|---|
| 0 | turn 11 | #134 | #216 | #42 | selvala_archetype's Archdruid's Charm mode: exile an artifact or enchantment (a) or search for a creature (b) |
| 1 | none through 16 | | | | |
| 2 | none through 16 | | | | |
| 3 | turn 12 | #190 | #254 | – | tymna_thrasios taps Tundra then Bayou (a), or Bayou then Tundra (b), for the same spell |
| 4 | none through 16 | | | | |
| 5 | none through 16 | | | | |
| 6 | turn 5 | #83 | #93 | – | tymna_thrasios taps Savannah then Tundra (a), or Tundra then Savannah (b), to cast Thrasios |
| 7 | none through 16 | | | | |
| 8 | none through 16 | | | | |
| 9 | none through 16 | | | | |

In all 10 pairs, every turn-0 record matched, including every mulligan and every card put on the bottom. 7 of 10 pairs were record-for-record identical through turn 16.

Review note (post hoc): k=3 and k=6 did not diverge in play. With every run of consecutive tap records (events) and MANA entries (log) sorted, both pairs are identical in all three streams through turn 16 (`review_e2.py tap`): the same lands were tapped for the same spell, in a different order, and nothing else differed. So 9 of 10 game-0 pairs were identical in play through turn 16. The one real divergence, k=0, is a decision Forge's AI draws from an unseeded shuffle (see "Why seeded games drift").

## Informative checks

- **I1, the second game of a two-game cell: paired, 10/10.** Game 1 matched between replicates on deal, first player and first mulligan record in every pair, after game 0 had been ended by the turn cap in the same JVM. Through turn 16, 8 of 10 were identical. k=2 diverged at turn 7 on which opponent received Into the Flood Maw's gifted Fish (selvala_archetype or tymna_thrasios). k=8 diverged at turn 10 on the Archdruid's Charm mode again. Both are decisions Forge's AI takes from an unseeded shuffle (review, below).
- **I2, seed + g x stride: 18/18.** Game 1 of run k (Forge seed `s_k + 104729`) dealt exactly what game 0 of run k+1 dealt: same cards, same card ids, same first player, same first mulligan record, for both replicates. So a game's deal depends only on its seed, not on its position in the JVM or on the game before it. Card ids restart every game.
- **I3, G0a's own pairing: real.**
  - Arm C against arm T, same cell and game index: all 80 game pairs had the same `--seed-forge`. The deal matched in **80/80** and the first player in **80/80** (cEDH-A 64/64, Richard's pod 16/16; counts only for their pod). The first mulligan record matched in 79/80. The exception (n7WpsqsZtdQ rotation 2, game 5) is a treatment effect, not a seeding failure: under version-2 plans Magda saw no plan card in the same 7 and mulliganed (`mull_take planCard=false`), where version 1 kept it.
  - E2's fresh-JVM game 0 at `s_k` against game k of G0a's 8-game `n7WpsqsZtdQ` rotation-0 cells: **16/16** matched on deal, first player and first mulligan record (k = 0..7, arms T and C). That includes C games 4 and 6, which followed games ended by the 900 s clock. Deep games of a long cell were really dealt from `seed + g * stride`.
  - After the opening, C and T part quickly, as two plan versions should. First divergence in the events stream: turn 0 in 13 pairs, turns 1-4 in 31, 5-12 in 31, 13 or later in 4, and never in 1 short game.
- **I4, stock seats: paired, 3/3.** Seeds `s_0..s_2` with one plan seat and three `stock:Default` seats: the deal, first player and first mulligan record matched in 3/3. Later play diverged in 1/3: a hidden draw at turn 15 (a different card on top of selvala_archetype's library). A second pair differed at turn 10 only in the order it tapped the same two sources, Tundra and Chrome Mox, for Thrasios, and was otherwise identical through turn 16 (review correction: this was first reported as a different mana source). Stock-seat beds (cEDH-A/stock, E3's opponents) pair their openings too.

## Why seeded games drift (post hoc, not pre-registered; corrected by the review)

The seeding itself is sound. What makes same-seed play differ between JVMs is a random source that `--seed-forge` does not reach. E2's first diagnosis blamed Forge's threaded AI (point 4 keeps it, corrected); the review found the source and tested it.

1. **An unseeded shuffle in Forge's AI changes play.** `java.util.Collections.shuffle(List)`, the one-argument form, draws from a private static `Random` inside `java.util.Collections`, seeded from the clock once per JVM. `MyRandom.setRandom` does not touch it. Forge 2.0.13 calls it on paths these games run:
   - `forge.ai.ability.CharmAi.checkApiLogic`: when the AI chooses fewer modes than a modal spell offers, it shuffles the modes and takes the first acceptable one. This is the Archdruid's Charm divergence (game 0 k=0, game 1 k=8).
   - `forge.ai.AiCostDecision.visit(CostPromiseGift)`: it shuffles the possible gift recipients and takes the first. This is the Into the Flood Maw divergence (game 1 k=2, and the diagnostic's k=3: nine runs of that Forge seed gifted the Fish to magda 4 times, tymna_thrasios 4 times and selvala_archetype once).
   - Also `DiscardAi` (discard targets), `ChooseCompanionAi`, `DraftEffect`, and `GameAction.drawStartingHand`. The last runs only with Forge's filtered-hands option, which is off, as the paired deals confirm.

   A shuffle can also move the seeded `MyRandom` stream with no visible record. k=0's turn-15 draw differed in all three hash-pinned replicates with nothing different before it, and it stopped differing once the shuffle was fixed (arms P, B and D below). The likely route is the AI evaluating modal spells it does not cast, in a shuffled order that changes how many `MyRandom` draws the evaluation takes. That route is not proven. E2's original scan looked for `Math.random`, `ThreadLocalRandom`, `SecureRandom` and `new Random` and missed this call; its figures (52 of the 1,133 `forge.ai` and `forge.game` classes use `MyRandom`; `SpellAbilityPicker` builds its own `Random` but runs only with AI simulation, which the shim never enables) are right. `review_e2.py scan` lists every call site from the jar.
2. **Tap order within one payment changes nothing.** At k=3 and k=6 (and I4's k=1) the pair tapped the same sources for the same spell in the opposite order, and every other record matched through turn 16. The order varied between ordinary JVMs and never between JVMs with identity hashes pinned, so it most likely comes from iterating a hash-ordered collection of mana sources.
3. **Test: route that shuffle through the seeded generator.** The review ran E2's command through throwaway launchers that do one reflective write to `Collections`' private `Random` field before calling the unmodified `SimShim.main` (`--add-opens java.base/java.util=ALL-UNNAMED`), at most 2 JVMs, replicate a before replicate b. Every run exited 0, and every pair matched on the primary object.

   | Arm | What is fixed | Game pairs | Identical in play through turn 16 | Record for record |
   |---|---|---|---|---|
   | E2, as run | nothing | 20 | 17 | 15 |
   | B | `Collections`' `Random` seeded once per JVM, and identity hashes pinned (`-XX:hashCode=2`) | 20 | 19 | 19 |
   | D | `Collections`' `Random` drawing from `MyRandom`, so it follows each game's `--seed-forge` generator; hashes not pinned | 20 | **20** | 16 |

   "In play" sorts each run of consecutive tap records and MANA entries first. B's one miss is game 1 of k=8, at the same Charm mode. A generator seeded once per JVM is consumed by however many turns game 0 plays past the cap before the 2 s poll kills it, and game 0 ended at turn 17 in one replicate and turn 18 in the other. D reseeds with every game, so it has no such tail. D's four raw misses are all tap-order swaps. An earlier pass (arm P, the once-per-JVM seed without hash pinning, 13 runs on the diverging seeds) gave the same picture: k=0, k=3 and k=6 each gave one trajectory in 3 JVMs, and k=8 game 1 split at the same Charm mode.

4. **E2's first diagnosis, corrected.**
   - "No second random source on the paths that run" is wrong; see 1.
   - The hash-pinning rerun (`diag_hashcode.py`; 3 pinned and 2 more ordinary replicates of k=0, 3 and 6) stands as data. Its pinned replicates still diverged in play on k=0 (three different turn-15 draws) and k=3 (the gift recipient), because hashes are not the source. But the pins did remove the tap-order swaps: k=6 was identical record for record in all 3 pinned JVMs.
   - Forge's AI does decide on other threads under wall-clock limits. `AiController.chooseSpellAbilityToPlayFromList` runs each spell choice on a new thread and waits `Game.getAITimeout()` seconds, 5 s by default. Only Forge's GUI path (`HostedMatch`) sets it; the shim builds `Match` directly. `AiAttackController.declareAttackers` fans attacker evaluation out with `CompletableFuture.supplyAsync` and `completeOnTimeout` (`AI_CAN_USE_TIMEOUT` is true by default). But no divergence E2 saw needs either one: the spell-choice timeout never fired in E2's runs (no `TimeoutException` in any stderr), and with the shuffle routed through `MyRandom`, 20 of 20 game pairs were identical in play. Whether these threads add drift in long or heavy games is not tested. In G0a the timeout fired 915 times (below), and each firing is a decision cut off by wall clock.
   - The counting-`Random` probe E2 proposed is not needed to find the source.

**For the shim's owner.** To pair games beyond the opening, route those shuffles through the seeded generator. There are two ways. One is an upstream Card-Forge change to `Collections.shuffle(list, MyRandom.getRandom())` in the six classes above; CLAUDE.md prefers upstream PRs. The other is a per-game reseed of `Collections`' generator from the shim next to the existing `setRandom` call; that needs `--add-opens java.base/java.util=ALL-UNNAMED` on every java command line. Neither changes a decision policy: the same random choices would draw from the seeded generator. Production runs are unseeded, so this matters only for paired studies. Tap order needs no fix.

**A larger finding for the owner: in G0a, that 5-second timeout fired 915 times** (stderr `TimeoutException` traces, every one in `chooseSpellAbilityToPlayFromList`): arm C 289, T 210, Z 416, across 31 of 36 cells, at 12 JVMs. Each time the stock AI's pick for that priority was lost: `getSpellAbilityToPlay` returns nothing, so a stock seat passes, and a plan seat passes unless the plan agent's own line pursuit casts something. The average is 3.8 per game, but the timeouts are concentrated (review): 71 of 240 games had any, 7 games hold half of them, and 459 fell in the 28 games that ran into the 900 s game clock. Because the budget is wall clock, which decisions get cut off can depend on machine load as well as on the seed. That dependence is inferred, not measured: E2's short games at 4 JVMs had no timeouts, and G0a's cluster in heavy games whose evaluations may be slow on any machine. The shim can raise that budget through the same kind of public call as `seedForge` (`Game.AI_TIMEOUT` is a public field). That is a behaviour change with a cost to weigh: in the heavy games a longer budget means more wall time per decision, so more of them would run out the 900 s clock. It needs its own gate, measured on the production VM, so it is left as an owner decision.

## What this means for G0a

G0a's arms C and T shared seed lists, and E2 says the pairing that assumed was real where it could be. All 80 C/T game pairs were dealt identical opening hands, with the same first player. The 16 deep-cell checks show that game k of an 8-game cell really ran on `seed + k * stride`, even after long games and clock timeouts. Past the opening the pairing thins out fast: the plan versions differ by design, and Forge's AI adds drift of its own through an unseeded shuffle (1 of 10 same-arm game-0 pairs, and 3 of 20 over both games, diverged in play within 16 turns). And 915 spell-choice timeouts, concentrated in a few heavy games, cut the stock AI's choice off by wall clock. None of this touches G0a's verdict. Its statistics were unpaired and clustered by game, which is conservative when a pairing is partial. Its `combo_hold` explanation relied on C and T sharing deals while Z did not, and that is confirmed. The G0a RESULTS line "C and T share their deals by construction" is accurate. "Paired" there should be read as shared deals, not paired games.

## Protocol notes

1. The pre-registration glossed the first MULLIGAN log entry as "the first player's first mulligan decision". Forge logs each mulligan when it is taken and every keep only after the round, so the first entry is the first mulligan taken in round one, or the first player's keep when nobody mulligans (k=1: selvala_archetype went first, tymna_thrasios's mulligan is the first record). The operational definition governs, and it is stricter than the gloss, because it depends on every seat's round-one decision.
2. The I3 reading of G0a's existing output was first run while `read_e2.py` was being tested, before any E2 run. After that, and before the commit, a per-stream breakdown of the C/T divergence turn was added to the reader. No E2 data existed at the time.
3. The informal week-2 check (other pod, pre-release jar, `--max-turns 1`) was disclosed in the pre-registration and is not pooled.
4. `diag_hashcode.py` and the bytecode scan are post hoc diagnostics. They were not gated, and the verdict does not rest on them.
5. **Adversarial review (2026-09-28, branch `r3/e2-review`).** PREREG.md (753a852, 07:20:46) predates the first run (07:24:49) and the branch reflog agrees; `run_e2.py` and `read_e2.py` (df56f51, 07:24:40) are unchanged since and implement the pre-registration. Re-running `read_e2.py` reproduced the saved reading byte for byte. Seeds k=1 and k=6 were re-run twice more (replicates c and d, both games, the committed command): the primary object matched across all four replicates of both seeds, and the new pair c/d matched too, so the reading holds. The review found two errors in the post hoc part and corrected them here: E2's scan missed an unseeded random source that Forge's AI does use, and two of the three game-0 "drifts" were tap order only. The pre-registered numbers are unchanged; every review figure is labelled post hoc.

## Reproduce

```bash
py studies/e2_seeding/run_e2.py run                # refuses unless PREREG.md and both scripts are committed; checks every hash
py studies/e2_seeding/read_e2.py --json reading.json
py studies/e2_seeding/diag_hashcode.py run         # post hoc
py studies/e2_seeding/diag_hashcode.py read
py studies/e2_seeding/review_e2.py scan            # review: unseeded random sources in the Forge jar
py studies/e2_seeding/review_e2.py tap             # review: E2's pairs with tap order normalized
```

The review's pinned runs used two throwaway Java launchers kept in the scratch folder (`e2_review/pin/`), not in this repo: they link the shim, so they stay on the GPL side of the boundary. Each is one reflective write followed by `SimShim.main(args)`.

Raw JSONL and cell metadata stay outside git (`$E2_OUT`, default the scratch folder). I3 reads G0a's output from `$G0A_OUT/runs`. Richard's decklists are user data and appear here only as counts.
