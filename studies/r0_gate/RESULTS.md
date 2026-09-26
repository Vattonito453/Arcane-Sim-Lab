# R0 gate: shim 0.16.0 vs 0.15.0 on Richard's pod (2026-09-26)

**Verdict: PASS.** Production can move to shim 0.16.0 (commit 62fe295) at R0.

Design (tasks/25-repair-plan.md, section 4.4): Richard's production pod (Kess, Reanimator; Skrat's Revenge; Stella Lee, Wild Card; Krenko Goblins), all four seats plan agents as in production, same plans file, 4 seat rotations x 4 games per arm, 900 s clock, 120-turn cap, 8 JVMs on the dev box. The 0.15.0 jar is byte-size-identical to production's (48,322 bytes); the 0.16.0 jar was built from the shim's main branch at 62fe295. Run twice (independent replicates), 64 games in all. `r0_gate.py` is the harness; the imported decklists and plans are user data and stay off-repo.

| Check | 0.15.0 | 0.16.0 | Pass rule |
|---|---|---|---|
| Games / crashed cells | 32 / 0 | 32 / 0 | no crashes |
| Timeouts | 3 | 3 | – |
| Turns with more than one kingmaker re-aim (the re-ask loop signature) | 0 | 0 | 0 on 0.16.0 |
| attack_reask / attack_reverted (0.16.0's guards) | – | 0 / 0 | – |
| Agent-event rates per seat-game, pooled, game-clustered SE | – | largest gap combo_cast z = +2.10 | none beyond the Holm threshold (z 2.94 for 15 metrics) |

**How the gate was read, and a lesson.** The first replicate flagged counter_fire (z +2.10) and counter_veto (z +2.45) under game-clustered SE. None of 0.16.0's new code ran in those games (0 re-asks, 0 reverts, solver and gates off, counterspell code byte-identical between the versions), so a second replicate was run instead of arguing it. The replicate flipped the sign (z -3.38 and -2.80), and pooled over 64 games the gaps vanish (-1.06 and -0.24). At 16 games per arm, agent-event rates swing about +/-3 SE between identical-code replicates, because events cluster by deck and seat. Future gates on event rates should pool at least 32 games per arm, correct for the number of metrics, and replicate before believing a single small run.

The re-ask loop did not occur in either arm on this pod, so this gate shows 0.16.0 is safe here, not that it fixes anything visible on Richard's decks; the loop was measured on cEDH and precon pods (shim README, 0.16.0).
