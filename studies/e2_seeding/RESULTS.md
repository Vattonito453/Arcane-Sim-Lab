# E2 results: `--seed-forge` pairs opening hands (PASS)

Read 2026-09-28 with `read_e2.py`, unchanged since it was committed (df56f51) before the first run. The pre-registration is 753a852; every cell records it. 26 runs, all exit code 0, none re-run, 07:24 to 07:30.

**Decision, per PREREG.md: PASS, 10/10.** With the same `--seed-forge` value, two separate JVMs on shim 0.17.0 (b8894e1, `c2273bef...`) dealt the same opening seven to every seat, card for card and card id for card id, picked the same first player and logged the same first mulligan decision, in all 10 pairs. The WS1 row "Same seed gives the same opening hands" is met.

**What pairing does not give you.** Play after the opening is not reproducible. The same seed on the same jar, plans and decks drifted apart within 16 turns in 3 of 10 game-0 pairs (first divergence at turns 5, 11 and 12). The cause is inside Forge's AI (below). So a shared seed list pairs the deal, the first player and the first mulligan round, and no more. That is the pairing E2 was asked to prove, and it is real. Anything measured later in the game should be treated as coming from independent games.

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

## Informative checks

- **I1, the second game of a two-game cell: paired, 10/10.** Game 1 matched between replicates on deal, first player and first mulligan record in every pair, after game 0 had been ended by the turn cap in the same JVM. Through turn 16, 8 of 10 were identical. k=2 diverged at turn 7 on which opponent received Into the Flood Maw's gifted Fish (selvala_archetype or tymna_thrasios). k=8 diverged at turn 10 on the Archdruid's Charm mode again.
- **I2, seed + g x stride: 18/18.** Game 1 of run k (Forge seed `s_k + 104729`) dealt exactly what game 0 of run k+1 dealt: same cards, same card ids, same first player, same first mulligan record, for both replicates. So a game's deal depends only on its seed, not on its position in the JVM or on the game before it. Card ids restart every game.
- **I3, G0a's own pairing: real.**
  - Arm C against arm T, same cell and game index: all 80 game pairs had the same `--seed-forge`. The deal matched in **80/80** and the first player in **80/80** (cEDH-A 64/64, Richard's pod 16/16; counts only for their pod). The first mulligan record matched in 79/80. The exception (n7WpsqsZtdQ rotation 2, game 5) is a treatment effect, not a seeding failure: under version-2 plans Magda saw no plan card in the same 7 and mulliganed (`mull_take planCard=false`), where version 1 kept it.
  - E2's fresh-JVM game 0 at `s_k` against game k of G0a's 8-game `n7WpsqsZtdQ` rotation-0 cells: **16/16** matched on deal, first player and first mulligan record (k = 0..7, arms T and C). That includes C games 4 and 6, which followed games ended by the 900 s clock. Deep games of a long cell were really dealt from `seed + g * stride`.
  - After the opening, C and T part quickly, as two plan versions should. First divergence in the events stream: turn 0 in 13 pairs, turns 1-4 in 31, 5-12 in 31, 13 or later in 4, and never in 1 short game.
- **I4, stock seats: paired, 3/3.** Seeds `s_0..s_2` with one plan seat and three `stock:Default` seats: the deal, first player and first mulligan record matched in 3/3. Later play diverged in 2/3: a hidden draw at turn 15 (a different card on top of selvala_archetype's library), and a mana source at turn 10 (Tundra or Chrome Mox). Stock-seat beds (cEDH-A/stock, E3's opponents) pair their openings too.

## Why seeded games drift (post hoc, not pre-registered)

The seeding itself is sound: game-level determinism breaks inside Forge's AI. What was checked:

1. **No second random source on the paths that run.** A bytecode scan covered every `forge.ai` and `forge.game` class in the Forge 2.0.13 jar (1,133 classes). 52 of them use `forge.util.MyRandom`, which `--seed-forge` replaces. None uses `Math.random`, `ThreadLocalRandom` or `SecureRandom`. The one class that builds its own `Random` is `forge.ai.simulation.SpellAbilityPicker`. It runs only when AI simulation is on, an `AIOption` the shim never passes. The shim's own collections hash by card id or by string, and each plan seat's controller RNG is seeded.
2. **Not identity-hash iteration order.** `diag_hashcode.py` reran the three diverging seeds with every identity hash code pinned to 1 (`-XX:+UnlockExperimentalVMOptions -XX:hashCode=2`, 3 replicates each) and in ordinary JVMs (2 more each). The pinned replicates still diverged on 2 of 3 seeds. On k=0 the three pinned replicates drew three different cards at turn 15 with no earlier difference in any stream. On k=3 one replicate gifted the Fish to magda and the other two to tymna_thrasios. Ordinary replicates kept splitting as before: k=0 gave three distinct trajectories in four JVMs, k=6 gave two.
3. **Forge's AI decides on other threads, under wall-clock limits.**
   - `AiController.chooseSpellAbilityToPlayFromList` runs every spell choice on a new thread and waits `Game.getAITimeout()` seconds. That is 5 s by default. Only Forge's GUI path (`HostedMatch`) reads a preference for it, and the shim builds `Match` directly. On timeout it stops the thread and the AI plays nothing at that priority.
   - `AiAttackController.declareAttackers` fans attacker evaluation out with `CompletableFuture.supplyAsync` and `completeOnTimeout` (`AI_CAN_USE_TIMEOUT` is true by default).
   - `ComputerUtilMana.isManaSourceReserved` rolls `MyRandom`. So a shift in the random stream's position first shows up as a different land tapped, a different Charm mode, a different gift recipient or a different shuffle. That is exactly the set of symptoms seen.

The 5-second spell-choice timeout never fired in E2's runs: short games, 4 JVMs, no `TimeoutException` in any stderr. So E2's drift comes from thread scheduling and not from the budget. The most likely site is the attack fan-out, the one concurrent evaluation on these paths. **The exact site is not proven.** The definitive probe is a counting `Random` handed to `MyRandom.setRandom`, logging the draw count and the drawing thread at each turn boundary. That is a logging-only shim change for the shim's owner, and this experiment did not modify the shim.

**A larger finding for the owner: in G0a, that 5-second timeout fired 915 times** (stderr `TimeoutException` traces, every one in `chooseSpellAbilityToPlayFromList`): arm C 289, T 210, Z 416, across 31 of 36 cells. About 3.8 times per game at 12 JVMs, the AI's spell choice was cut off by the clock and it passed. Sim play therefore depends on CPU contention, and not only on the seed. The shim can raise that budget through the same kind of public call as `seedForge` (`Game.AI_TIMEOUT` is a public field). That is a behaviour change needing its own gate, so it is left as an owner decision.

## What this means for G0a

G0a's arms C and T shared seed lists, and E2 says the pairing that assumed was real where it could be. All 80 C/T game pairs were dealt identical opening hands, with the same first player. The 16 deep-cell checks show that game k of an 8-game cell really ran on `seed + k * stride`, even after long games and clock timeouts. Past the opening the pairing thins out fast: the plan versions differ by design, and Forge's threaded AI adds drift of its own (3 of 10 same-arm pairs within 16 turns). And 915 spell-choice timeouts made later play depend on machine load. None of this touches G0a's verdict. Its statistics were unpaired and clustered by game, which is conservative when a pairing is partial. Its `combo_hold` explanation relied on C and T sharing deals while Z did not, and that is confirmed. The G0a RESULTS line "C and T share their deals by construction" is accurate. "Paired" there should be read as shared deals, not paired games.

## Protocol notes

1. The pre-registration glossed the first MULLIGAN log entry as "the first player's first mulligan decision". Forge logs each mulligan when it is taken and every keep only after the round, so the first entry is the first mulligan taken in round one, or the first player's keep when nobody mulligans (k=1: selvala_archetype went first, tymna_thrasios's mulligan is the first record). The operational definition governs, and it is stricter than the gloss, because it depends on every seat's round-one decision.
2. The I3 reading of G0a's existing output was first run while `read_e2.py` was being tested, before any E2 run. After that, and before the commit, a per-stream breakdown of the C/T divergence turn was added to the reader. No E2 data existed at the time.
3. The informal week-2 check (other pod, pre-release jar, `--max-turns 1`) was disclosed in the pre-registration and is not pooled.
4. `diag_hashcode.py` and the bytecode scan are post hoc diagnostics. They were not gated, and the verdict does not rest on them.

## Reproduce

```bash
py studies/e2_seeding/run_e2.py run                # refuses unless PREREG.md and both scripts are committed; checks every hash
py studies/e2_seeding/read_e2.py --json reading.json
py studies/e2_seeding/diag_hashcode.py run         # post hoc
py studies/e2_seeding/diag_hashcode.py read
```

Raw JSONL and cell metadata stay outside git (`$E2_OUT`, default the scratch folder). I3 reads G0a's output from `$G0A_OUT/runs`. Richard's decklists are user data and appear here only as counts.
