# Sim performance — Stage 1 measurement (task 15)

Measured directly against the production VM (`simlab`, 35.192.104.34) on
2026-08-02 — real job history from `jobs.db`, real per-game timings from the
shim's own JSONL logs, no synthetic/local reproduction. Per CLAUDE.md's
"trust the measurement" rule, two numbers below contradict existing docs and
those docs are corrected in the same commit as this file.

## The box itself

`simlab` is a GCP **`e2-standard-2`: 2 vCPU, 7.8 GiB RAM**, confirmed via
`gcloud compute instances describe`. `deploy_plan.md`'s capacity line ("a
4-vCPU box runs ~3 concurrent Forge games...") describes a *different,
never-provisioned* planning option (Hetzner CPX31 / Fly 2×shared-cpu-4GB) —
the box actually running production has half that CPU. `deploy/.env` caps
the worker container at `MTG_WORKER_CPUS=2`, i.e. the whole VM, so **the API
and web containers compete with the worker for CPU during a sim**, not just
theoretically — there is no headroom left on this box while a game runs.

## Finding 1 — seat rotation was silently off in every production result for ~2 days

`SIM_CALIBRATION.md`'s rule 1 ("always seat-rotate; never report a
single-seat win rate") and `mtg_engine.py`'s own comment ("SEAT ROTATION IS
THE DEFAULT") both say every run should rotate. **Every finished job between
2026-07-31 17:42 and 2026-08-02 21:27 did not** — their result files' `meta`
is a raw `java ... simlab.shim.SimShim ...` command line (the single-shot
code path's signature), never the rotated path's `{"source": "rotated", ...}`
marker. Checked directly: 8-deck-pod jobs run all N games in one fixed seat
order; a 2-deck 1-game job produced exactly 1 game, not the 2 a rotation
would produce.

The very next job after the worker container's most recent restart (2026-08-02
~21:51, "Up 5 minutes" when first checked) **did** rotate correctly —
`meta.source: "rotated"`, `rotations: 2`, two per-rotation JSONL files. The
code (`mtg_engine.py` `simulate()`, `run_sim.py`) is identical between the
local repo and the deployed container (diffed both, zero differences), and
`MTG_SIM_ROTATE` is not set anywhere in the current worker environment — so
this was not a code bug. The most likely explanation is a temporary
`MTG_SIM_ROTATE=0` set in a prior `.env` during the shim-deploy debugging
work (2026-08-01 through 2026-08-02) that got cleared by the most recent
redeploy. **Unverified — nobody confirmed the actual `.env` from that window,
since old container instances are gone.** What's confirmed is the *effect*:
every real result from that ~2-day window has an unrotated, seat-biased win
rate, and every result since the last redeploy does not.

**Action needed, not just a performance note:** audit whether any result from
that window is still being shown to a user as a "real" win rate, and consider
whether `_read_result`/the results pages should surface `meta.source !==
"rotated"` more prominently than they do today (the UI note referenced in
task 16 already exists for unrotated runs — confirm it actually renders for
these specific files).

## Finding 2 — per-JVM-launch overhead is the real cost, and rotation multiplies it

The shim logs each game's own wall-clock cost (`{"rec":"result", ..., "ms":
...}`). Comparing that sum against the job's total wall-clock time
(`finished - started` in `jobs.db`) isolates JVM startup/teardown overhead
from actual gameplay:

| Job | Games | JVM launches | Sum of game `ms` | Job wall time | Overhead | Overhead/launch |
|---|---|---|---|---|---|---|
| `cb3f63b5` | 8 (1 launch) | 1 | 969.3 s | 1001.7 s | 32.4 s | 32.4 s |
| `389f6435` | 8 (1 launch) | 1 | 877.5 s | 902.0 s | 24.5 s | 24.5 s |
| `0da4d7d9` | 8 (1 launch) | 1 | 863.5 s | 897.2 s | 33.7 s | 33.7 s |
| `9d97a823` | 8 (1 launch) | 1 | 833.1 s | 858.4 s | 25.3 s | 25.3 s |
| `a28fecae` | 8 (1 launch) | 1 | 881.5 s | 908.7 s | 27.2 s | 27.2 s |
| `6c316e50` | 2 (1 launch) | 1 | 217.3 s | 278.9 s | 61.6 s | 61.6 s |
| `6a04076b` | 1 (1 launch) | 1 | 21.0 s | 51.6 s | 30.6 s | 30.6 s |
| `b01bd0ed467e` (rotated) | 2 (2 launches) | 2 | 60.0 s | 245.7 s | 185.7 s | **92.9 s** |

Single-launch overhead clusters around **25–35 s** regardless of game count
in that launch — consistent with a mostly-fixed JVM/Forge/AWT/deck-load cost,
amortized across however many games run in that one process. The one rotated
sample paid **~93 s of overhead per launch**, over 2–3× the single-launch
figure; it's also the very first JVM launch of a freshly restarted
container, so cold OS/page-cache effects may be inflating it — **this needs
a second rotated sample from a warm container before trusting the exact
multiplier**, but the direction is unambiguous: rotation launches one JVM per
deck in the pod (`rotations = len(deck_names)`), so a 4-player Commander pod
now pays this overhead **4 times per job**, not once. Steady-state per-game
time itself (roughly 20–130 s depending on the matchup/deck, no clear
correlation measured yet with turn count) is not the bottleneck — the
now-mandatory multiplied cold start is.

## What this means for task 15's candidate list

- **Persistent-JVM shim (task 07's `Match`-driving GPL shim) is the highest-
  leverage fix**, not a nice-to-have: it would let one JVM play every
  rotation's games back-to-back instead of relaunching per rotation, cutting
  the ~25–90 s overhead from N launches to 1 for the whole job. Worth
  prioritizing ahead of horizontal scaling.
- **Horizontal scaling (tasks 04/05) does not fix this** — more boxes just
  run more copies of the same per-launch tax in parallel, it doesn't remove
  the tax. Confirmed this box is genuinely capacity-constrained (2 vCPU
  total, worker alone claims both), so scaling *is* eventually needed, but
  it's a different problem from the cold-start multiplier above.
- **Second measurement needed before committing to a fix size**: one more
  rotated job on a warm (not-just-restarted) container, ideally a 4-deck pod
  (today's real product shape) rather than the 2-deck sample available here.

## Open items

- [ ] Confirm (or rule out) the `MTG_SIM_ROTATE=0` hypothesis for the
      2026-07-31–2026-08-02 window — check any surviving `.env` backup or
      deploy log; if it can't be confirmed, say so in the incident record
      rather than asserting it.
- [ ] Re-measure rotated-job overhead on a warm container with a 4-deck pod.
- [ ] Decide whether any result file from the unrotated window needs a
      retroactive label or removal from result listings.
