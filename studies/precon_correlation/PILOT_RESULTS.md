# Pilot results — 2026-08-04

8 precons x 2 arms x 32 games = **512 games**, `--clock 900`, seat-rotated 4-player
pods against three fixed Commander 2014 controls, pinned shim
`sha256 7d15e42b16301276`. Reproduce with:

```
python3 studies/precon_correlation/analyze.py
```

Design, pre-registration and known defects: `STUDY_PLAN.md`. Read §1 (ground
truth is only 46% reliable), §3d (controls too weak) and §7a.2 (arm-dependent
censoring) before quoting anything here.

---

## Headline: the primary outcome is null, and it leans against the agent

**Δr = −0.063** (Spearman, agent minus stock), paired bootstrap 95% CI
**[−1.249, +1.068]**, P(Δ>0) = 0.465 over 10,000 resamples.

The pre-registered primary hypothesis was Δr > 0 — that the humanized agent
predicts human precon win rates better than stock Forge. **It does not, on this
evidence.** And the agent is worse on every secondary calibration measure:

| metric | shim_stock | agent_v3 | better |
|---|---|---|---|
| Spearman vs human | 0.530 | 0.467 | stock |
| Pearson | 0.416 | 0.142 | stock |
| Pearson, weighted 1/SE² | 0.499 | **0.006** | stock |
| calibration slope (1.0 ideal) | 0.472 | 0.167 | stock |
| mean absolute gap | 17.7 pp | 22.0 pp | stock |
| side-of-baseline accuracy | 4/8 | 4/8 | tie |
| censored games | 7.8% | 19.9% | stock |

The weighted Pearson of **0.006** is the starkest number: once each deck is
weighted by how reliable its human win rate actually is, the agent arm has
essentially no linear relationship with human outcomes.

This is the first direct test of the claim in `MARKET_SCAN.md` §8 that the
humanized agent is the product's competitive moat. The claim is **not
supported**, and this needs to be said plainly rather than explained away.

## Per-deck

| precon | human | stock | gap | agent | gap |
|---|---|---|---|---|---|
| Planeswalker Party | 40.87% | 39.3% | −1.6 | 52.2% | +11.3 |
| Tricky Terrain | 32.07% | 42.3% | +10.2 | 25.0% | **−7.1** |
| Explorers of the Deep | 25.25% | 53.3% | +28.1 | 52.0% | +26.8 |
| Doom Prevails | 21.06% | 53.3% | +32.3 | 42.9% | +21.8 |
| Blight Curse | 18.49% | 40.0% | +21.5 | 50.0% | +31.5 |
| Mutant Menace | 15.12% | 40.0% | +24.9 | 52.0% | +36.9 |
| Grand Larceny | 13.20% | 19.4% | +6.2 | 24.1% | +10.9 |
| Deadly Disguise | 11.96% | 29.0% | +17.1 | 41.4% | +29.4 |

Both arms inflate almost everything, which is the weak-control problem (§3d),
and both compress hard: calibration slopes of 0.47 and 0.17 against an ideal
of 1.0.

## What the pilot was for: gate results

| gate | result |
|---|---|
| Pipeline end to end | **PASS** — Forge `.dck` → rotated pod → win rate, both arms, 16/16 cells, no failures |
| Forge card coverage | **PASS** — 0 stderr flags on all 16 cells, including both 2026 sets (Doom Prevails/Marvel, Blight Curse/Lorwyn Eclipsed). The full 66-deck cohort is viable; no need to drop to the 42-deck pre-2025 set |
| Do the extremes separate? | **PARTIAL** — stock spans 19.4-53.3% across a 12-41% human range, Spearman 0.530. Positive but not significant at n=8 (critical \|r\| ≈ 0.71) |
| Clock adequate at 900 s? | **FAIL** — see below |
| Controls adequate? | **FAIL** — see below |

## Two instrument defects that must be fixed before any full run

**1. The 900 s clock is too short, and it censors asymmetrically.**
Natural completions reach p95 686-741 s, p99 837-839 s, max 890 s — pressing
right against the wall. Censoring: stock 20/256 (7.8%), agent 51/256 (**19.9%**),
a 2.6x difference on matched decks and matched n.

This is not "excluding stalls." It is **excluding the long games**, and the agent
produces more of them, so the agent arm loses 2.6x more real data. Every agent
number above is computed on a more heavily censored, differently-selected
sample than its stock counterpart.

**Recommended clock: 1260 s** (agent p99 × 1.5), set from the agent arm because
it has the longer games. This is what makes censoring comparable.

Also settled: **there is no turns/sec stall threshold.** Natural games run as
slow as 0.041 turns/sec, below the fastest censored game (0.119). The clean
separation seen at n=76/clock-600 was an artifact. Drop that idea.

**2. The Commander 2014 control gauntlet is too weak.**
Six of eight decks sim above the 25% baseline, several by 20-37 pp. Twelve years
of power creep means modern precons beat 2014 precons regardless of their
standing among each other. Replace with precons Playgroup tracks but has no
stock win-rate data for — outside the 66 by construction, contemporary with the
cohort. Candidates verified in Forge's bundle: `Riveteers Rampage [NCC]`,
`Divine Convocation [MOC]`, `Draconic Dissent [CLB]`, `Painbow [DMC]`,
`Tinker Time [MOC]`.

## The one signal that favours the agent, and why it is weak

Post-hoc (tags assigned by me, and assigned *after* seeing early cells — the
motivated-classification risk is real):

| arm | creature decks | non-creature | spread |
|---|---|---|---|
| shim_stock | +30.2 pp | +13.0 pp | **17.1 pp** |
| agent_v3 | +24.3 pp | +18.8 pp | **5.4 pp** |

The agent's bias is far more *uniform across archetypes* — the spread falls from
17.1 pp to 5.4 pp, and it held when the deck count went from 4 to 8. That
distinction matters because **a uniform offset can be calibrated away; an
archetype-dependent one cannot.** If real, it is a better argument for the agent
than proximity to human win rates, because it is what makes a correction layer
possible at all.

But: **"creature" is n=2 in both arms.** The comparison is 2 decks against 6,
with hand-assigned post-hoc tags. This is a hypothesis worth testing properly,
not a finding. To test it honestly, archetype tags must be assigned for all 66
decks and registered *before* the full run.

## Recommendation

Do not launch the 168-264 hour full run yet. In order:

1. **Fix the instrument.** Contemporary controls, clock 1260 s. Both are known
   defects and both change the numbers.
2. **Pre-register the archetype hypothesis.** Tag all 66 precons before running
   anything, so the one promising signal can be tested rather than fitted.
3. **Re-run this same 8-deck pilot** on the fixed instrument, roughly 6-8 hours.
   If the null holds with good controls and comparable censoring, that is a real
   answer and it is cheap.
4. **Then decide** whether the full cohort is worth it, and on what primary
   outcome. If archetype-uniformity is the live hypothesis, the full run's value
   is measured per-archetype correction factors that could replace the
   hand-tuned archetype baselines in `SIM_CALIBRATION.md` — arguably more useful
   to the product than the correlation headline.

## What this means for the business argument

`MARKET_SCAN.md` §8 argues the humanized agent is the moat, on the strength of
behavioural resemblance (attack splits, block rate, mulligan rate all moving
into human bands). That evidence stands; it is measured from agent telemetry and
is unaffected by any of this.

What this pilot tested is the *further* claim that resemblance buys predictive
validity. On the current instrument it does not, and the agent looks somewhat
worse than stock. Two honest readings, and it is too early to choose:

- **The instrument is broken** (weak controls, asymmetric censoring, n=8), the
  null is uninformative, and a fixed re-run may show something different.
- **Humanization genuinely trades discrimination for realism.** More blocking
  and more interaction make games more even, which compresses win rates toward
  the 25% baseline — the agent's calibration slope is 0.167 against stock's
  0.472, and its sim spread is narrower. A deck-analysis product needs the
  opposite of that.

If the second reading survives a fixed re-run, `MARKET_SCAN.md` §8 needs
rewriting, and the moat argument should move to the measurement apparatus and
the corpus, which is where §8 already says the durable asset lives.

One more consequence worth noting: stock Forge scored Spearman **0.530** here.
If that survives, then Grim.Cards' stock-Forge approach has real predictive
validity, and "they run stock Forge" is not by itself the competitive weakness
`MARKET_SCAN.md` §2 implies.
