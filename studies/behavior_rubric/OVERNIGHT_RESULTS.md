# Overnight win-rate ablation: 1,536 games, and the honest answer

2026-08-29. Three configurations, 512 mixed-pod precon games each (16 pods x
4 rotations x 8 cycles), shim 0.9.3 throughout, turn cap 90, clock 900 s.
Two plan seats and two stock seats per game, so every decided game is one
head-to-head observation with null 50%.

```
python studies/behavior_rubric/winrate.py  runs_overnight/<arm>
python studies/behavior_rubric/observer.py runs_overnight/<arm>
python studies/behavior_rubric/compare.py  runs_overnight
```

## Win rate: parity, at power that settles it

| arm | record | % of decided | p (binomial) | censored | median game |
|---|---|---|---|---|---|
| base (shipping) | 205-198 | 50.9% | 0.77 | 108/512 | 310 s |
| lean (layers stripped) | 223-215 | 50.9% | 0.74 | **73/512** | **287 s** |
| split (splitAttacks 0.7) | 191-204 | 48.4% | 0.55 | 116/512 | 346 s |

Pooled: 619-617 (50.05%). At n ~ 400+ decided per arm the 95% CI is about
+/-4.9 pp, so this EXCLUDES any config being more than ~5 pp better or worse
than stock. Three conclusions, each now measured rather than argued:

1. **No behaviour configuration wins more than stock on precons.** The earlier
   46.6% over 256 games was noise around parity.
2. **The play-quality layers cost nothing.** `lean` strips the counter-eager
   profile, the threat veto (counterThreshold 0), grudge, kingmaker re-aim
   and voluntary chumps — and wins exactly as often as base. The layers are
   free on the win axis; they exist for how the game reads, and they can be
   judged on that alone.
3. **Win-rate gains, if they exist, are not in personality dials.** Two
   ablation campaigns (7 arms total) found nothing. What is left is strategy
   content: better lines, better tutor targets, conversion — the data side.

The 12-arm-hours spent here also bound the sim-time story: lean is ~7%
faster per game and censors 8 pp less than base; split is ~12% slower and
censors the most (more defenders means more combats to compute).

## The blocking edge holds at 512 games per arm, in every arm

Paired within game, sign-flip permutation (compare.py):

| metric (plan minus stock) | base | lean | split |
|---|---|---|---|
| engage | +0.035 (p < 1e-4) | +0.029 (p = 0.0003) | +0.044 (p < 1e-4) |
| declined blockable attackers | -0.152 (p < 1e-4) | -0.138 (p < 1e-4) | -0.174 (p < 1e-4) |
| free-block capture | +0.071 (p = 0.03) | +0.169 (p = 0.0001) | +0.158 (p < 1e-4) |
| safe-block capture | +0.099 (p = 0.0004) | +0.179 (p < 1e-4) | +0.147 (p < 1e-4) |
| chump share of blocks | -0.049 (p = 0.03) | -0.066 (p = 0.004) | +0.016 (ns) |
| damage per combat | ns | ns | ns |
| commit / keptEnough | ns | ns | ns |

The agent blocks more of what can be blocked, captures more of the profitable
blocks, chumps proportionally less, and attacks with the same commitment as
stock. Damage per combat stays equal (the 128-game "takes 4.67 less" claim
stays retracted).

## Mulligans, measured neutrally for the first time (1,024 seat-games/pilot)

| pilot | kept 7 | mulls/seat | lands kept | hands outside 2-5 lands |
|---|---|---|---|---|
| agent | 74.8% | 0.29 | 2.94 | 0.6% |
| stock | 82.0% | 0.21 | 3.05 | 0.6% |

Two documented claims die here:

- **"Stock keeps ~97% of opening hands" is wrong.** Measured per seat on the
  same terms as the agent, stock keeps 82.0% and mulls 18%: right AT the
  66-precon hypergeometric floor (mean 18.5% of sevens fall outside a 2-5
  land window). Stock does the land arithmetic. What it lacks is the REASON
  test: the agent also ships in-window hands with no plan card (keeps 74.8%),
  which is the part of mulligan skill Reid Duke's keep test describes.
- Both pilots end up outside the 2-5 window in only 0.6% of kept hands, so
  "keeps unkeepable hands" is not the stock failure mode either.

## Ship decisions from this run

- **Defaults stay base** for the interaction layers: win-neutral, and they are
  what makes the agent READ as smart (fired counters aim at median threat 8;
  vetoed chaff at median 2). The product sells the experience; the layers are
  the experience.
- **splitAttacks ships at 0.7** (deck_plan.py, all archetypes). It was
  misfiled as an error dial and never ran in a shipped config. Isolated at
  512 games: win effect -2.5 pp, not significant, CI includes zero; defenders
  per attack declaration 1.03 -> 1.28, the first config to break stock's 98%
  single-target habit. Cost: ~12% median game time.
- **Hold-back stays off, blockiness stays per-archetype** (unchanged).
- `lean` documents that a "fast mode" exists: ~7% quicker, 8 pp fewer clock
  kills, same wins, at the cost of unaimed interaction. Not shipped; noted
  for a future latency-sensitive tier.

## The 0.9.3 combo-gate A/B (cEDH, same pods, same plans, shim-only diff)

| | 0.9.1 (veto unconditional) | 0.9.3 (veto needs owned line) |
|---|---|---|
| combo casts | 53 | **73** (+38%) |
| tutor casts | 67 | **84** |
| combo holds | 31, all speculative | 28, **all on owned lines** |
| median winning game | 51 turns | **48 turns** |
| win round (true rounds) | 13.8 | **13.1** (stock 12.7, human 5.0) |
| counter fires (isolation check) | 89 | 86 |

n = 28 decided per side, so the sizes are estimates; the direction agrees
with the mechanism. The agent closed from 1.1 true rounds behind stock to
0.4. (Win rounds here were restated 2026-08-29 in true table rounds, counted
per player, after Vincent caught the replay showing Forge's per-player turn
counter; the old figures divided by a constant 4 and undercounted rounds in
games with eliminations.)
