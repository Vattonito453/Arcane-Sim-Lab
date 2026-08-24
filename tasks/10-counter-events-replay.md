# 10 — Counter events in the replay

The replay shows spells, combat, and zone exits, but says nothing when a
permanent or player gains counters — +1/+1, charge, loyalty, energy,
experience, poison. Decks built on those triggers (proliferate, All Will Be
One, Steel Overseer lines) look inert in playback even when they're winning,
and a viewer can't confirm the triggers actually fired. Make counter activity
visible so nobody has to trust that it happened.

## What Forge's log actually gives us (measured on the 2-game fixture)

Counter additions ARE in the stdout log as ability-resolution lines with
parseable shapes:

```
Uthros, Titanic Godcore (52) - Ai(2)-Kilo Helm Final puts a charge counter on Uthros, Titanic Godcore (52).
Crystalline Crawler (88) - Ai(2)-Kilo Helm Final puts a +1/+1 counter on Crystalline Crawler (88).
Uthros, Titanic Godcore (52) - Ai(2)-Kilo Helm Final puts three charge counters on Uthros, Titanic Godcore (52).
Steel Overseer (7) - Put a +1/+1 counter on each valid permanent.
Ripples of Potential (31) - Proliferate. (Choose any number of permanents…)
```

Known limits — this is the same inference regime as board reconstruction, and
the spec is honest about it:

- Quantities come as words ("a", "three", "X") and sometimes per-object
  ("for each charge counter on it") — parse what's explicit, record the rest
  as an unquantified `counter` event rather than guessing.
- "each valid permanent" and proliferate lines don't itemize targets. Emit
  the event without object resolution; don't invent targets.
- Counters placed as part of entering the battlefield ("enters with N
  +1/+1 counters") appear in the log but describe an entry Forge never
  otherwise logs — treat them as counter events only, not as board entries.
- **Oracle/reminder text also mentions counters** (Fabricate, Bloodthirst
  reminder text is echoed in cast lines). The parser must key on the
  resolution shape (`<Player> puts … counter[s] on …` / `Put a … counter on
  each …`), never on the word "counter" appearing anywhere.
- Energy and experience counters go to a *player*, not a card. The fixture
  has none — before claiming coverage, run a sim with an energy deck and an
  experience commander (e.g. Satya / Meren) and measure what Forge prints.
  Poison is explicitly in scope too (playtester ask, 2026-08-06).
- **The shim does not currently help.** Measured 2026-08-06 on
  `shim_raw_study_blight-curse_agent_v3_g32_c900_rot0.jsonl`: the typed
  GameLog entries carry counter activity only as the same free-text
  resolution lines stdout has (`… puts a -1/-1 counter on …`,
  `enters with three loyalty counters` under `EFFECT_REPLACED`), so the
  earlier claim here that task 07's typed GameLog reports counters
  structurally was wrong. The parser built by this task therefore covers
  BOTH paths — feed shim runs through it too.
- The sanctioned structural fix is a new shim record type (like the `zone`
  records) serialized from Forge's counter events on the event bus — a
  data-out-only addition that stays a thin adapter per the GPL boundary.
  That lives in the shim repo (task 07 territory); when it lands, this
  task's parser becomes the fallback for stdout and pre-upgrade shim logs.
  Either way keep the parser small and replaceable.

## What to build

1. **Adapter** (`engine/forge_log_adapter.py`): a `counter` event type —
   `{type: "counter", object?, player?, counter_type, amount?, raw}`.
   `object` carries the `(instance id)` reference when present. Split
   references on `(id)` per the existing rule, never on commas.
2. **Board** (`engine/board.py`): accumulate counter totals per tracked
   object so the reconstruction can report them; do not let counter events
   affect zone inference or `exit_match_rate`.
3. **Replay UI** (`web/lib/replay.ts`, replay page): counter events render in
   the event log like any other event; permanents on the tabletop show a
   counter badge (JetBrains Mono figure) when the running total is known.
   Player-level counters (energy, experience, poison) show beside the life
   total. Unquantified events still show in the log — visibility of the
   trigger is the point — with no badge change.
4. **Honesty note**: the existing "board is inference" note under the
   top-down table extends to counter totals. Never present a counter badge
   as ground truth.

## Acceptance criteria

- [ ] `test_adapter.py` gains fixture lines for: single named counter, worded
      quantity ("three"), "each valid permanent", proliferate, enters-with,
      and a reminder-text line that must NOT produce an event.
- [ ] Replaying the fixture shows counter events in the log and +1/+1 /
      charge badges on the affected permanents.
- [ ] `python3 engine/board.py engine/tests/fixtures/sim_sample.json
      --no-fetch` — `exit_match_rate` unchanged.
- [ ] A measured note (in this file or SIM_CALIBRATION.md) states what share
      of counter mentions in a real run were parseable vs unquantified, and
      what energy/experience decks actually print.
- [ ] `cd web && npm run verify` clean; no new CSS files; badges use tokens.

## Verification

```bash
python3 engine/tests/test_adapter.py
python3 engine/board.py engine/tests/fixtures/sim_sample.json --no-fetch
cd web && npm run verify
# manual: replay a fixture game, step to a Steel Overseer / Uthros trigger,
# confirm the event appears and the badge increments
```
