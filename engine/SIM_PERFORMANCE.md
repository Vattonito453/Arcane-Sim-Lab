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

## Stage 1b (2026-09-07): inside the game, and a re-weighting of Finding 2

Prompted by an outside note (Richard Goldsmith, 2026-09-07) proposing four
speedups: multi-process parallelism, removing "double" combat evaluation in
the shim, headless JVM flags, and skipping Main Phase 1 evaluation. None of
those claims came with a measurement, so this section supplies them. Method
and raw summaries: `studies/sim_profile/`. Four single 4-deck games on a
12-core Mac (Forge 2.0.13, shim 0.14.0, JDK 17), Java Flight Recorder at
`settings=profile`; two with the humanized agent, two with stock AI.

| game | turns | in-JVM s | CPU user/real | GC pause | heap peak |
|---|---|---|---|---|---|
| agent | 44 | 47 | 1.46 | 0.9 s (2%) | 0.81 GiB |
| stock | 67 | 103 | 1.28 | 1.5 s (1.4%) | 0.77 GiB |
| agent (deep stacks) | 35 | 77 | – | 0.9 s | 0.74 GiB |
| stock (deep stacks) | 48 | 65 | – | 1.1 s | 0.70 GiB |

**Where the CPU goes (inclusive share of samples, all four games agree):**

- **37-52%: Forge's AI asking "what can I cast?"** `AiController.
  chooseSpellAbilityToPlay -> ComputerUtilAbility.getSpellAbilities ->
  Card.getAllPossibleAbilities -> GameActionUtil.getAlternativeCosts ->
  GameAction.checkStaticAbilities`. Every priority pass re-derives every
  card's static abilities across the whole game (`Game.forEachCardInGame`
  is 25-44% on its own). This is Forge-internal; the shim only wraps the
  call (`PlanPlayerController.chooseSpellAbilityToPlay` calls super first).
- **11-49%: Forge's stock combat AI**, `AiBlockController.assignBlockers`
  and `AiAttackController.declareAttackers`, most of it inside
  `ComputerUtil.predictNextCombatsRemainingLife` and `canPlayAndPayFor`
  (the AI checks what it could still cast while deciding blocks).
- **36-57%: the static-ability layer** (`forge.game.staticability`)
  reached from both of the above. Self time is dominated by collection
  churn: `TreeMap.getFirstEntry`, guava `StandardTable` cell iteration,
  `FCollection.addAll`, `HashSet.add`, `String.split` inside
  `CardProperty.cardHasProperty`.
- **0.0%: the shim's own combat passes** (`humanizeAttacks`,
  `humanizeBlocks`, `holdBackBlockers`, `preferOpenTarget`,
  `kingmakerReaim`). `CombatUtil.canBlock` anywhere in a stack: 0.2-3.2%.
  The 5.4 s/turn figure in the shim's `COMBAT_SCAN_CAP` comment predates
  that cap; after it, the shim's Java is not measurable in the profile.
- **0.0-0.1%: AWT/Swing.** The desktop GUI class is initialised and then
  idle. `ComputerUtilMana` (mana solving): 3-8% in stock-AI games, 3-4%
  with the agent. `forge.ai.simulation` (lookahead): 0%, it is off.
- **GC is 1-2% of wall time** at the default collector with `-Xmx4g`, and
  the live heap peaks at 0.7-0.8 GiB. There is no fragmentation story to
  fix; there IS 5x heap headroom that matters for concurrency (below).

**Startup, re-measured.** `--games 0` (init, load decks, exit): 4.9 s wall,
0.8 GB RSS on the Mac. Finding 2's 25-35 s per launch on the VM is still
the production number. But with `TYPICAL_GAME_SECONDS = 240` (re-measured
2026-08-28), a rotated 16-game job is 4 x 30 s of launch against 16 x 240 s
of play: **launch is ~3% of the job**. Finding 2 was written when games ran
20-130 s; the plan agent made steady-state play the bottleneck. Persisting
the JVM across rotations is still correct, and now worth about two
minutes an hour.

**Forcing headless does not work.** `-Djava.awt.headless=true` fails in
0.05 s with `ExceptionInInitializerError` / `HeadlessException` from
`forge.GuiDesktop.<clinit>` -> `initializeScreenScale` ->
`getDefaultScreenDevice`, exactly as `deploy/worker-entrypoint.sh`
documents. The `forge.profile.properties` keys the note names
(`loadCardImages`, `soundEngine`, `cardImageCacheSize`) do not exist in
Forge 2.0.13; the real preferences (`UI_DISABLE_CARD_IMAGES`,
`UI_ENABLE_SOUNDS`, ...) govern the GUI and never run in sim mode.

**Concurrency headroom.** One game already uses 1.3-1.5 cores (Forge runs
spell evaluation on its own `Game AI Eval` thread via
`ThreadUtil.executeWithTimeout`). On the 2-vCPU VM, two concurrent
rotations therefore share about 2.8 cores of demand across 2, so the
ceiling is roughly 1.3-1.5x, not 2x, and per-game wall time rises, which
the 900 s clock censors on (see SIM_CALIBRATION.md, concurrency table).
Memory: two JVMs at `-Xmx4g` do not fit beside api and web in 7.8 GB;
at `-Xmx2g` they would, given the 0.8 GiB live peak, but that peak is from
short games and must be confirmed on a full 16-game job with token boards
before the default changes. Concurrent games inside ONE JVM are not an
option without work: Forge keeps `Game.maxId`, `Card.cp2card`,
`MyRandom.random` and `AiCardMemory` as process-wide statics.

### Assessment of the four proposals

| proposal | measured basis | verdict |
|---|---|---|
| 1. Run rotations/games in parallel processes | rotations are a sequential loop in `run_sim.py`; 1.3-1.5 cores per game | Right idea, hardware-bound. ~1.3-1.5x on the 2-vCPU VM (needs the heap lowered to fit); 3-4x on a 4-8 vCPU box. Worth doing as an env-gated worker count. Never oversubscribe: the clock is wall-clock. |
| 2. Skip `super.declareAttackers/Blockers`; pre-filter flying | shim combat 0.0%; canBlock <=3.2%; stock combat AI 11-49% | The double scan is real in code and immeasurable in CPU. Removing the `super` calls would replace Forge's combat AI with ours, which is the rules-reimplementation the boundary forbids and would cost quality for at most the 11-49% Forge spends there. Decline. |
| 3. Headless flags, G1 tuning, disable images/sound | headless crashes; AWT 0.1%; GC 1-2%; prefs do not exist | Nothing to gain; one of the flags breaks the launch. Decline. |
| 4. Return nothing from `chooseSpellAbilityToPlay` in Main 1 | 37-52% of CPU is the "what can I cast?" enumeration, per priority pass, all phases | The target is right, the gate is wrong. Main 1 is one of ~40 priority passes per turn cycle in a pod; the cost is every pass. A gate that skips `super` on an opponent's turn with an empty stack outside a small set of windows is the same mechanism `tasks/21-interaction-timing.md` specifies for human-like instant timing, so one change serves both. Upper bound if three quarters of passes are skipped: ~30-40% of game CPU. It changes behaviour, so it ships only as an A/B arm with thresholds in plan JSON. |

Ranked next steps, all inside the GPL boundary:

1. Instrument the shim to count `chooseSpellAbilityToPlay` calls per game
   by (own turn?, phase, stack empty?) and emit the histogram as data. That
   turns the 30-40% upper bound into a number before anything is gated.
2. Build the priority gate as task 21's mechanism with plan-JSON thresholds;
   A/B it in `studies/skill_headtohead` for both win-rate and s/turn.
3. Concurrent rotations in `run_sim.py` behind `MTG_SIM_WORKERS`
   (default 1). Prerequisite: measure heap on a 16-game job and pick the
   `-Xmx` that lets two fit on the VM. `GET /sim-live` globs `_rot*` files
   and will need to pick the live one rather than the last.
4. Upstream: `Card.getAllPossibleAbilities -> getAlternativeCosts ->
   checkStaticAbilities` recomputes the full static layer per call. A cache
   keyed on the game's static-effect timestamp is a Card-Forge PR, not a
   fork, and would help every Forge user. Long shot, high value.
5. A bigger VM is the only 4x lever the note describes, and it is a cost
   decision (e2-standard-4 doubles the bill, `deploy/HOSTING.md`).
