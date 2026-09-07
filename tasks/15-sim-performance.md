# 15 — Explore ways to increase sim performance

**Stage 1 and 1b are done — see [`engine/SIM_PERFORMANCE.md`](../engine/SIM_PERFORMANCE.md)
for the measured findings (2026-08-02 against the production VM; 2026-09-07 in-game CPU profile, `studies/sim_profile/`).**
Two headline results: (1) seat rotation was silently off in every production
result for ~2 days, just self-corrected by a redeploy — a correctness issue,
not just a performance one; (2) per-JVM-launch overhead is ~25–35 s on a
single-launch job and rotation multiplies that by the pod size (one JVM
launch per deck), which is the real lever, not steady-state per-game time or
horizontal scaling. `deploy_plan.md`'s capacity math also assumed a 4-vCPU
box; the real one is 2-vCPU (`e2-standard-2`) — corrected in that doc.
Stage 2 below is now scoped by those findings, not open-ended.

**This is a research spike, not a shippable feature.** Per CLAUDE.md, a
simulation is "a 4 GB JVM for 10-60 minutes," and `deploy_plan.md` measures
"a 4-vCPU box runs ~3 concurrent Forge games and roughly 2,000 users saturate
one box. Watch queue depth, not CPU." Nobody has profiled *why* a single game
takes as long as it does, or where a JVM's wall-clock time actually goes.
Don't propose fixes before measuring — the repo's whole discipline is "trust
the measurement," and performance work is the easiest place to guess wrong.

## Stage 1 — measure, don't guess

Instrument a handful of real runs (`run_sim.py`) and answer, with numbers:

- JVM startup/teardown cost per game vs. actual game-play time. If Forge
  pays a large fixed cold-start cost per game (classloading, card DB parse),
  that's a very different fix than if games are simply slow to play out.
- Wall-clock time as a function of format/deck (Commander pods of 4 vs. a
  1v1 format, once task 09 exists) and of turn count — does time scale
  linearly with turns, or is there a fixed overhead dwarfing the variable
  part on short games?
- Where CPU time actually goes during a game: AI decision search (Forge's AI
  is what plays every seat), rules-engine bookkeeping, or I/O (log writing,
  `forge_raw_*.log` is 31 MB across current results per CLAUDE.md).
- Adapter/analysis-side cost, separately from Forge itself:
  `forge_log_adapter.py` parsing, `board.py` reconstruction, `analysis.py` /
  `deck_telemetry.py` compute — these run after the JVM exits and are pure
  Python, so they're much cheaper to speed up if they turn out to matter.
- Current queue behavior under load: does `jobqueue.py` + `worker.py` leave
  capacity idle between games (poll interval, claim overhead), or is the
  box CPU-bound the whole time per the ~3-concurrent-games measurement?

## Stage 2 — enumerate options against what Stage 1 finds

Do not commit to any of these until Stage 1 says which bottleneck is real.
Plausible directions, roughly ordered by how much they touch the GPL
boundary (CLAUDE.md "Legal posture" — anything that runs *inside* Forge or
links it is a GPL derivative and must stay a thin, engine-agnostic shim):

- **Reduce per-game JVM overhead** — if cold start dominates, a persistent
  Forge process that plays multiple games per JVM lifetime (this is exactly
  what task 07's GPL shim is for: it drives `Match` programmatically instead
  of shelling out once per game) would amortize startup across a whole
  gauntlet instead of paying it every game.
- **Horizontal scaling** — more worker hosts running games in parallel.
  Blocked until tasks 04 (Postgres queue) and 05 (object storage) both ship;
  today `MTG_DATA_DIR` is local-disk and single-host by construction. Don't
  reach for this before Stage 1 shows CPU-bound, not I/O- or overhead-bound,
  behavior — more boxes doesn't fix a fixed per-game cold-start tax.
- **Cheaper adapter/analysis passes** — only worth pursuing if Stage 1 shows
  this is a meaningful fraction of user-perceived latency (it runs after the
  sim, not during it, so it affects "time to see results," not "time to run
  the gauntlet").
- **Trim what gets logged** — `forge_raw_*.log` is kept on disk but nothing
  reads it after adaptation (CLAUDE.md gotcha). If Forge's own I/O to produce
  that log measurably slows the game (not just wastes disk), reducing
  verbosity is worth a line item — but confirm this against Stage 1 numbers
  before touching Forge's launch flags, and remember "no verbosity flag fixes
  the entering-battlefield gap" (CLAUDE.md) — this is a different, narrower
  claim about wall-clock cost, not about log completeness.

## What NOT to do

- Don't patch or fork Forge to make it faster — the sanctioned lever for
  anything Forge-internal is the GPL shim (task 07), not modifying the
  upstream jar.
- Don't scale API replicas as a performance fix — `_rate_ok()` is in-process
  (CLAUDE.md "API safety"); replicas double quotas silently rather than add
  sim throughput, since sim work happens in `worker.py`, not the API process.
- Don't propose a paid/priority tier as part of this task — monetization is
  explicitly gated on legal review (CLAUDE.md, tasks/README Tier 3 framing).

## Acceptance criteria (for the spike)

- [ ] A short written report (this file, updated in place, or a new
      `engine/SIM_PERFORMANCE.md` alongside `SIM_CALIBRATION.md`) states, with
      real numbers from real runs: JVM startup share vs. gameplay share of
      wall-clock time, how time scales with turn count, and whether the
      current ~3-concurrent-games/4-vCPU figure is CPU-bound or something
      else.
- [ ] A ranked list of candidate improvements, each tagged with which Stage 1
      measurement justifies it and which existing task (04/05/07) it depends
      on or duplicates.
- [ ] No code changes required to close this task — it hands off to whichever
      follow-up task the measurements justify (could be a new task file, or
      could fold into 04/05/07's existing scope).

## Verification

```bash
# Time a handful of real sims end-to-end and inside run_sim.py's own phases;
# no fixture substitutes for this — the fixture is 2 games, too small to
# measure JVM overhead against gameplay time.
time python3 engine/run_sim.py --decks <a.dck> <b.dck> --games 5 --format Commander --out /tmp/perf
```
