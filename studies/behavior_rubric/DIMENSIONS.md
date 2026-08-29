# The eight dimensions: stock vs agent vs human, measured

Status as of 2026-08-29. One row per dimension Vincent named. Every number
below is measured, with its population and source next to it; the overnight run
(1,536 games) landed 2026-08-29; every cell below is final except the 0.9.3
cEDH validation noted in row 7. Full overnight data: `OVERNIGHT_RESULTS.md`.

Populations differ by dimension and cannot be merged: blocking and mulligans
need creature-dense boards (precons), interaction and combo need dense-line
decks (cEDH). Human baselines exist only where videos narrate the action.

| # | dimension | stock | agent (shipping) | human | verdict |
|---|---|---|---|---|---|
| 1 | Mulligans | keeps 82.0% (at the land floor) | keeps 74.8% (floor + reason test) | not measurable (edited out) | measured at 1,024 seat-games each; "stock keeps ~97%" was wrong |
| 2 | Blockers | 76.0% free-block capture | **96.3%** | not measurable (never narrated) | DONE, replicated across 2x128 games |
| 3 | Split attacks | 1.03 defenders/attack | **1.28** at splitAttacks 0.7, now shipped | partial (key_line) | win effect -2.5 pp ns at n = 512; first config to break single-target |
| 4 | Instants off-turn | 62% of disruption | 62% | n/a (floor data only) | timing was never broken; both bots are fine here |
| 5 | Combo pursuit | sits on tutors, burns pieces | steering works; early-burn veto was overfiring | closes round 5 | 0.9.3 gates the veto on line proximity |
| 6 | Intentional triggers | Forge's trigger AI | never misses; combo triggers protected | n/a | DONE at triggerMiss 0 |
| 7 | Pursuing win con | win round 10.9 (cEDH) | 12.3 (0.9.3 validation in flight) | **5.0** | head-to-head is PARITY at n = 1,236 decided: 50.9/50.9/48.4% per arm |
| 8 | Disrupting enemy win con | no threat model | fires at median threat 8 (92% >= 8), vetoes chaff at median 2 | 7.3 disruption/game (floor) | DONE: interaction is aimed, not sprayed |

## What each row rests on

**1. Mulligans.** The agent keeps a hand only with 2-5 lands AND a plan card
(after the free Commander mulligan the reason requirement relaxes; London
bottoming sheds excess lands then the worst nonplan cards). Measured
neutrally at 1,024 seat-games per pilot (shim 0.9.2 `mull` records): stock
keeps 82.0% of sevens — NOT the ~97% previously documented — which is right
AT the cohort's hypergeometric floor (mean 18.5% of sevens fall outside a
2-5 land window; range 12.8-21.0% across 36-44 lands). Stock does the land
arithmetic; the agent adds the reason test and keeps 74.8%. Both pilots keep
an out-of-window hand only 0.6% of the time.

**2. Blockers.** Two independent 128-game mixed-pod runs: the agent captures
96.3% of kill-and-survive blocks vs stock's 76.0% (paired +0.227, p = 0.0023,
36 of 38 games; independently +0.171, p = 0.025), lets 39.1% of blockable
attackers through vs 51.8%. Replicated; shipped. Details: `ARMS_RESULTS.md`.

**3. Split attacks.** Stock is 98% single-target. `deck_plan.py` shipped
`splitAttacks 0.0` until 2026-08-29, so the split machinery (a third of
attackers, weakest first, onto the highest-threat other opponent) had never
run in a shipped config. Tested at 512 games: defenders per attack 1.03 ->
1.28, win effect -2.5 pp (not significant, CI includes zero), ~12% more game
time. **Now shipped at 0.7**: the most visible humanity marker in a replay,
at a bounded cost.

**4. Instant timing.** Off-turn share of disruption on cEDH pods: stock 62%,
agent 62%. Forge already casts disruption at instant speed on other people's
turns; this dimension was never the gap the precon numbers made it look like
(2.4% off-turn on precons is a population artifact: precons barely carry
instants).

**5. Combo pursuit.** The steering layer works (Stage 2: 38/38 legal steers,
assembly improved). The conversion side had a measured misfire: ALL 31
early-burn vetoes on the shipping cEDH rerun were Tainted Pact (21) or
Jeska's Will (10) — premium value spells held forever for lines whose other
pieces were still in the library. 0.9.3 fires the veto only when every other
piece is already owned (hold Tainted Pact when Thassa's Oracle is in hand;
cast it as an answer otherwise). Validation rerun queued behind the
overnight.

**6. Intentional triggers.** `triggerMiss 0.0` shipped: the agent never
declines an optional trigger stock would take, and triggers on combo-line
cards are protected from miss rolls regardless (a per-iteration miss once
halted "you may" loops after a median ~23 iterations — the deck assembled its
win and stopped; that class of fizzle is structurally gone).

**7. Pursuing the win con.** The open gap, now measured to a standstill on
the dial side. Humans close on round 5.0; stock 10.9; the shipping agent 12.3
(cEDH). Head-to-head on precons: **parity at power** — 512 games per arm gave
50.9% (base), 50.9% (layers stripped) and 48.4% (split), pooled 619-617, CI
about +/-4.9 pp. Two ablation campaigns and seven arms agree: personality
dials neither win nor lose games. Win-rate gains, if they exist, live in
strategy CONTENT (lines, tutor targets, conversion), not personality. The
0.9.3 veto gate removes one measured drag (~1 wasted premium cast per game);
its cEDH validation is the remaining open measurement.

**8. Disrupting the enemy win con.** The SimLabHuman profile makes stock
propose counters eagerly; the threat veto then filters: fired counters aim at
mean threat 8.5, median 8, with 92% at threat >= 8 (win attempts and named
threats); vetoed proposals average threat 1.9 (chaff). 2.8 counters fired per
game vs stock's unaimed thresholds. Interaction volume overall: agent 4.6
disruption casts/game vs stock 4.4 on cEDH (the earlier 6.5 was the old
combat config and did not survive the config change; the counter layer
itself is unchanged, veto rate 68.0% -> 65.9%).

## Sim time (the product constraint)

Measured this week, single-game JVMs: cEDH all-plan median 272 s (p90 576 s),
precon mixed median 312 s (p90 at the 900 s clock). The shipping agent is
FASTER than the old config (median 373 s, p90 2,402 s): the combat scan cap
and dropping hold-back cut the tail 4x. Production changes landed:

- `TYPICAL_GAME_SECONDS` 120 -> 240 (the old figure predated the agent;
  healthy runs sat at double their estimate and read as stuck).
- `run_sim.py` now passes `--max-turns 120` (p95 of finished games is 70-75
  turns, max 122, so 120 trims ~nothing legitimate and ends turn-cycling
  stalemates before the 900 s clock).
- The worst-case tail is Forge itself: a token-copy board rechecks every
  static ability per token entering play, inside ONE turn, where no turn cap
  can fire. The 900 s clock is the only backstop. 12 games ~= 55-70 min
  sequential at current medians; parallel workers divide that.

## Corrections this document supersedes

- "Interaction volume is closed (6.5 vs 4.4)" — old-config number; shipping
  measures 4.6 vs 4.4. The aimed-ness (row 8) is the real, surviving edge.
- "Stock attacks with everything" — stock commits 71.6% of eligible
  attackers, agent 68.1% (indistinguishable). The old near-1.0 claim came
  from a biased denominator.
- The `blocky` arm never tested "block more"; it flattened per-archetype
  blockiness to 0.6. A genuine block-rate increase remains untested.
