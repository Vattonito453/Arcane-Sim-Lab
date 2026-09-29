# E2 pre-registration: does `--seed-forge` pair opening hands?

Written and committed **before any E2 run**. `run_e2.py` and `read_e2.py` are committed after this file and before the first run. The runner refuses to start unless all three files are committed and unchanged, and it writes the commit of this file into every cell's metadata, so every `started` time is later than this commit.

Plan references: `tasks/25-repair-plan.md` section 3.0 ("Pairing"), section 4.4 (pre-registered experiments, row E2), and the WS1 acceptance row "Same seed gives the same opening hands (E2, within 0.17.0)": 10 pairs, pass at **10/10 identical up to the first decision**.

## Why it matters

Before 0.17.0, library shuffles, the first-player pick and every stock AI roll drew from Forge's unseeded `forge.util.MyRandom`, so two arms could never share a deal. Shim 0.17.0 adds `--seed-forge N`: before game `g` is built, it calls `MyRandom.setRandom(new Random(N + g * 104729))`. Until E2 passes, every n in the plan is sized as unpaired. G0a's arms C and T already shared seed lists; this experiment also says whether the pairing they assumed was real.

## What is being tested

- **Jar:** shim 0.17.0, branch `shim-0.17.0`, commit b8894e1, the jar G0a tested: `scratchpad/g0a/shim-0.17.0-b8894e1.jar`, SHA-256 `c2273bef30d7cd9edb20d711f81bce01444470a91e9d15bbf23f2e3fd3081dfd`.
- **Forge:** 2.0.13, `forge-gui-desktop-2.0.13-jar-with-dependencies.jar`, SHA-256 `94d55a3602ede599d6a0884a3fee6c047c3e9cf44356f79898a942ce8f8386d3`, run with the Forge folder as the working directory.
- **Pod:** cEDH-A `n7WpsqsZtdQ`, all plan seats, in G0a's rotation 0 seat order: magda, rog_ishai, selvala_archetype, tymna_thrasios (`studies/human_ceiling/decks/n7WpsqsZtdQ/dck/*.dck`, sorted; SHA-256 `3d442e0e...`, `43303cf3...`, `19654955...`, `dadf1b17...`, checked by the runner in full).
- **Plans:** exactly the file G0a arm T used: `scratchpad/g0a/plans_n7WpsqsZtdQ_v2.json` (version 2, every fix flag on), SHA-256 `9f0588572283ec83169cf3e827e33b03de89eada1bf449da25691644c69a41d9`, the `plans_sha256` recorded in G0a's arm-T cells. Not rebuilt.
- **Command per run** (G0a arm T's command except `--games` and `--max-turns`):
  `java -Xmx3g -cp <jar>;<forge jar> simlab.shim.SimShim --decks <4 decks> --games 2 --timeout 900 --max-turns 16 --plans <plans> --seat-pilots plan:SimLabHuman,plan:SimLabHuman,plan:SimLabHuman,plan:SimLabHuman --seed-forge <seed> --out <file>`.
  Neither changed flag can reach the deal: the turn cap is checked only once turns are being played, and the clock never binds on 16 turns.
- **Seeds:** `s_k = 2026092700 + 104729 * k` for k = 0..9 (2026092700, 2026197429, 2026302158, 2026406887, 2026511616, 2026616345, 2026721074, 2026825803, 2026930532, 2027035261). Two reasons for this list. `s_0..s_7` are the Forge seeds of games 0..7 of G0a's `n7WpsqsZtdQ` rotation-0 cells (arms C and T), so check I3 lines up with G0a's own games. And `s_(k+1) = s_k + 104729`, so game 1 of run k has the same Forge seed as game 0 of run k+1 (check I2).
- **Replicates:** each seed runs twice, replicate `a` and replicate `b`, each in its own JVM. At most 4 JVMs at once. Every `a` run finishes before any `b` run starts, so the two replicates of a seed never share a moment of machine load.
- Output goes to `scratchpad/e2_seeding/runs/`, never into git.

## The primary object: "identical up to the first decision"

Read from game 0 of each replicate's JSONL:

1. **The opening deal.** The longest leading run of the game's `zone` records (in emission order) that all have `turn` 0, `from` Library and `to` Hand. Each record is compared on (`toPlayer`, `cardId`, `card`), in order. This is every seat's opening seven, dealt before anyone decides anything. It must hold exactly 7 records for each of the 4 seats; otherwise the game is malformed.
2. **The first player:** the player named in the game's first log `entry` of type TURN ("Turn 1 (...)").
3. **The first decision record:** the game's first log `entry` of type MULLIGAN (lowest `seq`), compared on its message: which seat decided, and whether it kept or mulliganed to how many cards. Mulligans are taken in turn order from the first player, so this is the first player's first mulligan decision.

A pair is **identical** when all three are exactly equal between replicates `a` and `b`.

## Pass rule

**E2 passes if and only if 10 of 10 pairs are identical.** 9/10 fails.

A run whose JVM exits before emitting game 0's `result` record is re-run once with the same seed and replicate label; both attempts are reported. A pair whose game 0 is still missing or malformed after that counts as not identical.

## Secondary measure (descriptive, not gated): where each pair first diverges

For game 0 of every pair (and for game 1, under I1), three ordered streams are compared record by record:

- **events:** the shim's event-tap records (`zone`, `tap`, `counters`, `attach`, `rubric`) in emission order, compared as whole records. A record without a `turn` field takes the turn of the record before it.
- **log:** Forge's log `entry` records in `seq` order, compared on (`type`, `message`, `card`, `cardId`). An entry's turn is N from the latest preceding "Turn N" entry, or 0 before it.
- **agent:** the plan seats' `agent` records in emission order, compared as whole records.

Only records with turn <= 16 are compared: the turn-cap kill lands at a wall-clock-dependent moment in turn 17, so anything after the cap is not comparable. If one stream ends earlier than the other within the cap, the first missing index is the divergence. Reported per pair: the first differing record index in each stream, the turn (and phase, where the record has one) at that index in each replicate, the two differing records, and the pair's first divergence turn (the earliest over the three streams), or "none through turn 16". Games that end before the cap also report both results. Where a pair diverges, the differing records are read to name the decision or the random draw at which it happened.

## Informative checks (reported, not gated)

- **I1, the second game of a two-game cell.** Game 1 of replicate `a` against game 1 of replicate `b`: the same primary object (count of identical pairs out of 10) and the same divergence measure. This is the question whether game 2 of a cell is paired too (`seed + 1 * 104729`), after game 1 ended by the turn cap in the same JVM.
- **I2, seed + g x stride.** Game 1 of run k (Forge seed `s_k + 104729 = s_(k+1)`) against game 0 of run k+1, for k = 0..8, replicate `a` against `a` and `b` against `b` (18 comparisons): the deal (on `toPlayer`, `card` and `cardId`) and the first player. The first mulligan decision is reported beside them. Later play is expected to differ, because each plan seat's own controller seed includes the game index.
- **I3, G0a's own pairing.** Two readings of the existing G0a output (`scratchpad/g0a/runs/`), no new games:
  - For every cell G0a ran in both arm C (version-1 plans) and arm T (version-2 plans) at the same bed, rotation and `--seed-forge`, and for every game index in it (64 cEDH-A game pairs and 16 on Richard's pod): is the deal identical, the first player identical, and the first mulligan decision identical? The first divergence turn is reported; C and T are expected to diverge once the two plan versions choose differently. Richard's decklists are user data, so their pod is reported as counts only, with no card names.
  - E2's game 0 at seed `s_k` (k = 0..7) against game k of G0a's arm-T and arm-C `n7WpsqsZtdQ` rotation-0 cells, which ran on the same Forge seeds, the same jar and the same deck order: deal and first player. G0a's game k was the (k+1)th game of an 8-game JVM after games of up to 120 turns, so this says whether deep games of a long cell were really dealt from `seed + g * stride`.
- **I4, stock seats.** Seeds `s_0`, `s_1`, `s_2`, twice each, with `--seat-pilots plan:SimLabHuman,stock:Default,stock:Default,stock:Default` (the cEDH-A/stock bed's shape at rotation 0) and `--games 1`, otherwise as above: count of identical pairs out of 3, and the divergence measure. Stock seats draw every roll from `MyRandom`, so this says whether stock-seat beds (E3's opponents, the cEDH-A/stock bed) pair as well. It runs in the same two phases as the main runs.

## Decision

- **Pass:** the WS1 E2 row is met. Arms that share a seed list share opening deals and first players, so contrasts that depend on the deal may be sized as paired. The secondary measure bounds how far the pairing extends into play; beyond the first differing decision, games are independent draws and must be treated so.
- **Fail:** every n stays sized as unpaired. The cause is found before any design relies on seeding: a second random source that `setRandom` does not replace, thread timing (a game thread outliving its game, or a time-budgeted decision), or iteration order over identity-hashed collections. This experiment does not modify the shim; any fix goes to the shim's owner as a finding.

## Known before this was written

An informal check was run on 2026-09-27 during week 2 (scratch folder `scratchpad/e2`, never committed): a different pod (four precon decks from `engine/decks`), a pre-release 0.17.0 build (not the b8894e1 jar), `--games 1 --max-turns 1`, 10 seeds twice each. It found every pre-game zone record and the first player identical in 10/10 pairs, and one cross-JVM `seed + stride` check identical. Its comparison script was re-run read-only before this file was written, so the expected outcome is a pass. That check is not part of E2 and is not pooled with it. It could not test anything past turn 1, the tested jar, the cEDH-A pod or G0a's own games, which is what this experiment adds.
