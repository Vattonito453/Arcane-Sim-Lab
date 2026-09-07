# Sim profile: where one game's CPU goes

Java Flight Recorder profiles of single 4-deck Commander games run through
the shim, taken 2026-09-07 on a 12-core Mac (Forge 2.0.13, shim 0.14.0,
JDK 17). Findings and the assessment they support are in
`engine/SIM_PERFORMANCE.md`, section "Stage 1b".

## Reproduce

No code changes are needed: the JVM reads `JAVA_TOOL_OPTIONS`.

```bash
export SIMLAB_SHIM_JAR=~/Desktop/Personal/simlab-forge-shim-main/simlab-forge-shim.jar
JAVA_TOOL_OPTIONS="-XX:FlightRecorderOptions=stackdepth=1024 \
  -XX:StartFlightRecording=filename=/tmp/game.jfr,settings=profile,dumponexit=true" \
python3 engine/run_sim.py --deck-dir engine/decks \
  --decks atraxa_counters.dck dnide_wildsear.dck drana_vampires.dck nekusar_punisher.dck \
  --games 1 --format Commander --humanize --out /tmp/prof --run-id prof
python3 studies/sim_profile/jfr_summary.py /tmp/game.jfr
```

Use `--agent shim` instead of `--humanize` for the stock-AI arm. The
humanized run rewrites `engine/plan_feedback.json`; `git checkout` it after.

Two traps the script already handles: `jfr print` emits only five frames per
stack unless `--stack-depth` is passed, and the recording itself truncates at
64 frames unless `stackdepth=` is raised, which matters here because Forge's
static-ability recomputation nests deeply. `sumOfPauses` is an ISO-8601
duration.

## Files

- `jfr_summary.py`: aggregates `jdk.ExecutionSample` by bucket, by owning AI
  routine, and by inclusive method; prints GC totals and heap peak.
- `agent_summary.txt`, `stock_summary.txt`: 64-frame recordings (9% of
  stacks truncated).
- `agent2_summary.txt`, `stock2_summary.txt`: 1024-frame recordings.
