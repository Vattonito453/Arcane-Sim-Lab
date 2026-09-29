# Scenario report

Shim `shim-0.17.1-967cb71.jar` (sha256 `56758de2551b70e8`), repo `553dcf5b811b`, 4 trials per arm, seeds 2026101400..2026101403, started 2026-09-28T07:54:16. Trial k of every arm shares its Forge seed and library shuffle. ms per decision: not exposed by this shim.

## smoke_godo_helm

Harness smoke test, not the C1 control: Godo, Bandit Warlord with Helm of the Host attached on its controller's turn 5 main phase, the other three cEDH-A seats (pod 2iA_Jt0d6sM) on light boards at 40 life. Checks that a 4-player state loads for every arm and plays to a result. C1 proper (WS3 task 4) must reproduce the Helm-attached boards of the stock games it is compared with.

Scenario turn 5; success: seat 1 wins by turn 9; line pieces: Godo, Bandit Warlord, Helm of the Host.

| Arm | Loaded | Success | 95% CI | Kill on scenario turn | Turns to kill (median) | Line activity (mean) | Iterations, best turn (mean) | Extra combats, scenario turn (mean) | Draws / capped / timed out | Errors / exceptions | Game ms (mean) | Wall s (total) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stock | 4/4 | 4/4 | 0.51-1.00 | 4/4 | 0.0 | 67.5 | 67.5 | 21.5 | 0 / 0 / 0 | 0 / 0 | 47660.25 | 242.3 |
| plan | 4/4 | 4/4 | 0.51-1.00 | 4/4 | 0.0 | 66.0 | 66.0 | 21.0 | 0 / 0 / 0 | 0 / 0 | 32523.5 | 165.0 |
